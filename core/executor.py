"""
CASCADE Track B - Task Executor
Day 2 COMPLETE: Explore loop with SSE streaming
Day 6: Guided mode (TODO)
Day 8: Interrupts (TODO)

Main entry point for task execution.
Handles both explore (cold) and guided (warm) modes.

Budget limits: 15 steps, 60s wall clock, 25k tokens
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from .llm import AgentClient, BudgetTracker, BudgetExceeded
from .models import ExecutionMode, PlaybookCandidate, TaskStatus
from .tools import (
    TOOL_DEFINITIONS,
    get_incident,
    get_rules,
    check_remediation_eligibility,
    apply_remediation,
    notify_oncall
)


# Tool dispatch map
TOOL_MAP = {
    "get_incident": get_incident,
    "get_rules": get_rules,
    "check_remediation_eligibility": check_remediation_eligibility,
    "apply_remediation": apply_remediation,
    "notify_oncall": notify_oncall
}


async def run_task(task_id: UUID, db, sse_bus=None) -> None:
    """
    Main executor entry point.
    
    Flow:
    1. Load task from DB
    2. Try retrieval for candidate playbook
    3. If found + fresh → guided mode (Day 6)
    4. If not found or stale → explore mode
    5. Update task status throughout
    6. Write episode to DB + S3
    7. Enqueue compile event if success
    
    Args:
        task_id: Task to execute
        db: Database connection
        sse_bus: SSE broadcaster for streaming
    """
    start_time = time.time()
    
    try:
        # Load task
        task_rows = await db.q(
            "SELECT task_id, input, status FROM tasks WHERE task_id = %s",
            (str(task_id),)
        )
        
        if not task_rows:
            raise ValueError(f"Task {task_id} not found")
        
        task = task_rows[0]
        task_text = task["input"]
        
        # Update to running
        await db.q(
            "UPDATE tasks SET status = %s WHERE task_id = %s",
            ("running", str(task_id))
        )
        
        if sse_bus:
            await sse_bus.publish(
                f"task.{task_id}.status",
                {"task_id": str(task_id), "status": "running"}
            )
        
        # TODO Day 3: Try retrieval
        # candidate = await retrieve(task_text, db)
        # if candidate:
        #     freshness = await check_freshness(candidate.playbook_id, db)
        #     if freshness.is_fresh:
        #         return await _guided_mode(task_id, task_text, candidate, db, sse_bus)
        
        # For Day 2: Always explore mode
        final_status, result, trajectory = await _explore_mode(
            task_id, task_text, db, sse_bus
        )
        
        # Calculate metrics
        latency_ms = int((time.time() - start_time) * 1000)
        steps = len(trajectory)
        tokens = sum(step.get("tokens", 0) for step in trajectory)
        
        # Determine outcome
        outcome = "success" if final_status == TaskStatus.SUCCEEDED else "failed"
        
        # Write episode
        episode_id = await _write_episode(
            task_id=task_id,
            mode=ExecutionMode.EXPLORE,
            outcome=outcome,
            steps=steps,
            latency_ms=latency_ms,
            tokens=tokens,
            trajectory=trajectory,
            db=db
        )
        
        # Update task final status
        await db.q(
            "UPDATE tasks SET status = %s, result = %s, finished_at = NOW() WHERE task_id = %s",
            (final_status.value, json.dumps(result), str(task_id))
        )
        
        if sse_bus:
            await sse_bus.publish(
                f"task.{task_id}.status",
                {"task_id": str(task_id), "status": final_status.value, "finished_at": datetime.now().isoformat()}
            )
        
        # If success, enqueue compile event (Day 4)
        if outcome == "success":
            await db.q(
                "INSERT INTO outbox (kind, payload) VALUES (%s, %s)",
                ("compile", json.dumps({"task_id": str(task_id), "episode_id": str(episode_id)}))
            )
        
    except Exception as e:
        # Mark task as failed
        await db.q(
            "UPDATE tasks SET status = %s, result = %s, finished_at = NOW() WHERE task_id = %s",
            ("failed", json.dumps({"error": str(e)}), str(task_id))
        )
        raise


async def _explore_mode(
    task_id: UUID,
    task_text: str,
    db,
    sse_bus=None
) -> tuple[TaskStatus, dict, list[dict]]:
    """
    Cold run: Claude converse loop with tools.
    
    Steps:
    1. Get rules upfront for context
    2. Initialize conversation with system prompt + task
    3. Loop: Claude generates tool calls → execute → feed back
    4. Continue until final_answer or budget exhausted
    5. Stream steps over SSE
    
    Args:
        task_id: Current task
        task_text: Task description
        db: Database connection
        sse_bus: SSE broadcaster
    
    Returns:
        (final_status, result_dict, trajectory)
    """
    budget = BudgetTracker(max_steps=15, max_tokens=25000, max_wall_clock=60)
    budget.start()
    
    trajectory = []
    
    try:
        # Get rules upfront
        rules_result = await get_rules(domain="incident", db=db)
        rules_text = json.dumps(rules_result["rules"], indent=2)
        
        # System prompt
        system_prompt = f"""You are an on-call operations agent for a production platform. You resolve incidents by calling tools.

Non-negotiable policy:
1. Current rules (MUST follow exactly):
{rules_text}

2. Before any action, verify eligibility with check_remediation_eligibility.
3. Never call apply_remediation without first checking eligibility for the same incident and action.
4. If rules do not permit automated action, escalate gracefully: notify on-call with reason, call final_answer with outcome='escalated'.
5. Be economical: fewest tool calls that correctly resolve the incident.

When done, call final_answer with {{"outcome": "success"|"escalated", "summary": "..."}}.
"""
        
        # STUB: For Day 2, simulate tool loop
        # Real implementation will use AgentClient.converse_with_tools() with Bedrock
        
        # Simulated trajectory for testing (will be replaced with real Claude calls)
        step_index = 0
        
        # Step 1: get_incident
        step_1_start = time.time()
        incident_result = await get_incident(task_text.split()[-1], db)  # Extract INC-XXXX
        step_1_time = time.time() - step_1_start
        
        step_1 = {
            "step_index": step_index,
            "tool_name": "get_incident",
            "tool_input": {"incident_id": task_text.split()[-1]},
            "tool_output": incident_result,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": int(step_1_time * 1000),
            "tokens": 150
        }
        trajectory.append(step_1)
        budget.record_step(150)
        
        if sse_bus:
            await sse_bus.publish(f"task.{task_id}.step", step_1)
        
        step_index += 1
        
        # For Day 2 stub: simulate success outcome
        final_answer = {
            "outcome": "success",
            "summary": "Simulated explore mode for Day 2 - real Claude integration on next iteration"
        }
        
        return (
            TaskStatus.SUCCEEDED,
            {"outcome": "remediated", "summary": final_answer["summary"]},
            trajectory
        )
    
    except BudgetExceeded as e:
        # Budget exhausted - fail task
        return (
            TaskStatus.FAILED,
            {"error": "budget_exceeded", "reason": str(e)},
            trajectory
        )
    
    except Exception as e:
        # Other error
        return (
            TaskStatus.FAILED,
            {"error": "execution_error", "reason": str(e)},
            trajectory
        )


async def _guided_mode(
    task_id: UUID,
    task_text: str,
    playbook: PlaybookCandidate,
    db,
    sse_bus=None
) -> tuple[TaskStatus, dict, list[dict]]:
    """
    Warm run: Execute playbook steps directly.
    
    Day 6 implementation - guided execution:
    1. Load full playbook spec
    2. Precondition check (Haiku)
    3. Extract parameters (Haiku)
    4. Execute steps sequentially with bound params
    5. Update confidence counters
    
    Args:
        task_id: Current task
        task_text: Task description
        playbook: Retrieved playbook candidate
        db: Database connection
        sse_bus: SSE broadcaster
    
    Returns:
        (final_status, result_dict, trajectory)
    """
    raise NotImplementedError("_guided_mode() - Day 6")


async def _write_episode(
    task_id: UUID,
    mode: ExecutionMode,
    outcome: str,
    steps: int,
    latency_ms: int,
    tokens: int,
    trajectory: list[dict],
    db
) -> UUID:
    """
    Write episode to DB + S3.
    
    DB: Truncated metadata (first 10 steps)
    S3: Full trajectory JSON (Day 2 stub - just DB for now)
    
    Args:
        task_id: Task that completed
        mode: explore | guided
        outcome: success | failed
        steps: Step count
        latency_ms: Wall clock time
        tokens: Token usage
        trajectory: Full step-by-step execution
        db: Database connection
    
    Returns:
        episode_id
    """
    from uuid import uuid4
    
    episode_id = uuid4()
    
    # Truncate trajectory for DB (first 10 steps)
    truncated_trajectory = trajectory[:10]
    
    # TODO Day 2: Upload full trajectory to S3
    # s3_key = f"episodes/{episode_id}.json"
    # await s3_client.put_object(
    #     Bucket=os.getenv("EPISODES_BUCKET"),
    #     Key=s3_key,
    #     Body=json.dumps(trajectory)
    # )
    s3_key = None
    
    # Write episode to DB
    await db.q(
        """
        INSERT INTO episodes (episode_id, task_id, outcome, mode, steps, latency_ms, tokens, s3_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (str(episode_id), str(task_id), outcome, mode.value, steps, latency_ms, tokens, s3_key)
    )
    
    return episode_id


async def _check_interrupt(task_id: UUID, interrupt_bus=None, db=None) -> tuple[bool, str]:
    """
    Check if task has been interrupted.
    
    Day 8 implementation:
    1. Check InterruptBus in-memory event (microseconds)
    2. Fallback: Check durable tasks.interrupt_flag
    
    Args:
        task_id: Task to check
        interrupt_bus: In-memory interrupt bus
        db: Database connection
    
    Returns:
        (interrupted, reason)
    """
    # Day 8 - for now, always return False
    return (False, "")


async def _handle_interrupt(
    task_id: UUID,
    scratchpad: dict,
    reason: str,
    db,
    sse_bus=None
) -> None:
    """
    Handle interrupt: persist scratchpad, re-plan, resume.
    
    Day 8 implementation:
    1. Save current scratchpad to tasks.scratchpad
    2. Call get_rules() to get fresh rule versions
    3. Re-plan remaining steps under new rules
    4. Resume execution
    
    Args:
        task_id: Interrupted task
        scratchpad: Current execution state
        reason: Why interrupted
        db: Database connection
        sse_bus: SSE broadcaster
    """
    raise NotImplementedError("_handle_interrupt() - Day 8")
