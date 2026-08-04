"""In-process event bus + SSE fan-out (spec §5.2, D4).

OWNER: Ashfaq (Track A). PUBLIC SURFACE FROZEN AFTER DAY 0.

⚠️ Track B imports interrupt_bus and sse from here (executor.py calls
register/unregister; cascade.py calls interrupt_many and sse.publish).
Signature changes require a contract PR.

The SSE topic names below are part of the frozen contract because the
frontend subscribes to them by string.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FROZEN SSE topic names (spec §5.2). Frontend subscribes by these strings.
# ---------------------------------------------------------------------------

TOPIC_TASK_STEP = "task.{task_id}.step"
TOPIC_TASK_STATUS = "task.{task_id}.status"
TOPIC_RULE_CHANGED = "rule.changed"
TOPIC_PLAYBOOK_CHANGED = "playbook.changed"
TOPIC_METRICS_TICK = "metrics.tick"
TOPIC_APPROVAL_REQUESTED = "approval.requested"   # extension
TOPIC_INSIGHT_CREATED = "insight.created"         # extension

ALL_STATIC_TOPICS = [
    TOPIC_RULE_CHANGED,
    TOPIC_PLAYBOOK_CHANGED,
    TOPIC_METRICS_TICK,
    TOPIC_APPROVAL_REQUESTED,
    TOPIC_INSIGHT_CREATED,
]


class InterruptBus:
    """Microsecond in-process interrupt delivery, zero DB reads (D4).

    The durable `tasks.interrupt_flag` column is the correctness fallback;
    this is the fast path. An executor registers before it starts stepping
    and unregisters in a finally block.
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._reasons: dict[str, str] = {}

    def register(self, task_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[str(task_id)] = event
        return event

    def unregister(self, task_id: str) -> None:
        self._events.pop(str(task_id), None)
        self._reasons.pop(str(task_id), None)

    def interrupt(self, task_id: str, reason: str) -> None:
        key = str(task_id)
        self._reasons[key] = reason
        event = self._events.get(key)
        if event is not None:
            event.set()
            log.info("interrupt delivered via bus: task=%s reason=%s", key, reason)

    def interrupt_many(self, task_ids: list[str], reason: str) -> None:
        for task_id in task_ids:
            self.interrupt(task_id, reason)

    def reason_for(self, task_id: str) -> str | None:
        return self._reasons.get(str(task_id))

    def is_interrupted(self, task_id: str) -> bool:
        event = self._events.get(str(task_id))
        return event is not None and event.is_set()


class SSEBroadcaster:
    """Topic-based fan-out to connected dashboards.

    Each subscriber gets its own bounded queue. Slow clients drop events
    rather than blocking publishers — events are notifications, state lives
    in the database (spec edge case #18).
    """

    def __init__(self, max_queue: int = 256) -> None:
        self._subscribers: list[tuple[set[str], asyncio.Queue]] = []
        self._max_queue = max_queue

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        payload = {"topic": topic, "data": data}
        for topics, queue in list(self._subscribers):
            if not _matches(topic, topics):
                continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                log.warning("sse subscriber queue full, dropping event %s", topic)

    async def subscribe(self, topics: list[str]) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        entry = (set(topics), queue)
        self._subscribers.append(entry)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(entry)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


def _matches(topic: str, patterns: set[str]) -> bool:
    """Exact match, or a trailing '*' wildcard (e.g. 'task.*')."""
    if topic in patterns or "*" in patterns:
        return True
    return any(p.endswith("*") and topic.startswith(p[:-1]) for p in patterns)


# Module-level singletons — imported by both tracks.
interrupt_bus = InterruptBus()
sse = SSEBroadcaster()
