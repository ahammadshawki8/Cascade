"""
CASCADE Track B - Interface Contracts
FROZEN AFTER DAY 0 - Signatures cannot change without contract PR

Track A imports ONLY this file. All functions have stub bodies when CASCADE_STUB_MODE=true.
"""

import os
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from .models import (
    ApprovalStatus,
    CopilotAnswer,
    FreshnessResult,
    ImpactResult,
    Insight,
    InsightKind,
    PlaybookCandidate,
    StaleRule,
)

# Stub mode toggle
STUB = os.getenv("CASCADE_STUB_MODE", "true").lower() == "true"


# ============================================================================
# MVP Functions (Week 1-3)
# ============================================================================

async def retrieve(task_text: str) -> Optional[PlaybookCandidate]:
    """
    Phase 1: Vector retrieval for playbook candidates.
    Returns best match or None if no good candidates.
    """
    if STUB:
        return PlaybookCandidate(
            playbook_id=UUID("00000000-0000-0000-0000-000000000001"),
            name="Rollback bad deploy",
            version=1,
            confidence=0.72,
            distance=0.41,
            status_cache="active",
        )
    raise NotImplementedError("retrieve() not yet implemented")


async def check_freshness(playbook_id: UUID) -> FreshnessResult:
    """
    Point-of-use freshness check via provenance join.
    NEVER returns a bool - always returns FreshnessResult.
    """
    if STUB:
        return FreshnessResult(is_fresh=True, stale_rules=[])
    raise NotImplementedError("check_freshness() not yet implemented")


async def run_task(task_id: UUID) -> None:
    """
    Main executor entry point. Runs explore or guided mode.
    Updates task status, streams SSE events, writes episodes.
    """
    if STUB:
        # Stub: just mark task as succeeded
        print(f"[STUB] Task {task_id} would run here")
        return
    raise NotImplementedError("run_task() not yet implemented")


async def change_rule(
    rule_key: str,
    new_body: str,
    new_params: dict,
    actor: str
) -> ImpactResult:
    """
    O(1) cascade transaction: close old rule, insert new rule.
    Returns impact analysis.
    """
    if STUB:
        return ImpactResult(
            affected_playbooks=[UUID("00000000-0000-0000-0000-000000000001")],
            affected_count=1,
            will_trigger_cascade=True,
        )
    raise NotImplementedError("change_rule() not yet implemented")


async def answer_analytics_question(question: str) -> CopilotAnswer:
    """
    Ops Copilot: synthesize SQL from natural language question.
    Execute read-only with timeout + limit wrapper.
    """
    if STUB:
        return CopilotAnswer(
            sql="SELECT COUNT(*) as total FROM tasks WHERE status = 'succeeded'",
            results=[{"total": 42}],
            row_count=1,
        )
    raise NotImplementedError("answer_analytics_question() not yet implemented")


# ============================================================================
# Extension Functions (Week 4+, after MVP gate)
# ============================================================================

def decide_autonomy(playbook_id: UUID, step_index: int) -> str:
    """
    Autonomy gating: determine if step requires approval.
    Returns: "AUTO_EXECUTE" | "REQUIRES_APPROVAL"
    """
    if STUB:
        return "AUTO_EXECUTE"
    raise NotImplementedError("decide_autonomy() not yet implemented")


async def resolve_approval(
    approval_id: UUID,
    decision: ApprovalStatus,
    resolved_by: str
) -> None:
    """
    Handle approval decision. Resume task if approved.
    """
    if STUB:
        print(f"[STUB] Approval {approval_id} resolved: {decision}")
        return
    raise NotImplementedError("resolve_approval() not yet implemented")


async def generate_postmortem(episode_id: UUID) -> str:
    """
    Generate postmortem analysis from episode trajectory.
    Returns S3 key of generated markdown.
    """
    if STUB:
        return f"postmortems/{episode_id}.md"
    raise NotImplementedError("generate_postmortem() not yet implemented")


async def list_insights(include_dismissed: bool = False) -> list[Insight]:
    """
    List trend detection insights.
    """
    if STUB:
        return [
            Insight(
                insight_id=UUID("00000000-0000-0000-0000-000000000010"),
                kind=InsightKind.THRESHOLD_TREND,
                summary="Rollback window trending toward 4h threshold",
                related_rule_key="incident.rollback_window",
                suggested_params={"rollback_window_hours": 4},
                evidence={"samples": 10, "mean": 4.2},
                created_at=datetime.now(),
                dismissed=False,
            )
        ]
    raise NotImplementedError("list_insights() not yet implemented")


async def dismiss_insight(insight_id: UUID) -> None:
    """
    Dismiss an insight (sets dismissed=true).
    """
    if STUB:
        print(f"[STUB] Insight {insight_id} dismissed")
        return
    raise NotImplementedError("dismiss_insight() not yet implemented")


async def simulate_rule_change(
    rule_key: str,
    new_body: str,
    new_params: dict
) -> ImpactResult:
    """
    Dry-run: show impact without committing change.
    """
    if STUB:
        return ImpactResult(
            affected_playbooks=[UUID("00000000-0000-0000-0000-000000000001")],
            affected_count=1,
            will_trigger_cascade=True,
        )
    raise NotImplementedError("simulate_rule_change() not yet implemented")
