"""
CASCADE Track B - Task Executor
Day 2 (explore loop), Day 6 (guided mode), Day 8 (interrupts)

Main entry point for task execution.
Handles both explore (cold) and guided (warm) modes.
"""

from uuid import UUID

from .models import ExecutionMode, PlaybookCandidate, TaskStatus


async def run_task(task_id: UUID) -> None:
    """
    Main executor entry point.
    
    Flow:
    1. Load task from DB
    2. Retrieve candidate playbook
    3. If found: check freshness → guided mode
    4. If not found or stale → explore mode
    5. Update task status throughout
    6. Write episode to DB + S3
    
    Args:
        task_id: Task to execute
    """
    raise NotImplementedError("run_task() - Day 2")


async def _explore_mode(
    task_id: UUID,
    task_text: str
) -> tuple[TaskStatus, dict, list[dict]]:
    """
    Cold run: Claude converse loop with tools.
    
    Steps:
    1. Initialize conversation with task
    2. Loop: Claude generates tool calls → execute → feed back
    3. Continue until final_answer
    4. Stream steps over SSE via InterruptBus
    5. Check interrupt_flag before side-effects
    
    Args:
        task_id: Current task
        task_text: Task description
    
    Returns:
        (final_status, result_dict, trajectory)
    """
    raise NotImplementedError("_explore_mode() - Day 2")


async def _guided_mode(
    task_id: UUID,
    task_text: str,
    playbook: PlaybookCandidate
) -> tuple[TaskStatus, dict, list[dict]]:
    """
    Warm run: Execute playbook steps directly.
    
    Steps:
    1. Load full playbook spec
    2. Precondition check (Haiku)
    3. Extract parameters (Haiku)
    4. Execute steps sequentially
    5. Check interrupt_flag before each side-effect step
    6. Update confidence counters
    
    Args:
        task_id: Current task
        task_text: Task description
        playbook: Retrieved playbook candidate
    
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
    trajectory: list[dict]
) -> None:
    """
    Write episode to DB + S3.
    
    DB: Truncated metadata
    S3: Full trajectory JSON
    
    Args:
        task_id: Task that completed
        mode: explore | guided
        outcome: success | failed
        steps: Step count
        latency_ms: Wall clock time
        tokens: Token usage
        trajectory: Full step-by-step execution
    """
    raise NotImplementedError("_write_episode() - Day 2")


async def _check_interrupt(task_id: UUID) -> tuple[bool, str]:
    """
    Check if task has been interrupted.
    
    Checks:
    1. InterruptBus in-memory event (microseconds)
    2. Durable tasks.interrupt_flag fallback
    
    Args:
        task_id: Task to check
    
    Returns:
        (interrupted, reason)
    """
    raise NotImplementedError("_check_interrupt() - Day 8")


async def _handle_interrupt(
    task_id: UUID,
    scratchpad: dict,
    reason: str
) -> None:
    """
    Handle interrupt: persist scratchpad, re-plan, resume.
    
    Steps:
    1. Save current scratchpad to tasks.scratchpad
    2. Call get_rules() to get fresh rule versions
    3. Re-plan remaining steps under new rules
    4. Resume execution
    
    Args:
        task_id: Interrupted task
        scratchpad: Current execution state
        reason: Why interrupted
    """
    raise NotImplementedError("_handle_interrupt() - Day 8")
