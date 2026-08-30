"""Autonomy gating — human-in-the-loop for irreversible actions (spec D2, §9).

The agent may read anything. It may act on its own only where policy *and*
risk allow. Everything else stops and waits for a person.

Risk is a static property of the tool (`TOOL_RISK` in models.py), not something
the model reasons about — an LLM must never be able to argue its way into
calling `apply_remediation` unsupervised. The gate combines that fixed risk
with the blast radius of the specific target:

    apply_remediation on a tier-1 service      -> REQUIRES_APPROVAL
    apply_remediation from a low-confidence pb -> REQUIRES_APPROVAL
    anything else high-risk under manual policy-> REQUIRES_APPROVAL
    everything else                            -> AUTO_EXECUTE

RESUMPTION
----------
Approving does not splice execution back into a suspended coroutine. The task
is simply re-run, and the earlier steps replay: every side-effecting tool is
idempotent on a deterministic `{task_id}:{step_index}` key, so a replayed
`apply_remediation` returns the original result instead of acting twice, and
read-only tools cost nothing. That property is what makes resume-by-replay
correct rather than merely convenient.

The approved step is recorded in `tasks.scratchpad.approved` as a fingerprint
of (tool, args), so approval authorises *that action*, not "the next thing the
agent decides to do".
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from .models import TOOL_RISK

log = logging.getLogger(__name__)

AUTO_EXECUTE = "AUTO_EXECUTE"
REQUIRES_APPROVAL = "REQUIRES_APPROVAL"

# Services at or below this tier are production-critical: a wrong rollback here
# is a customer-visible outage, so a human confirms even when policy permits.
# This gate is always on — blast radius is what earns a human, not uncertainty.
CRITICAL_TIER = 1

# Optional second gate: make an unproven runbook earn the right to act
# unsupervised. Off by default (0.0).
#
# Turning it on produces a genuine "earn autonomy" progression — a fresh
# playbook starts at 0.30, and each approved success adds 0.15, so it takes
# three supervised runs before it acts alone. That is a compelling property,
# but it also means *every* first reuse of a new runbook stops for a human,
# which is a policy choice a team should make deliberately rather than inherit
# as a default. Set AUTONOMY_MIN_CONFIDENCE=0.6 to enable.
DEFAULT_MIN_CONFIDENCE = 0.0


def fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    """Stable id for one proposed action.

    Args are canonicalised so key order cannot produce two different prints for
    the same action. `idempotency_key` is excluded — it encodes the step index,
    and an approval must survive a replay that lands on the same step.
    """
    payload = {k: v for k, v in sorted(args.items()) if k != "idempotency_key"}
    digest = hashlib.blake2b(
        json.dumps([tool_name, payload], sort_keys=True, default=str).encode(),
        digest_size=12,
    )
    return digest.hexdigest()


def decide_autonomy(
    tool_name: str,
    *,
    incident: dict[str, Any] | None = None,
    playbook_confidence: float | None = None,
) -> tuple[str, str]:
    """Return (decision, reason). Reason is shown to the approver."""
    risk = TOOL_RISK.get(tool_name, "high")

    if risk in ("none", "low"):
        return AUTO_EXECUTE, ""

    incident = incident or {}
    tier = incident.get("service_tier")
    service = incident.get("service_name", "the service")

    if isinstance(tier, int) and tier <= CRITICAL_TIER:
        return (
            REQUIRES_APPROVAL,
            f"{tool_name} targets {service}, a tier-{tier} production-critical "
            "service. Automated remediation here requires sign-off.",
        )

    from app.config import settings

    min_confidence = float(
        getattr(settings, "autonomy_min_confidence", DEFAULT_MIN_CONFIDENCE)
    )
    if (
        min_confidence > 0
        and playbook_confidence is not None
        and playbook_confidence < min_confidence
    ):
        return (
            REQUIRES_APPROVAL,
            f"{tool_name} would run from a runbook with confidence "
            f"{playbook_confidence:.2f}, below the {min_confidence:.2f} bar for "
            "unsupervised irreversible actions.",
        )

    return AUTO_EXECUTE, ""


async def is_pre_approved(task_id: UUID, tool_name: str, args: dict, db) -> bool:
    """Has a human already approved exactly this action for this task?"""
    rows = await db.q(
        "SELECT scratchpad FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    if not rows:
        return False
    scratchpad = rows[0]["scratchpad"] or {}
    if isinstance(scratchpad, str):
        try:
            scratchpad = json.loads(scratchpad)
        except json.JSONDecodeError:
            return False
    return fingerprint(tool_name, args) in set(scratchpad.get("approved") or [])


async def request_approval(
    task_id: UUID,
    tool_name: str,
    args: dict[str, Any],
    step_index: int,
    reason: str,
    db,
    playbook_id: UUID | None = None,
    risk: str = "high",
) -> UUID | None:
    """Record a pending approval and park the task.

    Returns the approval id, or None if an identical request is already
    pending — a replay must not create a second card in the reviewer's queue.
    """
    incident_id = args.get("incident_id")

    existing = await db.q(
        """
        SELECT approval_id FROM approvals
        WHERE task_id = %s AND status = 'pending' AND step_index = %s
        """,
        (str(task_id), step_index),
    )
    if existing:
        return _as_uuid(existing[0]["approval_id"])

    rows = await db.q(
        """
        INSERT INTO approvals (
            task_id, playbook_id, step_index, action, status, reason,
            tool_name, tool_args, risk, incident_id
        ) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s)
        RETURNING approval_id
        """,
        (
            str(task_id),
            str(playbook_id) if playbook_id else None,
            step_index,
            f"{tool_name}({args.get('action', '')})".replace("()", "()"),
            reason,
            tool_name,
            json.dumps(args, default=str),
            risk,
            incident_id,
        ),
    )
    approval_id = _as_uuid(rows[0]["approval_id"])

    await db.q(
        """
        UPDATE tasks SET status = 'awaiting_approval'
        WHERE task_id = %s
        """,
        (str(task_id),),
    )
    log.info(
        "approval %s requested for task %s: %s", approval_id, task_id, tool_name
    )
    return approval_id


async def resolve_approval(
    approval_id: UUID, decision: str, resolved_by: str, db
) -> dict[str, Any]:
    """Approve or reject. Approving records the fingerprint and resumes.

    The whole transition is one transaction: an approval recorded without its
    fingerprint landing in the scratchpad would resume straight back into the
    same gate.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")

    async def txn(cur):
        await cur.execute(
            """
            SELECT task_id, tool_name, tool_args, step_index, status
            FROM approvals WHERE approval_id = %s
            """,
            (str(approval_id),),
        )
        approval = await cur.fetchone()
        if approval is None:
            raise ValueError(f"approval {approval_id} not found")
        if approval["status"] != "pending":
            return {"already_resolved": True, "status": approval["status"]}

        await cur.execute(
            """
            UPDATE approvals
            SET status = %s, resolved_at = now(), resolved_by = %s
            WHERE approval_id = %s
            """,
            (decision, resolved_by, str(approval_id)),
        )

        task_id = approval["task_id"]
        args = approval["tool_args"] or {}
        if isinstance(args, str):
            args = json.loads(args)

        await cur.execute(
            "SELECT scratchpad FROM tasks WHERE task_id = %s", (str(task_id),)
        )
        task_row = await cur.fetchone()
        scratchpad = (task_row or {}).get("scratchpad") or {}
        if isinstance(scratchpad, str):
            scratchpad = json.loads(scratchpad)

        if decision == "approved":
            approved = set(scratchpad.get("approved") or [])
            approved.add(fingerprint(approval["tool_name"], args))
            scratchpad["approved"] = sorted(approved)
            next_status = "queued"
        else:
            scratchpad["rejected_step"] = approval["step_index"]
            next_status = "failed"

        await cur.execute(
            """
            UPDATE tasks
            SET scratchpad = %s, status = %s,
                finished_at = CASE WHEN %s = 'failed' THEN now() ELSE NULL END,
                result = CASE WHEN %s = 'failed' THEN 'escalated' ELSE result END
            WHERE task_id = %s
            """,
            (
                json.dumps(scratchpad, default=str),
                next_status,
                next_status,
                next_status,
                str(task_id),
            ),
        )

        await cur.execute(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, %s, %s)",
            (
                f"approval.{decision}",
                resolved_by,
                json.dumps(
                    {
                        "approval_id": str(approval_id),
                        "task_id": str(task_id),
                        "tool": approval["tool_name"],
                        "step_index": approval["step_index"],
                    }
                ),
            ),
        )

        return {
            "already_resolved": False,
            "task_id": task_id,
            "decision": decision,
            "resume": decision == "approved",
        }

    result = await db.run_txn(txn)
    log.info("approval %s -> %s by %s", approval_id, decision, resolved_by)
    return result


async def list_pending(db, limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.q(
        """
        SELECT a.approval_id, a.task_id, a.playbook_id, a.step_index, a.action,
               a.status, a.reason, a.tool_name, a.tool_args, a.risk,
               a.incident_id, a.requested_at, t.input AS task_input,
               p.name AS playbook_name, p.confidence
        FROM approvals a
        JOIN tasks t ON t.task_id = a.task_id
        LEFT JOIN playbooks p ON p.playbook_id = a.playbook_id
        WHERE a.status = 'pending'
        ORDER BY a.requested_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
