"""Tasks router — create and list incident remediation tasks.

OWNER: Ashfaq (Track A).

Endpoints:
    POST /api/tasks               — Submit a new task (starts run_task in background)
    GET  /api/tasks               — List recent tasks
    GET  /api/tasks/{id}          — Get single task
    GET  /api/tasks/{id}/explain  — Why this run went guided or cold
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.bus import TOPIC_TASK_STATUS, sse
from app.config import settings
from app.core.contracts import run_task
from app.core.models import Task, TaskStatus

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    # Must read settings, not os.environ: pydantic-settings loads .env into the
    # Settings object and never exports it to the process environment. Reading
    # os.getenv here meant a .env-only CASCADE_STUB_MODE=true left the lifespan
    # skipping pool creation while the routers still tried to query.
    return settings.cascade_stub_mode


# In-memory task store for stub mode
_stub_tasks: list[Task] = []


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateTaskRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=500, examples=["Remediate INC-1001"])


class CreateTaskResponse(BaseModel):
    task_id: UUID
    status: TaskStatus


class TaskListResponse(BaseModel):
    tasks: list[Task]
    count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/tasks", response_model=CreateTaskResponse, status_code=201)
async def create_task(body: CreateTaskRequest):
    """Create a task and kick off execution in the background."""

    if _stub_mode():
        task_id = uuid4()
        task = Task(
            task_id=task_id,
            input=body.input,
            status="queued",
            created_at=datetime.now(UTC),
        )
        _stub_tasks.insert(0, task)
        # Simulate background execution completing after a short delay
        asyncio.create_task(_stub_execute(task_id))
        return CreateTaskResponse(task_id=task_id, status="queued")

    from app.db import one
    row = await one(
        """
        INSERT INTO tasks (input) VALUES (%s)
        RETURNING task_id, status
        """,
        (body.input,),
    )
    if row is None:
        raise HTTPException(500, "failed to create task")

    task_id = row["task_id"]
    log.info("task created: %s input=%s", task_id, body.input[:60])
    asyncio.create_task(_execute_task(task_id))
    return CreateTaskResponse(task_id=task_id, status="queued")


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(limit: int = 20, status: str | None = None):
    """List recent tasks, optionally filtered by status."""
    if _stub_mode():
        tasks = _stub_tasks[:limit]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return TaskListResponse(tasks=tasks, count=len(tasks))

    from app.db import q
    if status:
        rows = await q(
            """
            SELECT task_id, input, status, result, mode, playbook_id,
                   interrupt_flag, interrupt_reason, scratchpad,
                   created_at, finished_at
            FROM tasks
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (status, limit),
        )
    else:
        rows = await q(
            """
            SELECT task_id, input, status, result, mode, playbook_id,
                   interrupt_flag, interrupt_reason, scratchpad,
                   created_at, finished_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    tasks = [Task(**r) for r in rows]
    return TaskListResponse(tasks=tasks, count=len(tasks))


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: UUID):
    """Get a single task by ID."""
    if _stub_mode():
        for t in _stub_tasks:
            if t.task_id == task_id:
                return t
        raise HTTPException(404, f"task {task_id} not found")

    from app.db import one
    row = await one(
        """
        SELECT task_id, input, status, result, mode, playbook_id,
               interrupt_flag, interrupt_reason, scratchpad,
               created_at, finished_at
        FROM tasks
        WHERE task_id = %s
        """,
        (str(task_id),),
    )
    if row is None:
        raise HTTPException(404, f"task {task_id} not found")
    return Task(**row)


# ---------------------------------------------------------------------------
# Why did this run go the way it did
# ---------------------------------------------------------------------------
# The console shows *what* the agent did. This answers *why* — which is the
# only part a reviewer cannot verify by watching. Four outcomes are possible
# and they look nearly identical from the outside:
#
#   reused              memory matched and was fresh, so no planner ran
#   refused_stale       memory matched but a rule it was compiled against moved
#   refused_precondition memory matched but this incident is not what it covers
#   no_match            memory had nothing close enough
#
# The middle two are the project's whole thesis, and both currently render as
# "it just explored again", which reads as the retrieval having failed.

_REASONS = {
    "reused": (
        "Reused a runbook from memory",
        "Vector search matched a runbook, every rule it was compiled against is "
        "still at head, and its preconditions hold for this incident. No planner "
        "ran: the steps were replayed with fresh parameters.",
    ),
    "refused_stale": (
        "Refused a matching runbook: it is stale",
        "Vector search matched a runbook, but a policy rule it was compiled "
        "against has changed since. Acting on it would apply superseded policy, "
        "so it was refused and the incident was re-planned from scratch.",
    ),
    "refused_precondition": (
        "Refused a matching runbook: preconditions do not hold",
        "Vector search matched a runbook, but its preconditions are not "
        "satisfied by this incident, so it does not apply here. Re-planned "
        "from scratch rather than forcing a near-miss.",
    ),
    "no_match": (
        "Nothing in memory matched",
        "Vector search found no sufficiently similar runbook, so the agent "
        "planned from policy and tools alone. This is the expensive path, and "
        "it is what a successful run turns into reusable memory.",
    ),
}


@router.get("/tasks/{task_id}/explain")
async def explain_task(task_id: UUID):
    """Reconstruct the decision behind one run.

    Reads the audit trail rather than re-deriving anything: the explanation has
    to be what actually happened, not a plausible reconstruction of it.
    """
    if _stub_mode():
        raise HTTPException(400, "explain requires CASCADE_STUB_MODE=false")

    from app.db import one, q

    task = await one(
        """
        SELECT task_id, input, status, result, mode, playbook_id,
               interrupt_reason, created_at, finished_at
        FROM tasks WHERE task_id = %s
        """,
        (str(task_id),),
    )
    if task is None:
        raise HTTPException(404, f"task {task_id} not found")

    episode = await one(
        "SELECT steps, latency_ms, tokens, outcome FROM episodes WHERE task_id = %s",
        (str(task_id),),
    )

    # Retrieval decisions are audit rows, carrying task_id since the executor
    # started stamping them. Runs from before that stamp simply report no
    # recorded refusal, which is the honest answer rather than a guess.
    events = await q(
        """
        SELECT kind, details, at FROM audit_log
        WHERE kind IN ('retrieval.stale_block', 'retrieval.precondition_miss',
                       'playbook.compiled')
          AND details ->> 'task_id' = %s
        ORDER BY at
        """,
        (str(task_id),),
    )
    by_kind = {e["kind"]: e["details"] for e in events}

    if task["mode"] == "guided" and task["playbook_id"]:
        reason = "reused"
    elif "retrieval.precondition_miss" in by_kind:
        reason = "refused_precondition"
    elif "retrieval.stale_block" in by_kind:
        reason = "refused_stale"
    else:
        reason = "no_match"

    headline, detail = _REASONS[reason]
    refusal = by_kind.get("retrieval.stale_block") or by_kind.get(
        "retrieval.precondition_miss"
    )

    playbook = None
    pb_id = task["playbook_id"] or (refusal or {}).get("playbook_id")
    if pb_id:
        playbook = await one(
            """
            SELECT playbook_id, name, version, status_cache, confidence,
                   uses, successes, failures
            FROM playbooks WHERE playbook_id = %s
            """,
            (str(pb_id),),
        )

    from app.core.retrieval import canonical_incident_id

    incident = None
    incident_id = canonical_incident_id(task["input"] or "")
    if incident_id:
        incident = await one(
            """
            SELECT incident_id, kind, severity, service_name, service_tier,
                   state, deploy_timestamp,
                   EXTRACT(EPOCH FROM (now() - deploy_timestamp)) / 3600 AS deploy_age_hours
            FROM mock_incidents WHERE incident_id = %s
            """,
            (incident_id,),
        )

    # The comparison is what makes the cost legible: a guided run is only
    # interesting next to what the cold path costs for the same work.
    #
    # Successful episodes only. An escalation short-circuits before doing the
    # expensive part, so averaging it in drags both modes toward each other and
    # understates the gap — the same workload has to be on both sides of the
    # ratio or the ratio means nothing. Sample sizes travel with it so a thin
    # comparison is visibly thin rather than quietly wrong.
    averages = await q(
        """
        SELECT mode, AVG(latency_ms)::INT AS avg_ms, AVG(tokens)::INT AS avg_tokens,
               COUNT(*)::INT AS runs
        FROM episodes WHERE outcome = 'success' GROUP BY mode
        """
    )
    avg = {r["mode"]: r for r in averages}
    cold_ms = (avg.get("explore") or {}).get("avg_ms")
    guided_ms = (avg.get("guided") or {}).get("avg_ms")

    return {
        "task_id": str(task["task_id"]),
        "input": task["input"],
        "status": task["status"],
        "result": task["result"],
        "mode": task["mode"],
        "interrupt_reason": task["interrupt_reason"],
        "decision": {
            "reason": reason,
            "headline": headline,
            "detail": detail,
            # Present only on a refusal, and named precisely: these are the
            # provenance edges that failed, not a generic error string.
            "stale_deps": (refusal or {}).get("stale_deps"),
            "failed_preconditions": (refusal or {}).get("failed"),
        },
        "incident": incident,
        "playbook": playbook,
        "episode": episode,
        "learned": by_kind.get("playbook.compiled"),
        "comparison": {
            "cold_avg_ms": cold_ms,
            "guided_avg_ms": guided_ms,
            "cold_runs": (avg.get("explore") or {}).get("runs", 0),
            "guided_runs": (avg.get("guided") or {}).get("runs", 0),
            "cold_avg_tokens": (avg.get("explore") or {}).get("avg_tokens"),
            "guided_avg_tokens": (avg.get("guided") or {}).get("avg_tokens"),
            "speedup": round(cold_ms / guided_ms, 2)
            if cold_ms and guided_ms and guided_ms > 0
            else None,
        },
    }


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------


async def _stub_execute(task_id: UUID) -> None:
    """Simulate task execution in stub mode."""
    await asyncio.sleep(0.5)
    for t in _stub_tasks:
        if t.task_id == task_id:
            t.status = "running"
            t.mode = "explore"
            break
    await sse.publish(
        TOPIC_TASK_STATUS.format(task_id=task_id),
        {"task_id": str(task_id), "status": "running"},
    )
    await asyncio.sleep(1.0)
    for t in _stub_tasks:
        if t.task_id == task_id:
            t.status = "succeeded"
            t.result = "remediated"
            t.finished_at = datetime.now(UTC)
            break
    await sse.publish(
        TOPIC_TASK_STATUS.format(task_id=task_id),
        {"task_id": str(task_id), "status": "succeeded"},
    )


async def _execute_task(task_id: UUID) -> None:
    """Background wrapper around contracts.run_task.

    The executor already marks the task failed and publishes on its way out, so
    this only has to make sure a crash before that point still leaves a
    terminal row — a task stuck in 'queued' or 'running' would be counted as
    in-flight forever by the interrupt sweep and the metrics.
    """
    from app.db import q

    try:
        await run_task(task_id)
    except Exception:
        log.exception("task %s failed", task_id)
        await q(
            """
            UPDATE tasks SET status = 'failed', finished_at = now()
            WHERE task_id = %s AND status NOT IN ('succeeded', 'failed', 'interrupted')
            """,
            (str(task_id),),
        )
        await sse.publish(
            TOPIC_TASK_STATUS.format(task_id=task_id),
            {"task_id": str(task_id), "status": "failed"},
        )
