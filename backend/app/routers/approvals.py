"""Approvals router — the human-in-the-loop gate (spec §9, D2).

Endpoints:
    GET  /api/approvals                  — pending queue for the right rail
    POST /api/approvals/{id}/resolve     — approve or reject
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import OPERATOR, Principal, require
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


# Approving is an operator action, not an admin one — the people on call
# should be able to release a gated remediation without holding the keys to
# policy itself.
require_operator = require(OPERATOR)


class PendingApproval(BaseModel):
    approval_id: UUID
    task_id: UUID
    playbook_id: UUID | None = None
    playbook_name: str | None = None
    confidence: float | None = None
    step_index: int
    action: str
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    risk: str = "high"
    incident_id: str | None = None
    reason: str | None = None
    task_input: str
    requested_at: datetime | None = None


class ApprovalListResponse(BaseModel):
    approvals: list[PendingApproval]
    count: int


class ResolveRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")


class ResolveResponse(BaseModel):
    approval_id: UUID
    decision: str
    resumed: bool
    message: str


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals():
    """Everything currently waiting on a human."""
    if _stub_mode():
        return ApprovalListResponse(approvals=[], count=0)

    from app import db as database
    from app.core.autonomy import list_pending

    rows = await list_pending(database)
    approvals = [PendingApproval(**row) for row in rows]
    return ApprovalListResponse(approvals=approvals, count=len(approvals))


@router.post("/approvals/{approval_id}/resolve", response_model=ResolveResponse)
async def resolve(
    approval_id: UUID,
    body: ResolveRequest,
    principal: Principal = Depends(require_operator),
):
    """Approve or reject a gated action.

    Approving re-runs the task rather than resuming a suspended coroutine.
    That is safe because every side-effecting tool is idempotent on a
    deterministic {task_id}:{step_index} key, so replayed steps return their
    original result instead of acting twice.
    """
    if _stub_mode():
        return ResolveResponse(
            approval_id=approval_id,
            decision=body.decision,
            resumed=False,
            message="Stub mode — nothing to resume.",
        )

    from app import db as database
    from app.bus import interrupt_bus, sse
    from app.core.autonomy import resolve_approval

    # Attribute to the authenticated principal. A client-supplied
    # `resolved_by` cannot be trusted for an audit record of who authorised an
    # irreversible action.
    resolver = principal.identity
    try:
        result = await resolve_approval(
            approval_id, body.decision, resolver, database
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    if result.get("already_resolved"):
        return ResolveResponse(
            approval_id=approval_id,
            decision=result["status"],
            resumed=False,
            message=f"Already {result['status']}.",
        )

    await sse.publish(
        "approval.resolved",
        {
            "approval_id": str(approval_id),
            "task_id": str(result["task_id"]),
            "decision": body.decision,
            "resolved_by": resolver,
        },
    )

    if not result.get("resume"):
        await sse.publish(
            f"task.{result['task_id']}.status",
            {
                "task_id": str(result["task_id"]),
                "status": "failed",
                "result": "escalated",
            },
        )
        return ResolveResponse(
            approval_id=approval_id,
            decision=body.decision,
            resumed=False,
            message="Rejected — task escalated to a human.",
        )

    from app.core.executor import run_task

    async def _resume() -> None:
        try:
            await run_task(
                result["task_id"], database, sse_bus=sse, interrupt_bus=interrupt_bus
            )
        except Exception:
            log.exception("resume after approval failed for %s", result["task_id"])

    asyncio.create_task(_resume())

    return ResolveResponse(
        approval_id=approval_id,
        decision=body.decision,
        resumed=True,
        message="Approved — resuming the task.",
    )
