"""Tasks router — create and list incident remediation tasks.

OWNER: Ashfaq (Track A).

Endpoints:
    POST /api/tasks       — Submit a new task (starts run_task in background)
    GET  /api/tasks       — List recent tasks
    GET  /api/tasks/{id}  — Get single task
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
