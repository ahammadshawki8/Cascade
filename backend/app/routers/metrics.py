"""Metrics router — cold vs guided performance delta (the demo money-shot).

OWNER: Ashfaq (Track A).

Endpoints:
    GET /api/metrics — Aggregated cold vs guided metrics + status counts
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import settings
from app.core.models import Metrics, ModeMetrics, RetrievalMetrics

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    # settings, not os.environ — see the note in routers/tasks.py.
    return settings.cascade_stub_mode


@router.get("/metrics", response_model=Metrics)
async def get_metrics():
    """Aggregate cold vs guided metrics from episodes + status counts.

    This is the demo money-shot: judges MUST see guided ≥3× faster than cold.
    """
    if _stub_mode():
        return Metrics(
            cold=ModeMetrics(avg_ms=12400, avg_tokens=8200, avg_steps=7.2, runs=5),
            guided=ModeMetrics(avg_ms=3100, avg_tokens=1800, avg_steps=3.0, runs=8),
            retrieval=RetrievalMetrics(hits=8, precondition_misses=1, stale_blocks=1),
            counts_by_status={"queued": 0, "running": 0, "succeeded": 11, "failed": 2},
        )

    from app.db import q
    mode_rows = await q(
        """
        SELECT mode,
               AVG(latency_ms)::FLOAT AS avg_ms,
               AVG(tokens)::FLOAT AS avg_tokens,
               AVG(steps)::FLOAT AS avg_steps,
               COUNT(*)::INT AS runs
        FROM episodes
        WHERE outcome = 'success'
        GROUP BY mode
        """
    )

    cold = ModeMetrics()
    guided = ModeMetrics()

    for row in mode_rows:
        m = ModeMetrics(
            avg_ms=row["avg_ms"],
            avg_tokens=row["avg_tokens"],
            avg_steps=row["avg_steps"],
            runs=row["runs"],
        )
        if row["mode"] == "explore":
            cold = m
        elif row["mode"] == "guided":
            guided = m

    # A hit is a run that actually executed a playbook. Misses and stale blocks
    # are recorded by the executor as audit events at the moment the decision is
    # made — inferring them from task columns counted the cold run that authored
    # a playbook as a miss, because that task also carried a playbook_id.
    hit_rows = await q(
        "SELECT COUNT(*)::INT AS hits FROM episodes WHERE mode = 'guided'"
    )
    # Only count events from the current world. audit_log survives a demo reset
    # by design, so without this boundary the hit-rate would carry misses from
    # runs whose episodes have already been cleared and never recover.
    event_rows = await q(
        """
        SELECT
            COUNT(*) FILTER (WHERE kind = 'retrieval.precondition_miss')::INT AS misses,
            COUNT(*) FILTER (WHERE kind = 'retrieval.stale_block')::INT        AS stale_blocks
        FROM audit_log
        WHERE kind IN ('retrieval.precondition_miss', 'retrieval.stale_block')
          AND at > COALESCE(
                (SELECT max(at) FROM audit_log WHERE kind = 'world.reset'),
                '-infinity'::TIMESTAMPTZ
              )
        """
    )
    retrieval = RetrievalMetrics(
        hits=(hit_rows[0]["hits"] if hit_rows else 0) or 0,
        precondition_misses=(event_rows[0]["misses"] if event_rows else 0) or 0,
        stale_blocks=(event_rows[0]["stale_blocks"] if event_rows else 0) or 0,
    )

    status_rows = await q(
        """
        SELECT status, COUNT(*)::INT AS cnt
        FROM tasks
        GROUP BY status
        """
    )
    counts_by_status = {r["status"]: r["cnt"] for r in status_rows}

    # Surfaced in the metric bar: the demo must never imply it is talking to
    # Bedrock when it has silently fallen back to the local path.
    from app.core.llm import degraded_reason, llm_status, serving_provider

    status = llm_status()
    return Metrics(
        cold=cold,
        guided=guided,
        retrieval=retrieval,
        counts_by_status=counts_by_status,
        llm=status,
        llm_provider=serving_provider(),
        llm_reason=degraded_reason(),
    )
