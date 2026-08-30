"""Cross-instance interrupt fan-out (T3.7, decision D4).

`InterruptBus` delivers in microseconds — to tasks running in *this* process.
With one ECS task that is the whole story, which is why the demo runs at
desired-count 1. Scale out and a rule change reaches only the instance that
served the request; executors elsewhere keep going until they hit the durable
`tasks.interrupt_flag`, up to one step later.

This closes that window by publishing interrupts to SNS, which every instance
subscribes to.

The durable flag remains the correctness guarantee. SNS is best-effort speed,
exactly like the post-commit SQS publish (D5): if it fails, nothing breaks —
the flag still stops the executor before its next side effect. So every failure
here is logged and swallowed.

Off unless `ENABLE_SNS_FANOUT=true` and a topic ARN is configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any

log = logging.getLogger(__name__)

# Identifies this process so it can ignore its own broadcasts — the local bus
# already delivered them, and re-applying would be pointless work.
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}"

_sns_client: Any = None
_checked = False


def _settings() -> Any:
    from app.config import settings

    return settings


def enabled() -> bool:
    settings = _settings()
    return bool(settings.enable_sns_fanout and settings.sns_bus_topic_arn)


def _client():
    global _sns_client, _checked
    if _checked:
        return _sns_client
    _checked = True

    if not enabled():
        return None
    try:
        import boto3

        _sns_client = boto3.client("sns", region_name=_settings().aws_region)
        log.info("SNS interrupt fan-out enabled (instance %s)", INSTANCE_ID)
    except Exception as exc:
        log.warning("SNS fan-out unavailable: %s", exc)
        _sns_client = None
    return _sns_client


async def publish_interrupt(task_ids: list[str], reason: str) -> bool:
    """Broadcast an interrupt to every instance. False if it didn't go out."""
    client = _client()
    if client is None or not task_ids:
        return False

    try:
        await asyncio.to_thread(
            client.publish,
            TopicArn=_settings().sns_bus_topic_arn,
            Message=json.dumps(
                {
                    "kind": "interrupt",
                    "origin": INSTANCE_ID,
                    "task_ids": [str(t) for t in task_ids],
                    "reason": reason,
                }
            ),
            MessageAttributes={
                "kind": {"DataType": "String", "StringValue": "interrupt"}
            },
        )
        log.info("interrupt fan-out published for %d task(s)", len(task_ids))
        return True
    except Exception as exc:
        # Never fatal: tasks.interrupt_flag is the correctness path.
        log.warning("interrupt fan-out failed (durable flag still applies): %s", exc)
        return False


async def handle_broadcast(message: dict[str, Any], interrupt_bus) -> int:
    """Apply an interrupt broadcast received from another instance.

    Returns how many local tasks were signalled. Called by the internal SNS
    webhook; ignores anything this process itself published.
    """
    if message.get("kind") != "interrupt":
        return 0
    if message.get("origin") == INSTANCE_ID:
        return 0

    task_ids = message.get("task_ids") or []
    reason = message.get("reason") or "rule changed"
    if not task_ids or interrupt_bus is None:
        return 0

    interrupt_bus.interrupt_many([str(t) for t in task_ids], reason)
    log.info(
        "applied interrupt broadcast from %s for %d task(s)",
        message.get("origin"),
        len(task_ids),
    )
    return len(task_ids)
