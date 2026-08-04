"""SSE events router — real-time streaming + Lambda→API bridge.

OWNER: Ashfaq (Track A).

Endpoints:
    GET  /api/events      — SSE streaming with topic filtering + heartbeat
    POST /internal/sse    — Lambda worker pushes events to connected dashboards
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.bus import sse
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()
internal_router = APIRouter()  # Mounted at root, no /api prefix

# Heartbeat interval keeps CloudFront / ALB connections alive (spec §4).
HEARTBEAT_SECONDS = 15


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------


@router.get("/events")
async def stream_events(
    request: Request,
    topics: str = Query(
        default="*",
        description=(
            "Comma-separated topic patterns. "
            "Use * for all, or specific: task.{id}.step,rule.changed,metrics.tick"
        ),
    ),
):
    """Server-Sent Events — real-time updates to the frontend.

    Topics (spec §4):
        task.{id}.step          — tool call during execution
        task.{id}.status        — task status changes
        rule.changed            — rule version bumped
        playbook.changed        — playbook compiled/invalidated/relearned
        metrics.tick            — metrics updated
        approval.requested      — extension: autonomy gate
        insight.created         — extension: trend detected

    Client reconnects with Last-Event-ID header automatically.
    """
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]

    async def event_generator():
        event_id = 0
        async for payload in sse.subscribe(topic_list):
            event_id += 1
            yield {
                "id": str(event_id),
                "event": payload["topic"],
                "data": json.dumps(payload["data"], default=str),
            }

    async def heartbeat_generator():
        """Wrap the event generator with periodic heartbeats."""
        gen = event_generator()
        while True:
            if await request.is_disconnected():
                break
            try:
                # Wait for next event, but send heartbeat if nothing arrives
                event = await asyncio.wait_for(gen.__anext__(), timeout=HEARTBEAT_SECONDS)
                yield event
            except TimeoutError:
                yield {"event": "heartbeat", "data": ""}
            except StopAsyncIteration:
                break

    return EventSourceResponse(
        heartbeat_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx / CloudFront
        },
    )


# ---------------------------------------------------------------------------
# Internal SSE bridge (Lambda → API)
# ---------------------------------------------------------------------------


@internal_router.post("/internal/sse")
async def internal_sse_publish(
    body: dict[str, Any],
    x_internal_secret: str = Header(...),
):
    """Lambda worker publishes events to connected dashboards.

    The worker can't open an SSE connection itself, so it POSTs here
    and we fan out to all subscribers.

    Body: {"topic": "playbook.changed", "data": {...}}
    """
    if x_internal_secret != settings.internal_sse_secret:
        raise HTTPException(403, "invalid internal secret")

    topic = body.get("topic")
    data = body.get("data", {})

    if not topic:
        raise HTTPException(400, "missing 'topic' field")

    await sse.publish(topic, data)
    log.info("internal sse bridge: %s", topic)
    return {"status": "ok"}


@internal_router.post("/internal/fanout")
async def internal_fanout(
    body: dict[str, Any],
    x_internal_secret: str = Header(...),
):
    """Apply an interrupt broadcast from another instance (T3.7, D4).

    Each API instance has its own in-process InterruptBus, so a rule change
    handled by one instance cannot reach executors running on another. SNS
    delivers here to close that window.

    Best-effort by design: `tasks.interrupt_flag` remains the correctness
    guarantee, so a missed broadcast costs at most one extra step before the
    durable check catches it.
    """
    if x_internal_secret != settings.internal_sse_secret:
        raise HTTPException(403, "invalid internal secret")

    from app.bus import interrupt_bus
    from app.core.fanout import handle_broadcast

    # SNS HTTP subscriptions wrap the payload in an envelope.
    message = body
    if "Message" in body and isinstance(body["Message"], str):
        try:
            message = json.loads(body["Message"])
        except json.JSONDecodeError:
            raise HTTPException(400, "unparseable SNS Message") from None

    applied = await handle_broadcast(message, interrupt_bus)
    return {"status": "ok", "applied": applied}
