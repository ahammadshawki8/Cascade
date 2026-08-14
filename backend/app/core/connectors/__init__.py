"""Connections — where a step reaches something real.

A connection is bound to a tool. When `notify_oncall` runs and a live Slack
connection is bound to it, the mock world still records the notification exactly
as before *and* a message lands in a channel. That layering is deliberate: the
seeded demo keeps its zero-dependency guarantee, every existing assertion keeps
passing, and the real side effect is additive rather than a replacement.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.connectors.payloads import KINDS, build
from app.core.connectors.transport import BREAKER_THRESHOLD, DeliveryResult, send

log = logging.getLogger(__name__)

__all__ = [
    "BREAKER_THRESHOLD",
    "KINDS",
    "DeliveryResult",
    "build",
    "connection_for_tool",
    "deliver_for_tool",
    "send",
]


async def connection_for_tool(tool_name: str, db) -> dict[str, Any] | None:
    """The enabled connection bound to this tool, if there is one."""
    try:
        rows = await db.q(
            """
            SELECT connection_id, name, kind, endpoint, config, mode, failures
            FROM connections
            WHERE tool_name = %s AND enabled = true
            ORDER BY created_at
            LIMIT 1
            """,
            (tool_name,),
        )
    except Exception as exc:
        # A missing table means migration 006 has not run. That must not stop
        # the mock world working, which is the whole point of the layering.
        log.debug("connection lookup for %s unavailable: %s", tool_name, exc)
        return None
    return rows[0] if rows else None


async def deliver_for_tool(
    tool_name: str,
    message: str,
    context: dict[str, Any],
    idempotency_key: str,
    db,
    task_id: Any = None,
    step_index: Any = None,
) -> dict[str, Any] | None:
    """Send through whatever is bound to this tool. None when nothing is.

    Swallows everything. A step whose mock side effect succeeded has done its
    job; a chat message failing to arrive cannot be allowed to turn that into a
    failed remediation.
    """
    try:
        connection = await connection_for_tool(tool_name, db)
        if connection is None:
            return None
        return await send(
            connection,
            message,
            context,
            idempotency_key or f"{tool_name}:{context.get('incident_id')}",
            db,
            task_id=task_id,
            step_index=step_index,
        )
    except Exception as exc:
        log.warning("connector delivery for %s failed: %s", tool_name, exc)
        return None
