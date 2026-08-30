"""Intelligence router — insights, savings, replay, time travel, graph.

Endpoints:
    GET  /api/insights                    — trend findings (T1.2)
    POST /api/insights/{id}/dismiss       — hide one
    GET  /api/savings                     — cost and toil avoided (T1.4)
    POST /api/rules/{key}/replay          — counterfactual against history (T2.2)
    GET  /api/timetravel                  — state as of N minutes ago (T2.3)
    GET  /api/graph                       — blast-radius graph (T2.4)
    GET  /api/anti-playbooks              — negative memory (T2.5)
    GET  /api/postmortems/{episode_id}    — generated writeup (T1.3)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import ADMIN, OPERATOR, Principal, require
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


require_admin = require(ADMIN)
require_operator = require(OPERATOR)


# ---------------------------------------------------------------------------
# Insights (T1.2)
# ---------------------------------------------------------------------------


class InsightItem(BaseModel):
    insight_id: UUID
    kind: str
    summary: str
    related_rule_key: str | None = None
    suggested_params: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    dismissed: bool = False


class InsightListResponse(BaseModel):
    insights: list[InsightItem]
    count: int


@router.get("/insights", response_model=InsightListResponse)
async def list_insights(include_dismissed: bool = False):
    if _stub_mode():
        return InsightListResponse(insights=[], count=0)

    from app.db import q

    rows = await q(
        """
        SELECT insight_id, kind, summary, related_rule_key, suggested_params,
               evidence, created_at, dismissed
        FROM insights
        WHERE (%s OR NOT dismissed)
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (include_dismissed,),
    )
    insights = [InsightItem(**r) for r in rows]
    return InsightListResponse(insights=insights, count=len(insights))


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(insight_id: UUID):
    if _stub_mode():
        return {"status": "ok"}

    from app.db import q

    await q(
        "UPDATE insights SET dismissed = TRUE WHERE insight_id = %s",
        (str(insight_id),),
    )
    return {"status": "ok", "insight_id": str(insight_id)}


@router.post("/insights/scan")
async def scan_insights(principal: Principal = Depends(require_admin)):
    """Run the detectors now instead of waiting for the scheduled sweep."""
    if _stub_mode():
        raise HTTPException(400, "scan requires CASCADE_STUB_MODE=false")

    from app import db as database
    from app.core.insights import scan_for_insights

    found = await scan_for_insights(database)
    return {"status": "ok", "found": len(found)}


# ---------------------------------------------------------------------------
# Playbook generalization (T3.8)
# ---------------------------------------------------------------------------


@router.get("/generalize/candidates")
async def generalization_candidates():
    """Clusters of runbooks that differ only in their arguments."""
    if _stub_mode():
        return {"clusters": [], "count": 0}

    from app import db as database
    from app.core.generalize import find_generalizable

    clusters = await find_generalizable(database)
    return {
        "count": len(clusters),
        "clusters": [
            {
                "size": len(members),
                "members": [
                    {
                        "playbook_id": str(m["playbook_id"]),
                        "name": m["name"],
                        "confidence": float(m["confidence"]),
                    }
                    for m in members
                ],
            }
            for members in clusters
        ],
    }


@router.post("/generalize")
async def generalize(principal: Principal = Depends(require_admin)):
    """Merge each eligible cluster into one parameterized runbook.

    Members are archived rather than deleted — episodes reference them, and the
    `merged_from` lineage is what makes the merge auditable.
    """
    if _stub_mode():
        raise HTTPException(400, "generalize requires CASCADE_STUB_MODE=false")

    from app import db as database
    from app.core.generalize import find_generalizable, generalize_cluster

    created = []
    for members in await find_generalizable(database):
        playbook_id = await generalize_cluster(members, database)
        if playbook_id:
            created.append(str(playbook_id))

    return {"status": "ok", "created": created, "count": len(created)}


# ---------------------------------------------------------------------------
# Savings (T1.4)
# ---------------------------------------------------------------------------


@router.get("/savings")
async def savings():
    """Tokens, dollars and engineer-hours avoided by reuse."""
    if _stub_mode():
        return {"available": False, "message": "Stub mode."}

    from app import db as database
    from app.core.savings import compute_savings

    return await compute_savings(database)


# ---------------------------------------------------------------------------
# Counterfactual replay (T2.2)
# ---------------------------------------------------------------------------


class ReplayRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=1000)


@router.post("/rules/{rule_key}/replay")
async def replay_rule(rule_key: str, body: ReplayRequest):
    """What a proposed policy would have done to historical incidents.

    Deterministic and side-effect free — it re-decides eligibility, it does not
    re-execute anything.
    """
    if _stub_mode():
        raise HTTPException(400, "replay requires CASCADE_STUB_MODE=false")

    from app import db as database
    from app.core.analysis import counterfactual_replay

    try:
        return await counterfactual_replay(rule_key, body.params, database, body.limit)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------
# Time travel (T2.3)
# ---------------------------------------------------------------------------


@router.get("/timetravel")
async def timetravel(minutes_ago: int = Query(default=10, ge=1, le=1500)):
    """State as of N minutes ago, straight from CockroachDB MVCC history."""
    if _stub_mode():
        raise HTTPException(400, "time travel requires CASCADE_STUB_MODE=false")

    from app import db as database
    from app.core.analysis import time_travel

    return await time_travel(database, minutes_ago)


# ---------------------------------------------------------------------------
# Blast radius graph (T2.4)
# ---------------------------------------------------------------------------


@router.get("/graph")
async def graph(rule_key: str | None = None):
    """rules -> playbooks -> tasks, with stale edges marked."""
    if _stub_mode():
        return {"nodes": [], "edges": [], "focus_rule": rule_key, "stale_edges": 0}

    from app import db as database
    from app.core.analysis import blast_radius_graph

    return await blast_radius_graph(database, rule_key)


# ---------------------------------------------------------------------------
# Negative memory (T2.5)
# ---------------------------------------------------------------------------


@router.get("/anti-playbooks")
async def anti_playbooks(limit: int = Query(default=25, ge=1, le=100)):
    """What the system has learned *not* to do."""
    if _stub_mode():
        return {"anti_playbooks": [], "count": 0}

    from app.db import q

    rows = await q(
        """
        SELECT anti_id, incident_kind, attempted_action, failure_reason,
               occurrences, created_at, updated_at
        FROM anti_playbooks
        ORDER BY occurrences DESC, updated_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"anti_playbooks": [dict(r) for r in rows], "count": len(rows)}


# ---------------------------------------------------------------------------
# Postmortems (T1.3)
# ---------------------------------------------------------------------------


@router.get("/postmortems/{episode_id}")
async def postmortem(episode_id: UUID):
    if _stub_mode():
        raise HTTPException(404, "not available in stub mode")

    from app.db import one

    row = await one(
        """
        SELECT postmortem_id, episode_id, s3_key, summary, body, generated_at
        FROM postmortems WHERE episode_id = %s
        """,
        (str(episode_id),),
    )
    if row is None:
        raise HTTPException(404, f"no postmortem for episode {episode_id}")
    return dict(row)


@router.get("/postmortems")
async def list_postmortems(limit: int = Query(default=20, ge=1, le=100)):
    if _stub_mode():
        return {"postmortems": [], "count": 0}

    from app.db import q

    rows = await q(
        """
        SELECT p.postmortem_id, p.episode_id, p.summary, p.generated_at,
               t.input AS task_input, e.outcome, e.mode
        FROM postmortems p
        JOIN episodes e ON e.episode_id = p.episode_id
        JOIN tasks t ON t.task_id = e.task_id
        ORDER BY p.generated_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"postmortems": [dict(r) for r in rows], "count": len(rows)}
