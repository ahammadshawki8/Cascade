"""Rules router — policy management with cascade transaction.

OWNER: Ashfaq (Track A).

Endpoints:
    GET  /api/rules                  — List all head (current) rules
    GET  /api/rules/{rule_key}       — Single rule with version history
    POST /api/rules/{rule_key}       — Change rule (cascade transaction)
    POST /api/rules/{rule_key}/dry-run — Simulate impact without committing
    GET  /api/impact                 — Impact preview (deterministic SQL)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import ADMIN, Principal, require
from app.config import settings
from app.core.contracts import change_rule, simulate_rule_change
from app.core.models import ImpactResult, Rule

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    # settings, not os.environ — see the note in routers/tasks.py.
    return settings.cascade_stub_mode


# ---------------------------------------------------------------------------
# Stub data
# ---------------------------------------------------------------------------

_STUB_RULES = [
    Rule(
        rule_key="incident.auto_remediate_tier",
        version=1,
        domain="incidents",
        body='Automated remediation (restart, rollback, scale_up) is permitted only for services of tier {min_tier} or a higher tier number.',
        params={"min_tier": 2},
        changed_by="system",
    ),
    Rule(
        rule_key="incident.rollback_window",
        version=1,
        domain="incidents",
        body='Automatic rollback is permitted only within {hours} hours of the service\'s last deploy.',
        params={"hours": 24},
        changed_by="system",
    ),
    Rule(
        rule_key="incident.notify",
        version=1,
        domain="incidents",
        body='The on-call channel must be notified after any remediation decision.',
        params={},
        changed_by="system",
    ),
    Rule(
        rule_key="incident.single_action",
        version=1,
        domain="incidents",
        body='At most one automated remediation action may be applied to an incident.',
        params={},
        changed_by="system",
    ),
]


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


require_admin = require(ADMIN)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChangeRuleRequest(BaseModel):
    body: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class RuleView(Rule):
    """A rule, plus how it decides.

    Extends the frozen Day-0 `Rule` rather than editing it: that model is the
    Track A/B interface and the assertion suite compares its shape exactly.
    Subclassing adds fields for this API without touching the contract.
    """

    predicate: dict[str, Any] | None = None
    enforcement: str = "advisory"
    # True for the rules the demo world seeds. The console shows these with a
    # "Sample" chip so a judge can always tell what came with the product from
    # what they wrote, without the two living in separate places.
    sample: bool = False


class RuleWithHistory(BaseModel):
    current: RuleView
    history: list[Rule] = Field(default_factory=list)


class RulesListResponse(BaseModel):
    rules: list[RuleView]
    count: int


class CreateRuleRequest(BaseModel):
    rule_key: str = Field(..., min_length=3, max_length=100)
    domain: str = "incident"
    body: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    predicate: dict[str, Any] | None = None
    enforcement: str = "advisory"


class ChangeDefinitionRequest(BaseModel):
    body: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    predicate: dict[str, Any] | None = None
    enforcement: str = "advisory"


class PreviewRequest(BaseModel):
    """Try a predicate against the world without saving it."""

    predicate: dict[str, Any] | None = None
    params: dict[str, Any] = Field(default_factory=dict)


ENFORCEMENT_MODES = ("advisory", "shadow", "enforcing")


class ImpactPreviewResponse(BaseModel):
    rule_key: str
    affected_playbook_ids: list[str]
    affected_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=RulesListResponse)
async def list_rules():
    """List all head (current version) rules."""
    if _stub_mode():
        stub = [RuleView(**r.model_dump(), sample=True) for r in _STUB_RULES]
        return RulesListResponse(rules=stub, count=len(stub))

    from app.db import q
    rows = await q(
        """
        SELECT rule_key, version, domain, body, params,
               valid_from, valid_to, changed_by, predicate, enforcement
        FROM rules
        WHERE valid_to IS NULL
        ORDER BY domain, rule_key
        """
    )
    # A seeded rule is one whose *first* version was written by the seed. Read
    # rather than hardcoded, so the list cannot drift from 002_seed.sql; and
    # taken from v1 specifically, because a judge editing a sample rule sets
    # changed_by on the new version and it is still a sample rule.
    seeded = await q(
        "SELECT rule_key FROM rules WHERE version = 1 AND changed_by = 'system'"
    )
    sample_keys = {r["rule_key"] for r in seeded}

    rules = [
        RuleView(
            **{k: v for k, v in r.items() if k not in ("predicate", "enforcement")},
            predicate=r.get("predicate"),
            enforcement=r.get("enforcement") or "advisory",
            sample=r["rule_key"] in sample_keys,
        )
        for r in rows
    ]
    return RulesListResponse(rules=rules, count=len(rules))


@router.get("/policy/facts")
async def policy_facts(domain: str = "incident"):
    """The fields a rule in this domain may reason about.

    Backs the rule builder. Offering a dropdown of real field names is the
    difference between writing a predicate and guessing at one, and the
    validator rejects anything outside this list anyway.
    """
    from app.core.policy.facts import DOMAIN_FACTS
    from app.core.policy.predicates import OP_LABELS

    fields = DOMAIN_FACTS.get(domain, [])
    if not _stub_mode():
        from app import db as db_module

        try:
            rows = await db_module.q(
                "SELECT field, kind, label, choices FROM domain_facts "
                "WHERE domain = %s ORDER BY field",
                (domain,),
            )
            if rows:
                fields = [dict(r) for r in rows]
        except Exception as exc:
            log.warning("domain_facts unavailable, using built-in list: %s", exc)

    return {
        "domain": domain,
        "fields": fields,
        "operators": [{"op": op, "label": label} for op, label in OP_LABELS.items()],
        "enforcement_modes": [
            {
                "mode": "advisory",
                "label": "Advisory",
                "hint": "Cited and versioned. Never blocks anything.",
            },
            {
                "mode": "shadow",
                "label": "Shadow",
                "hint": "Evaluated and recorded, but does not block. Use this to "
                        "see what a rule would have refused before it refuses "
                        "anything.",
            },
            {
                "mode": "enforcing",
                "label": "Enforcing",
                "hint": "Blocks the action when it fails.",
            },
        ],
    }


@router.post("/rules", status_code=201)
async def create_rule_endpoint(
    body: CreateRuleRequest, principal: Principal = Depends(require_admin)
):
    """Add a rule that did not exist before.

    Until migration 006 there was no way to do this, and it would not have meant
    anything if there had been: the eligibility check named three rule keys in
    Python, so an invented rule was stored, versioned and cascaded while being
    enforced by nothing.
    """
    from app.core.contracts import create_rule
    from app.core.policy import PredicateError, validate_predicate

    if body.enforcement not in ENFORCEMENT_MODES:
        raise HTTPException(422, f"enforcement must be one of {ENFORCEMENT_MODES}")
    if body.enforcement != "advisory" and not body.predicate:
        raise HTTPException(
            422,
            "A rule that enforces or shadows needs a predicate. Without one there "
            "is nothing for it to decide.",
        )

    known = None
    if not _stub_mode():
        from app import db as db_module
        from app.core.policy.facts import known_fields

        known = await known_fields(db_module, body.domain)

    try:
        validate_predicate(body.predicate, known)
    except PredicateError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        result = await create_rule(
            rule_key=body.rule_key,
            domain=body.domain,
            body=body.body,
            params=body.params,
            predicate=body.predicate,
            enforcement=body.enforcement,
            actor=principal.identity,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    log.info("rule created: %s by %s", body.rule_key, principal.identity)
    return result


@router.post("/policy/preview")
async def preview_predicate(body: PreviewRequest):
    """Run a candidate predicate over the open incidents. Saves nothing.

    A rule is abstract until you see what it does to the world in front of you.
    This is the same evaluator the engine uses, so the preview cannot flatter
    the rule relative to what it will actually do.
    """
    if _stub_mode():
        return {"evaluated": 0, "refused": [], "allowed": []}

    from app import db as db_module
    from app.core.policy import PredicateError, build_incident_facts, evaluate
    from app.core.policy.facts import known_fields
    from app.core.tools import ACTION_FOR_KIND
    from app.db import q

    try:
        from app.core.policy import validate_predicate

        validate_predicate(body.predicate, await known_fields(db_module))
    except PredicateError as exc:
        raise HTTPException(422, str(exc)) from exc

    incidents = await q(
        """
        SELECT incident_id, kind, severity, service_name, service_tier,
               deploy_timestamp, state, error_rate, cpu_usage
        FROM mock_incidents
        ORDER BY incident_id
        """
    )

    refused, allowed, skipped = [], [], []
    for incident in incidents:
        action = ACTION_FOR_KIND.get(incident["kind"])
        facts = build_incident_facts(incident, action=action, prior_actions=0)
        verdict = evaluate(body.predicate, facts, body.params)
        entry = {
            "incident_id": incident["incident_id"],
            "kind": incident["kind"],
            "service_tier": incident["service_tier"],
            "action": action,
            "reason": verdict.reason,
        }
        if not verdict.applies:
            skipped.append(entry)
        elif verdict.passed:
            allowed.append(entry)
        else:
            refused.append(entry)

    return {
        "evaluated": len(incidents),
        "refused": refused,
        "allowed": allowed,
        "not_applicable": skipped,
        "summary": (
            f"Of {len(incidents)} incidents, this rule would refuse "
            f"{len(refused)}, allow {len(allowed)}, and have nothing to say "
            f"about {len(skipped)}."
        ),
    }


@router.get("/rules/{rule_key}", response_model=RuleWithHistory)
async def get_rule(rule_key: str):
    """Get the current rule plus its full version history."""
    if _stub_mode():
        for r in _STUB_RULES:
            if r.rule_key == rule_key:
                return RuleWithHistory(current=r, history=[r])
        raise HTTPException(404, f"rule {rule_key!r} not found")

    from app.db import one, q
    current_row = await one(
        """
        SELECT rule_key, version, domain, body, params,
               valid_from, valid_to, changed_by
        FROM rules
        WHERE rule_key = %s AND valid_to IS NULL
        """,
        (rule_key,),
    )
    if current_row is None:
        raise HTTPException(404, f"rule {rule_key!r} not found")

    history_rows = await q(
        """
        SELECT rule_key, version, domain, body, params,
               valid_from, valid_to, changed_by
        FROM rules
        WHERE rule_key = %s
        ORDER BY version DESC
        """,
        (rule_key,),
    )

    return RuleWithHistory(
        current=RuleView(
            **{
                k: v
                for k, v in current_row.items()
                if k not in ("predicate", "enforcement")
            },
            predicate=current_row.get("predicate"),
            enforcement=current_row.get("enforcement") or "advisory",
        ),
        history=[Rule(**{k: v for k, v in r.items()
                         if k not in ("predicate", "enforcement")})
                 for r in history_rows],
    )


@router.post("/rules/{rule_key}/definition", response_model=ImpactResult)
async def update_rule_definition(
    rule_key: str,
    body: ChangeDefinitionRequest,
    principal: Principal = Depends(require_admin),
):
    """Change what a rule says *and* how it decides, through the same cascade.

    Changing a predicate is a policy change in the fullest sense: a procedure
    compiled while the old one was in force may now be relying on a rule that
    no longer means what it did. Routing it anywhere other than the cascade
    would leave a class of policy change that silently kept stale procedures
    looking fresh.
    """
    from app.core.contracts import change_rule_definition
    from app.core.policy import PredicateError, validate_predicate

    if body.enforcement not in ENFORCEMENT_MODES:
        raise HTTPException(422, f"enforcement must be one of {ENFORCEMENT_MODES}")
    if body.enforcement != "advisory" and not body.predicate:
        raise HTTPException(
            422, "A rule that enforces or shadows needs a predicate."
        )

    known = None
    if not _stub_mode():
        from app import db as db_module
        from app.core.policy.facts import known_fields

        existing = await db_module.q(
            "SELECT domain FROM rules WHERE rule_key = %s AND valid_to IS NULL",
            (rule_key,),
        )
        if not existing:
            raise HTTPException(404, f"rule {rule_key!r} not found")
        known = await known_fields(db_module, existing[0]["domain"])

    try:
        validate_predicate(body.predicate, known)
    except PredicateError as exc:
        raise HTTPException(422, str(exc)) from exc

    result = await change_rule_definition(
        rule_key=rule_key,
        new_body=body.body,
        new_params=body.params,
        new_predicate=body.predicate,
        new_enforcement=body.enforcement,
        actor=principal.identity,
    )
    log.info(
        "rule definition changed: %s v%s->v%s by %s",
        rule_key, result.old_version, result.new_version, principal.identity,
    )
    return result


@router.post("/rules/{rule_key}", response_model=ImpactResult)
async def update_rule(
    rule_key: str,
    body: ChangeRuleRequest,
    principal: Principal = Depends(require_admin),
):
    """Change a rule — triggers the O(1) cascade transaction (D1 + D5)."""
    if not _stub_mode():
        from app.db import one
        existing = await one(
            "SELECT rule_key FROM rules WHERE rule_key = %s AND valid_to IS NULL",
            (rule_key,),
        )
        if existing is None:
            raise HTTPException(404, f"rule {rule_key!r} not found")

    # The real identity, not a shared literal — audit_log.actor is what answers
    # "who changed this policy", and it survives a demo reset by design.
    result = await change_rule(
        rule_key=rule_key,
        new_body=body.body,
        new_params=body.params,
        actor=principal.identity,
    )

    log.info(
        "rule changed: %s v%s→v%s impacted=%d playbooks",
        rule_key,
        result.old_version,
        result.new_version,
        len(result.impacted_playbooks),
    )
    return result


@router.post("/rules/{rule_key}/dry-run", response_model=ImpactResult)
async def dry_run_rule(rule_key: str, body: ChangeRuleRequest):
    """Simulate a rule change without committing."""
    result = await simulate_rule_change(
        rule_key=rule_key,
        new_body=body.body,
        new_params=body.params,
    )
    return result


@router.get("/impact", response_model=ImpactPreviewResponse)
async def impact_preview(rule_key: str):
    """Deterministic SQL impact query — no LLM."""
    if _stub_mode():
        return ImpactPreviewResponse(
            rule_key=rule_key,
            affected_playbook_ids=["00000000-0000-0000-0000-000000000001"],
            affected_count=1,
        )

    from app.db import one, q
    current = await one(
        "SELECT version FROM rules WHERE rule_key = %s AND valid_to IS NULL",
        (rule_key,),
    )
    if current is None:
        raise HTTPException(404, f"rule {rule_key!r} not found")

    rows = await q(
        """
        SELECT DISTINCT d.playbook_id::TEXT as playbook_id
        FROM playbook_deps d
        JOIN playbooks p ON p.playbook_id = d.playbook_id
        WHERE d.rule_key = %s
          AND p.status_cache IN ('active', 'candidate', 'suspect')
        """,
        (rule_key,),
    )

    ids = [r["playbook_id"] for r in rows]
    return ImpactPreviewResponse(
        rule_key=rule_key,
        affected_playbook_ids=ids,
        affected_count=len(ids),
    )
