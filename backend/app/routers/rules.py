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


class RuleWithHistory(BaseModel):
    current: Rule
    history: list[Rule] = Field(default_factory=list)


class RulesListResponse(BaseModel):
    rules: list[Rule]
    count: int


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
        return RulesListResponse(rules=_STUB_RULES, count=len(_STUB_RULES))

    from app.db import q
    rows = await q(
        """
        SELECT rule_key, version, domain, body, params,
               valid_from, valid_to, changed_by
        FROM rules
        WHERE valid_to IS NULL
        ORDER BY domain, rule_key
        """
    )
    rules = [Rule(**r) for r in rows]
    return RulesListResponse(rules=rules, count=len(rules))


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
        current=Rule(**current_row),
        history=[Rule(**r) for r in history_rows],
    )


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
