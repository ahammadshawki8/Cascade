"""The contract between the tracks. FROZEN AFTER DAY 0 (WORKFLOW.md §1).

the routers import ONLY this module.

Every function has two bodies: a canned one for CASCADE_STUB_MODE=true, and the
real engine underneath. That toggle is what let the shell and the frontend get
built before the engine existed — and flipping it to false IS the integration
test, so nothing here may change signature to make the wiring easier.

the routers know nothing about `db`, `sse`, or `interrupt_bus`. This
module is where those get injected, so the engine stays independently testable
with a fake db and the routers stay free of engine internals.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .models import (
    ApprovalStatus,
    CopilotAnswer,
    Fresh,
    FreshnessResult,
    ImpactedPlaybook,
    ImpactResult,
    Insight,
    PlaybookCandidate,
    PlaybookSpec,
    RuleCitation,
    Step,
)

log = logging.getLogger(__name__)


def _stub() -> bool:
    """Read at call time, not import time — tests and the routers toggle it."""
    from app.config import settings

    return settings.cascade_stub_mode


def _deps() -> tuple[Any, Any, Any]:
    """(db module, sse broadcaster, interrupt bus).

    Imported lazily so `import contracts` stays free of side effects and the
    engine modules can be unit-tested without a live pool.
    """
    from app import db as db_module
    from app.bus import interrupt_bus, sse

    return db_module, sse, interrupt_bus


# ---------------------------------------------------------------------------
# Stub fixtures — also imported by routers/playbooks.py for its stub library
# ---------------------------------------------------------------------------

_STUB_PLAYBOOK_ID = UUID("00000000-0000-0000-0000-000000000001")

_STUB_SPEC = PlaybookSpec(
    goal="Roll back a bad deploy on an eligible service and notify on-call",
    preconditions=[
        "Incident kind is bad_deploy",
        "Service tier is within the automation floor",
        "Last deploy is inside the rollback window",
    ],
    params={"incident_id": "string"},
    steps=[
        Step(tool="get_incident", args={"incident_id": "{incident_id}"}),
        Step(tool="get_rules", args={"domain": "incident"}),
        Step(
            tool="check_remediation_eligibility",
            args={"incident_id": "{incident_id}", "action": "rollback"},
        ),
        Step(
            tool="apply_remediation",
            args={"incident_id": "{incident_id}", "action": "rollback"},
        ),
        Step(
            tool="notify_oncall",
            args={
                "incident_id": "{incident_id}",
                "message": "Rolled back bad deploy",
            },
        ),
    ],
    rule_citations=[
        RuleCitation(
            rule_key="incident.auto_remediate_tier",
            rule_version=1,
            used_in_step=2,
            why="tier eligibility gate for automated remediation",
        ),
        RuleCitation(
            rule_key="incident.rollback_window",
            rule_version=1,
            used_in_step=2,
            why="verifies the deploy is inside the rollback window",
        ),
    ],
)


# ============================================================================
# MVP functions (Week 1-3)
# ============================================================================


async def retrieve(task_text: str) -> PlaybookCandidate | None:
    """Phase 1+2 vector retrieval. None means nothing reusable was found."""
    if _stub():
        return PlaybookCandidate(
            playbook_id=_STUB_PLAYBOOK_ID,
            name="rollback-bad-deploy",
            version=1,
            confidence=0.72,
            distance=0.41,
            status_cache="active",
            spec=_STUB_SPEC,
        )

    from .retrieval import retrieve as _retrieve

    db, _, _ = _deps()
    return await _retrieve(task_text, db)


async def check_freshness(playbook_id: UUID) -> FreshnessResult:
    """Point-of-use provenance check. Returns Fresh | Stale, never a bool."""
    if _stub():
        return Fresh()

    from .freshness import check_freshness as _check

    db, _, _ = _deps()
    return await _check(playbook_id, db)


async def run_task(task_id: UUID) -> None:
    """Execute a task: retrieve, gate on freshness, then guided or explore."""
    if _stub():
        log.info("[stub] run_task(%s) — no-op", task_id)
        return

    from .executor import run_task as _run

    db, sse, interrupt_bus = _deps()
    await _run(task_id, db, sse_bus=sse, interrupt_bus=interrupt_bus)


async def change_rule(
    rule_key: str, new_body: str, new_params: dict, actor: str
) -> ImpactResult:
    """Version a rule forward via the O(1) cascade transaction (D1)."""
    if _stub():
        return ImpactResult(
            rule_key=rule_key,
            old_version=1,
            new_version=2,
            impacted_playbooks=[
                ImpactedPlaybook(
                    playbook_id=_STUB_PLAYBOOK_ID,
                    name="rollback-bad-deploy",
                    version=1,
                    confidence=0.72,
                    status_cache="active",
                )
            ],
            committed=True,
        )

    from .cascade import change_rule as _change

    db, sse, interrupt_bus = _deps()
    return await _change(
        rule_key=rule_key,
        new_body=new_body,
        new_params=new_params,
        actor=actor,
        db=db,
        interrupt_bus=interrupt_bus,
        sse_bus=sse,
    )


async def change_rule_definition(
    rule_key: str,
    new_body: str,
    new_params: dict,
    new_predicate: dict | None,
    new_enforcement: str,
    actor: str,
) -> ImpactResult:
    """Change what a rule says *and* how it decides, in one cascade.

    Separate from `change_rule` because that signature is frozen: the Day-0
    contract is the interface the routers build against, and widening it would
    break every caller's expectation of what it accepts. This is additive.
    """
    if _stub():
        return await change_rule(rule_key, new_body, new_params, actor)

    from .cascade import change_rule as _change

    db, sse, interrupt_bus = _deps()
    return await _change(
        rule_key=rule_key,
        new_body=new_body,
        new_params=new_params,
        actor=actor,
        db=db,
        interrupt_bus=interrupt_bus,
        sse_bus=sse,
        new_predicate=new_predicate,
        new_enforcement=new_enforcement,
    )


async def create_rule(
    rule_key: str,
    domain: str,
    body: str,
    params: dict,
    predicate: dict | None,
    enforcement: str,
    actor: str,
) -> dict:
    """Add a rule that did not exist before.

    Not a cascade. A new rule invalidates nothing because nothing can cite a
    version that has never existed, so this is a single insert at v1 plus its
    audit row — deliberately not routed through `change_rule`, which would
    report an impact set and an old version that are both fictional.
    """
    if _stub():
        return {"rule_key": rule_key, "version": 1, "created": True}

    import json as _json

    db, _, _ = _deps()

    existing = await db.q(
        "SELECT version FROM rules WHERE rule_key = %s LIMIT 1", (rule_key,)
    )
    if existing:
        raise ValueError(f"rule {rule_key!r} already exists")

    await db.q(
        """
        INSERT INTO rules (rule_key, version, domain, body, params, changed_by,
                           predicate, enforcement)
        VALUES (%s, 1, %s, %s, %s, %s, %s, %s)
        """,
        (
            rule_key,
            domain,
            body,
            _json.dumps(params),
            actor,
            _json.dumps(predicate) if predicate is not None else None,
            enforcement,
        ),
    )
    await db.q(
        "INSERT INTO audit_log (kind, actor, details) VALUES ('rule.create', %s, %s)",
        (actor, _json.dumps({"rule_key": rule_key, "domain": domain,
                             "enforcement": enforcement})),
    )
    return {"rule_key": rule_key, "version": 1, "created": True}


async def answer_analytics_question(question: str) -> CopilotAnswer:
    """Ops Copilot: synthesize read-only SQL, run it, return SQL + rows."""
    if _stub():
        return CopilotAnswer(
            question=question,
            sql="SELECT count(*) AS total FROM tasks WHERE status = 'succeeded'",
            columns=["total"],
            rows=[[42]],
        )

    from .copilot import answer_analytics_question as _answer

    db, _, _ = _deps()
    return await _answer(question, db)


# ============================================================================
# Extension functions (Week 4+, staged behind the MVP gate)
# ============================================================================


def decide_autonomy(playbook_id: UUID, step_index: int) -> str:
    """"AUTO_EXECUTE" | "REQUIRES_APPROVAL" (D2 risk map).

    Frozen signature, kept for the routers. The executor calls the richer
    `autonomy.decide_autonomy(tool_name, incident=..., playbook_confidence=...)`
    directly, because the decision depends on *what* is being done to *which*
    service — not on a step ordinal. Risk stays a static property of the tool:
    the model never gets to argue its way past it.
    """
    return "AUTO_EXECUTE"


async def resolve_approval(
    approval_id: UUID, decision: ApprovalStatus, resolved_by: str
) -> None:
    """Record an approval decision and resume the task if approved."""
    if _stub():
        log.info("[stub] approval %s -> %s", approval_id, decision)
        return

    from .autonomy import resolve_approval as _resolve

    db, _, _ = _deps()
    value = decision.value if hasattr(decision, "value") else str(decision)
    await _resolve(approval_id, value, resolved_by, db)


async def generate_postmortem(episode_id: UUID) -> str:
    """Write a postmortem for an episode. Returns its S3 key (or a marker)."""
    if _stub():
        return f"postmortems/{episode_id}.md"

    from .postmortem import generate_postmortem as _generate

    db, _, _ = _deps()
    return await _generate(episode_id, db)


async def list_insights(include_dismissed: bool = False) -> list[Insight]:
    """Trend-detection insights. Reads the table; population is Week 4."""
    if _stub():
        return [
            Insight(
                insight_id=UUID("00000000-0000-0000-0000-000000000010"),
                kind="threshold_trend",
                summary="Rollback window trending toward the 4h threshold",
                related_rule_key="incident.rollback_window",
                suggested_params={"hours": 4},
                evidence={"samples": 10, "mean": 4.2},
                created_at=datetime.now(UTC),
            )
        ]

    db, _, _ = _deps()
    rows = await db.q(
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
    return [Insight(**row) for row in rows]


async def dismiss_insight(insight_id: UUID) -> None:
    """Hide an insight from the right rail."""
    if _stub():
        log.info("[stub] dismissed insight %s", insight_id)
        return

    db, _, _ = _deps()
    await db.q(
        "UPDATE insights SET dismissed = TRUE WHERE insight_id = %s",
        (str(insight_id),),
    )


async def simulate_rule_change(
    rule_key: str, new_body: str, new_params: dict
) -> ImpactResult:
    """Dry run for the Policy Panel confirm dialog. Writes nothing."""
    if _stub():
        return ImpactResult(
            rule_key=rule_key,
            old_version=1,
            new_version=2,
            impacted_playbooks=[
                ImpactedPlaybook(
                    playbook_id=_STUB_PLAYBOOK_ID,
                    name="rollback-bad-deploy",
                    version=1,
                    confidence=0.72,
                    status_cache="active",
                )
            ],
            committed=False,
        )

    from .cascade import simulate_rule_change as _simulate

    db, _, _ = _deps()
    return await _simulate(rule_key, new_body, new_params, db)
