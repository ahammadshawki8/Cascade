"""Admin router — demo reset and operational checks.

OWNER: Ashfaq (Track A). Reset internals: Shawki (Track B).

Endpoints:
    POST /api/admin/reset          — restore the clean v1 demo world
    GET  /api/admin/verify-index   — EXPLAIN proof that pb_embed_idx is used
    GET  /api/admin/smoke          — Bedrock reachability per model
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.auth import ADMIN, VIEWER, Principal, require
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()

# Delete order matters: children before parents, or the FKs abort the batch.
#   episodes  -> tasks        postmortems -> episodes
#   approvals -> tasks        tasks       -> playbooks
#   playbook_deps -> playbooks, rules
# audit_log is deliberately preserved (spec §3.4) — the demo resets the world,
# not the record of what was done to it.
_CLEAR_ORDER = (
    "postmortems",
    # anti_playbooks references episodes (ON DELETE SET NULL), so it is cleared
    # alongside the rest of the learned state. It was added in migration 003
    # and must not be forgotten here — negative memory surviving a reset would
    # keep warning the planner about incidents that no longer exist.
    "anti_playbooks",
    "episodes",
    "approvals",
    "tasks",
    "playbook_deps",
    "playbooks",
    "outbox",
    "insights",
    "mock_action_log",
    "mock_incidents",
    "mock_services",
    "rules",
)


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


require_admin = require(ADMIN)
require_viewer = require(VIEWER)


def _seed_sql() -> str:
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "migrations" / "002_seed.sql",  # backend/migrations
        Path("migrations/002_seed.sql"),
        Path("backend/migrations/002_seed.sql"),
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise HTTPException(500, "002_seed.sql not found")


@router.post("/admin/reset")
async def reset_world(principal: Principal = Depends(require_admin)):
    """Clear learned state and re-seed the v1 world.

    Everything happens in one transaction so a failed reset cannot leave the
    demo half-wiped — the previous implementation replayed the seed's INSERTs
    without clearing first, which collided on primary keys the moment it had
    ever been run.
    """
    if _stub_mode():
        from app.routers.tasks import _stub_tasks

        _stub_tasks.clear()
        log.info("stub world reset")
        return {"status": "ok", "message": "Stub demo world reset."}

    from app.db import pool

    seed = _seed_sql()

    async with pool().connection() as conn:
        await conn.set_autocommit(False)
        try:
            async with conn.cursor() as cur:
                for table in _CLEAR_ORDER:
                    await cur.execute(f"DELETE FROM {table} WHERE true")
                # The seed file carries its own BEGIN/COMMIT; strip them so it
                # nests inside this transaction instead of ending it early.
                await cur.execute(_strip_txn(seed))
                # audit_log deliberately survives a reset (spec §3.4), but
                # /api/metrics derives retrieval hit-rate from audit events.
                # This marker is the boundary those counts start from, so a
                # reset yields a clean hit-rate without erasing the history.
                await cur.execute(
                    "INSERT INTO audit_log (kind, actor, details) "
                    "VALUES ('world.reset', 'admin', '{}')"
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.set_autocommit(True)

    log.info("world reset — clean v1 state restored")
    return {
        "status": "ok",
        "message": "Demo world reset to v1: 4 rules, 6 services, 12 incidents.",
    }


@router.get("/admin/verify-index")
async def verify_index(principal: Principal = Depends(require_admin)):
    """Day-3 gate: prove the planner actually chooses the vector index.

    "We use distributed vector search" is only true if pb_embed_idx shows up
    in the query plan, so this asserts it rather than trusting the schema.
    """
    if _stub_mode():
        raise HTTPException(400, "verify-index requires CASCADE_STUB_MODE=false")

    from app import db as db_module
    from app.core.retrieval import verify_vector_index

    return await verify_vector_index(db_module)


@router.get("/admin/smoke")
async def smoke(principal: Principal = Depends(require_admin)):
    """Which LLM provider is actually serving requests right now.

    Names the provider rather than returning a bare boolean: "it works" is not
    the same claim as "Bedrock works", and the demo must not blur them.
    """
    from app.core.llm import degraded_reason, llm_smoke_test, llm_status

    result = await llm_smoke_test()
    result["llm_status"] = llm_status()
    result["degraded_reason"] = degraded_reason()
    return result


def _strip_txn(sql: str) -> str:
    lines = [
        line
        for line in sql.splitlines()
        if line.strip().upper().rstrip(";") not in ("BEGIN", "COMMIT")
    ]
    return "\n".join(lines)
