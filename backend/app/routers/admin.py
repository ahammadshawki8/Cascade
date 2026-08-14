"""Admin router — demo reset and operational checks.

OWNER: Ashfaq (Track A). Reset internals: Shawki (Track B).

Endpoints:
    POST /api/admin/reset          — restore the clean v1 demo world
    GET  /api/admin/verify-index   — EXPLAIN proof that pb_embed_idx is used
    GET  /api/admin/smoke          — Bedrock reachability per model
    POST /api/mock/incidents       — author a new incident to run the agent on
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
    "outbox",
    "insights",
    "mock_action_log",
    "mock_incidents",
    "mock_services",
)

# Never cleared. These are the things a user brought with them, and a button
# labelled "reset the demo" that silently deleted the Slack connection someone
# had just wired up, or the API key their editor is holding, would be a bug
# whatever the tooltip said.
#
#   connections, api_keys      configuration, not demo state
#   connector_calls            the idempotency ledger; losing it would let a
#                              replayed step page someone a second time
#   agent_activity, audit_log  the record of what was done, which survives the
#                              world being restored (spec 3.4)
_PRESERVED_TABLES = (
    "connections",
    "connector_calls",
    "api_keys",
    "agent_activity",
    "audit_log",
)

# Procedures the user brought or wrote. Compiled and merged ones are learned
# state and go back in the box; these do not.
_PRESERVED_ORIGINS = ("imported", "authored")


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
    """Restore the sample world. Keep everything the user made.

    The demo and the product live in one database on purpose — there is no
    second copy of the engine for "real" data, and pretending otherwise with a
    workspace switcher would imply an isolation guarantee this does not have.
    What makes them coexist is that this button is scoped: it restores the
    sample and touches nothing else.

    Everything happens in one transaction so a failed reset cannot leave the
    demo half-wiped — an earlier implementation replayed the seed's INSERTs
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
    kept_procedures = 0
    kept_rules = 0

    async with pool().connection() as conn:
        await conn.set_autocommit(False)
        try:
            async with conn.cursor() as cur:
                # A seeded rule is one whose first version the seed wrote. Read
                # rather than hardcoded so this cannot drift from 002_seed.sql.
                await cur.execute(
                    "SELECT rule_key FROM rules WHERE version = 1 AND changed_by = 'system'"
                )
                sample_keys = [r["rule_key"] for r in await cur.fetchall()]

                # Provenance of the procedures that are about to survive. Their
                # edges have to be dropped before the rules they point at can
                # be deleted, and rebuilt afterwards against the restored head.
                # Re-pinning is the semantically right answer, not a repair: if
                # policy has gone back to v1, a surviving procedure cites v1.
                await cur.execute(
                    """
                    SELECT d.playbook_id, d.rule_key, d.citation, d.extraction_confidence
                    FROM playbook_deps d
                    JOIN playbooks p ON p.playbook_id = d.playbook_id
                    WHERE p.origin = ANY(%s)
                    """,
                    (list(_PRESERVED_ORIGINS),),
                )
                surviving_deps = [dict(r) for r in await cur.fetchall()]

                for table in _CLEAR_ORDER:
                    await cur.execute(f"DELETE FROM {table} WHERE true")

                await cur.execute("DELETE FROM playbook_deps WHERE true")
                await cur.execute(
                    "DELETE FROM playbooks WHERE origin != ALL(%s)",
                    (list(_PRESERVED_ORIGINS),),
                )
                await cur.execute(
                    "SELECT count(*)::INT AS n FROM playbooks",
                )
                kept_procedures = (await cur.fetchone())["n"]

                # User-authored rules are not sample data and are left alone.
                await cur.execute(
                    "DELETE FROM rules WHERE rule_key = ANY(%s)", (sample_keys,)
                )
                await cur.execute("SELECT count(*)::INT AS n FROM rules")
                kept_rules = (await cur.fetchone())["n"]

                # The seed file carries its own BEGIN/COMMIT; strip them so it
                # nests inside this transaction instead of ending it early.
                await cur.execute(_strip_txn(seed))

                # Re-pin the survivors to whatever is now head. A dep whose rule
                # no longer exists at all is dropped rather than resurrected.
                for dep in surviving_deps:
                    await cur.execute(
                        "SELECT version FROM rules WHERE rule_key = %s AND valid_to IS NULL",
                        (dep["rule_key"],),
                    )
                    head = await cur.fetchone()
                    if head is None:
                        continue
                    await cur.execute(
                        """
                        INSERT INTO playbook_deps (playbook_id, rule_key, rule_version,
                                                   citation, extraction_confidence)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            str(dep["playbook_id"]),
                            dep["rule_key"],
                            head["version"],
                            dep["citation"],
                            dep["extraction_confidence"],
                        ),
                    )

                # audit_log deliberately survives a reset (spec §3.4), but
                # /api/metrics derives retrieval hit-rate from audit events.
                # This marker is the boundary those counts start from, so a
                # reset yields a clean hit-rate without erasing the history.
                await cur.execute(
                    "INSERT INTO audit_log (kind, actor, details) "
                    "VALUES ('world.reset', %s, %s)",
                    (
                        principal.identity,
                        json.dumps(
                            {
                                "kept_procedures": kept_procedures,
                                "kept_rules": kept_rules,
                            }
                        ),
                    ),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.set_autocommit(True)

    log.info(
        "world reset — sample restored, kept %d procedure(s) and %d user rule(s)",
        kept_procedures,
        kept_rules,
    )
    message = "Sample world restored: 4 rules, 6 services, 12 incidents."
    if kept_procedures or kept_rules:
        parts = []
        if kept_procedures:
            parts.append(
                f"{kept_procedures} imported procedure"
                + ("s" if kept_procedures != 1 else "")
            )
        if kept_rules:
            parts.append(f"{kept_rules} rule" + ("s" if kept_rules != 1 else "") + " you wrote")
        message += " Kept " + " and ".join(parts) + ", plus your connections and keys."

    return {
        "status": "ok",
        "message": message,
        "kept_procedures": kept_procedures,
        "kept_rules": kept_rules,
        "preserved": list(_PRESERVED_TABLES),
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


# ---------------------------------------------------------------------------
# Author your own incident
# ---------------------------------------------------------------------------
# The seeded world (INC-1001..1012) covers the decision space, but a reviewer
# who can only replay canned ids has no way to tell a learning agent from a
# scripted one. This lets anyone author a fresh incident and watch the same
# machinery decide on input it has never seen.
#
# Deliberately unauthenticated, matching POST /api/tasks: submitting work is
# public in this demo, and this is the input side of exactly that.

_KINDS = ("bad_deploy", "error_spike", "resource_exhaustion")
_SEVERITIES = ("P1", "P2", "P3")


class NewIncident(BaseModel):
    kind: str = Field(
        default="bad_deploy",
        description=f"one of {_KINDS}",
    )
    severity: str = Field(default="P2", description=f"one of {_SEVERITIES}")
    service_name: str = Field(default="svc-custom", max_length=64)
    service_tier: int = Field(default=2, ge=1, le=3, description="1 = most critical")
    deploy_age_hours: float = Field(
        default=2.0,
        ge=0,
        description=(
            "How long ago the service last deployed. This is the field the "
            "rollback-window policy is evaluated against, so it decides "
            "whether automatic rollback is permitted."
        ),
    )
    error_rate: float = Field(default=0.05, ge=0, le=1)
    cpu_usage: float = Field(default=0.4, ge=0, le=1)


@router.get("/mock/incidents")
async def list_incidents():
    """The incident inbox.

    Carries the policy verdict for each incident alongside its raw fields, so
    the UI can show *why* two otherwise identical incidents will be treated
    differently. That comparison is the thing a first-time viewer has to
    understand, and making them infer it from a raw timestamp does not work.

    Read-only and unauthenticated, matching the rest of the incident surface.
    """
    if _stub_mode():
        return {"incidents": []}

    from app.db import q

    rows = await q(
        """
        SELECT incident_id, kind, severity, service_name, service_tier, state,
               error_rate, cpu_usage,
               EXTRACT(EPOCH FROM (now() - deploy_timestamp)) / 3600
                   AS deploy_age_hours
        FROM mock_incidents
        ORDER BY incident_id
        """
    )

    rule_rows = await q(
        "SELECT rule_key, params FROM rules r WHERE version = "
        "(SELECT max(version) FROM rules WHERE rule_key = r.rule_key)"
    )
    params = {r["rule_key"]: (r["params"] or {}) for r in rule_rows}
    min_tier = int(params.get("incident.auto_remediate_tier", {}).get("min_tier", 2))
    window_h = float(params.get("incident.rollback_window", {}).get("hours", 24))

    incidents = []
    for row in rows:
        age = row["deploy_age_hours"]
        age = float(age) if age is not None else None
        # None, not False, when the rule does not apply: an error spike has no
        # deploy to roll back, and rendering that as "outside the window" would
        # invent a refusal that never happens.
        within_window = None if age is None else age <= window_h
        incidents.append(
            {
                **{k: v for k, v in row.items() if k != "deploy_age_hours"},
                "deploy_age_hours": age,
                "tier_allowed": row["service_tier"] >= min_tier,
                "within_window": within_window,
            }
        )

    return {
        "incidents": incidents,
        "policy": {"min_tier": min_tier, "rollback_window_hours": window_h},
    }


@router.post("/mock/incidents", status_code=201)
async def create_incident(body: NewIncident):
    """Author an incident, then run the agent on it.

    Returns the generated id. Submit it exactly like a seeded one:
    POST /api/tasks {"input": "Remediate <incident_id>"}
    """
    from app.db import one, q

    if body.kind not in _KINDS:
        raise HTTPException(422, f"kind must be one of {_KINDS}")
    if body.severity not in _SEVERITIES:
        raise HTTPException(422, f"severity must be one of {_SEVERITIES}")

    # Keep custom ids in their own range so they never collide with the seed
    # and survive a demo reset being distinguishable from it.
    row = await one(
        "SELECT count(*) AS n FROM mock_incidents WHERE incident_id LIKE 'INC-9%'"
    )
    incident_id = f"INC-9{(int(row['n']) if row else 0) + 1:03d}"

    # The service must exist first: mock_incidents.service_name carries a
    # foreign key into mock_services, so inserting the incident first aborts.
    await q(
        """
        INSERT INTO mock_services (service_name, tier, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (service_name) DO NOTHING
        """,
        (body.service_name, body.service_tier, "authored via /api/mock/incidents"),
    )

    await q(
        """
        INSERT INTO mock_incidents
            (incident_id, kind, severity, service_name, service_tier,
             deploy_timestamp, state, error_rate, cpu_usage)
        VALUES (%s, %s, %s, %s, %s, now() - (%s || ' hours')::INTERVAL,
                'open', %s, %s)
        """,
        (
            incident_id,
            body.kind,
            body.severity,
            body.service_name,
            body.service_tier,
            str(body.deploy_age_hours),
            body.error_rate,
            body.cpu_usage,
        ),
    )

    log.info(
        "authored incident %s: %s %s on %s (tier %d, deploy %.1fh ago)",
        incident_id, body.severity, body.kind, body.service_name,
        body.service_tier, body.deploy_age_hours,
    )
    return {
        "incident_id": incident_id,
        "submit_with": {"input": f"Remediate {incident_id}"},
        "expect": await _explain_expectation(body),
    }


async def _explain_expectation(body: NewIncident) -> str:
    """State up front what policy should decide, so the run is falsifiable.

    A reviewer who is told the expected outcome before pressing go can tell the
    difference between an agent reasoning about policy and a demo replaying a
    script. That only works if the prediction is right, so two rules apply.

    It is read from the live rules, never hardcoded: the demo exists to have
    its policy changed, and a prediction quoting the seeded 24h window would
    start lying the moment a reviewer moved it.

    And it predicts which *action* policy forbids, not the final outcome.
    Refusing a rollback does not oblige the agent to escalate: restarting is a
    permitted alternative, and the agent does reach for it. An earlier version
    of this promised escalation, which made a correct run look like a failure.
    """
    from app.db import q

    rows = await q(
        "SELECT rule_key, params FROM rules r WHERE version = "
        "(SELECT max(version) FROM rules WHERE rule_key = r.rule_key)"
    )
    params = {r["rule_key"]: (r["params"] or {}) for r in rows}
    min_tier = params.get("incident.auto_remediate_tier", {}).get("min_tier", 2)
    window_h = params.get("incident.rollback_window", {}).get("hours", 24)

    if body.service_tier < int(min_tier):
        return (
            f"tier {body.service_tier} is above what auto_remediate_tier permits "
            f"(tier {min_tier} or lower), so no automated remediation should be "
            "applied at all: expect an ESCALATION to a human"
        )
    if body.kind == "bad_deploy" and body.deploy_age_hours > float(window_h):
        return (
            f"the deploy is {body.deploy_age_hours:g}h old, past the {window_h}h "
            "rollback_window, so ROLLBACK should be refused. The agent may still "
            "remediate another permitted way, such as a restart, or escalate. "
            "What it must not do is roll back"
        )
    if body.kind == "bad_deploy":
        return (
            f"the deploy is {body.deploy_age_hours:g}h old, inside the {window_h}h "
            f"rollback_window, on a tier policy allows, so expect a ROLLBACK"
        )
    return (
        f"tier {body.service_tier} is within what policy permits, so expect "
        "automated remediation appropriate to the incident kind, followed by an "
        "on-call notification"
    )
