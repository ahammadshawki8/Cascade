"""Playbooks router — runbook library with provenance and freshness.

OWNER: Ashfaq (Track A).

Endpoints:
    GET /api/playbooks              — List all playbooks with deps + freshness
    GET /api/playbooks/{id}         — Single playbook detail
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import OPERATOR, Principal, require
from app.config import settings
from app.core.contracts import _STUB_PLAYBOOK_ID, _STUB_SPEC, check_freshness
from app.core.models import Playbook, PlaybookDep

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    # settings, not os.environ — see the note in routers/tasks.py.
    return settings.cascade_stub_mode


# ---------------------------------------------------------------------------
# Stub data
# ---------------------------------------------------------------------------

_STUB_PLAYBOOKS = [
    Playbook(
        playbook_id=_STUB_PLAYBOOK_ID,
        name="rollback-bad-deploy",
        domain="incidents",
        version=1,
        status_cache="active",
        spec=_STUB_SPEC,
        confidence=0.72,
        uses=12,
        successes=10,
        failures=2,
        deps=[
            PlaybookDep(
                rule_key="incident.auto_remediate_tier",
                rule_version=1,
                citation="step 2: eligibility gate",
                extraction_confidence=0.95,
                is_stale=False,
                head_version=1,
            ),
            PlaybookDep(
                rule_key="incident.rollback_window",
                rule_version=1,
                citation="step 2: eligibility gate",
                extraction_confidence=0.90,
                is_stale=False,
                head_version=1,
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PlaybookListResponse(BaseModel):
    playbooks: list[Playbook]
    count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_playbook(row: dict) -> Playbook:
    """Build a Playbook model from a DB row, enriching with deps + freshness."""
    from app.db import q
    playbook_id = str(row["playbook_id"])

    dep_rows = await q(
        """
        SELECT d.rule_key, d.rule_version, d.citation, d.extraction_confidence,
               r.version AS head_version
        FROM playbook_deps d
        LEFT JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        WHERE d.playbook_id = %s
        """,
        (playbook_id,),
    )

    deps = []
    for d in dep_rows:
        is_stale = d.get("head_version") is not None and d["rule_version"] != d["head_version"]
        deps.append(
            PlaybookDep(
                rule_key=d["rule_key"],
                rule_version=d["rule_version"],
                citation=d.get("citation"),
                extraction_confidence=d.get("extraction_confidence", 0.5),
                is_stale=is_stale,
                head_version=d.get("head_version"),
            )
        )

    return Playbook(
        playbook_id=row["playbook_id"],
        name=row["name"],
        domain=row["domain"],
        version=row["version"],
        supersedes=row.get("supersedes"),
        status_cache=row["status_cache"],
        spec=row["spec"],
        confidence=row["confidence"],
        uses=row["uses"],
        successes=row["successes"],
        failures=row["failures"],
        deps=deps,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/playbooks", response_model=PlaybookListResponse)
async def list_playbooks():
    """List all playbooks with deps + inline freshness indicators."""
    if _stub_mode():
        return PlaybookListResponse(
            playbooks=_STUB_PLAYBOOKS, count=len(_STUB_PLAYBOOKS)
        )

    from app.db import q
    rows = await q(
        """
        SELECT playbook_id, name, domain, version, supersedes,
               status_cache, spec, confidence,
               uses, successes, failures, created_at, updated_at
        FROM playbooks
        ORDER BY
            CASE status_cache
                WHEN 'active'      THEN 1
                WHEN 'candidate'   THEN 2
                WHEN 'suspect'     THEN 3
                WHEN 'invalidated' THEN 4
                WHEN 'rejected'    THEN 5
                ELSE 6
            END,
            confidence DESC
        """
    )

    playbooks = []
    for row in rows:
        pb = await _load_playbook(row)
        playbooks.append(pb)

    return PlaybookListResponse(playbooks=playbooks, count=len(playbooks))


@router.get("/playbooks/{playbook_id}", response_model=Playbook)
async def get_playbook(playbook_id: UUID):
    """Get a single playbook with full detail, deps, and freshness check."""
    if _stub_mode():
        for pb in _STUB_PLAYBOOKS:
            if pb.playbook_id == playbook_id:
                return pb
        raise HTTPException(404, f"playbook {playbook_id} not found")

    from app.db import one
    row = await one(
        """
        SELECT playbook_id, name, domain, version, supersedes,
               status_cache, spec, confidence,
               uses, successes, failures, created_at, updated_at
        FROM playbooks
        WHERE playbook_id = %s
        """,
        (str(playbook_id),),
    )
    if row is None:
        raise HTTPException(404, f"playbook {playbook_id} not found")

    return await _load_playbook(row)


# ---------------------------------------------------------------------------
# Freshness, lineage and re-learn
# ---------------------------------------------------------------------------


class FreshnessResponse(BaseModel):
    playbook_id: UUID
    is_fresh: bool
    stale_deps: list[dict] = Field(default_factory=list)


class EpisodeSummary(BaseModel):
    episode_id: UUID
    task_id: UUID
    task_input: str
    outcome: str
    mode: str
    steps: int
    latency_ms: int
    tokens: int
    created_at: datetime | None = None


class RelearnResponse(BaseModel):
    playbook_id: UUID
    queued: bool
    message: str
    # `queued: false` covers two opposite situations — one where a re-learn is
    # already under way and one where there is nothing left to do — and a
    # caller cannot tell them apart from the prose. The UI reports the first as
    # progress and the second as finished, so it needs the distinction.
    state: str = "queued"


# Re-learning is an operator action: it re-derives a runbook under current
# policy without changing policy itself.
require_operator = require(OPERATOR)


@router.get("/playbooks/{playbook_id}/freshness", response_model=FreshnessResponse)
async def playbook_freshness(playbook_id: UUID):
    """The authoritative provenance check, exposed for the UI and the demo.

    `status_cache` on the list endpoint is an async convenience that can lag;
    this is the join that actually decides whether the playbook may execute.
    """
    result = await check_freshness(playbook_id)
    return FreshnessResponse(
        playbook_id=playbook_id,
        is_fresh=result.kind == "fresh",
        stale_deps=[d.model_dump() for d in getattr(result, "stale_deps", [])],
    )


@router.get("/playbooks/{playbook_id}/episodes", response_model=list[EpisodeSummary])
async def playbook_episodes(playbook_id: UUID, limit: int = 20):
    """Runs that executed this playbook — backs the 'View episodes' drawer."""
    if _stub_mode():
        return []

    from app.db import q

    rows = await q(
        """
        SELECT e.episode_id, e.task_id, t.input AS task_input, e.outcome, e.mode,
               e.steps, e.latency_ms, e.tokens, e.created_at
        FROM episodes e
        JOIN tasks t ON t.task_id = e.task_id
        WHERE t.playbook_id = %s
        ORDER BY e.created_at DESC
        LIMIT %s
        """,
        (str(playbook_id), limit),
    )
    return [EpisodeSummary(**r) for r in rows]


@router.post("/playbooks/{playbook_id}/relearn", response_model=RelearnResponse)
async def relearn_playbook(playbook_id: UUID, principal: Principal = Depends(require_operator)):
    """Queue a re-learn: explore under current rules, compile as v2.

    Enqueues an outbox row rather than running inline — the worker owns this
    job, and going through the outbox keeps the manual path and the automatic
    cascade path identical (and idempotent).
    """
    if _stub_mode():
        return RelearnResponse(
            playbook_id=playbook_id,
            queued=True,
            message="Stub mode — not queued.",
            state="queued",
        )

    from app.db import one, q

    row = await one(
        "SELECT status_cache FROM playbooks WHERE playbook_id = %s", (str(playbook_id),)
    )
    if row is None:
        raise HTTPException(404, f"playbook {playbook_id} not found")

    superseded = await one(
        "SELECT playbook_id FROM playbooks WHERE supersedes = %s", (str(playbook_id),)
    )
    if superseded is not None:
        return RelearnResponse(
            playbook_id=playbook_id,
            queued=False,
            message="Already superseded by a newer version.",
            state="superseded",
        )

    pending = await one(
        """
        SELECT event_id FROM outbox
        WHERE kind = 'relearn'
          AND processed_at IS NULL
          AND payload ->> 'playbook_id' = %s
        """,
        (str(playbook_id),),
    )
    if pending is not None:
        return RelearnResponse(
            playbook_id=playbook_id,
            queued=False,
            message="A re-learn is already under way for this runbook.",
            state="in_flight",
        )

    await q(
        "INSERT INTO outbox (kind, payload) VALUES ('relearn', %s)",
        (json.dumps({"playbook_id": str(playbook_id)}),),
    )
    log.info("relearn queued for playbook %s", playbook_id)
    return RelearnResponse(
        playbook_id=playbook_id, queued=True, message="Re-learn queued.", state="queued"
    )
