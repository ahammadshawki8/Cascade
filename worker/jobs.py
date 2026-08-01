"""
CASCADE Track B - Worker Jobs
Day 9-10 implementation target

Background jobs triggered by outbox events:
- compile: Convert episode to playbook
- rule_changed: Update status_cache, set interrupt flags, queue relearns
- relearn: Synthesize task for stale playbook, run explore, compile v2
- recheck: Periodic confidence updates
"""

from typing import Any
from uuid import UUID


async def job_compile(payload: dict[str, Any]) -> None:
    """
    Compile episode into playbook.
    
    Payload: {episode_id: UUID}
    
    Steps:
    1. Load episode from DB + S3
    2. Call compiler.compile_playbook()
    3. POST /internal/sse with playbook.changed event
    """
    raise NotImplementedError("job_compile() - Day 9")


async def job_rule_changed(payload: dict[str, Any]) -> None:
    """
    Handle rule change cascade.
    
    Payload: {rule_key: str, old_version: int, new_version: int}
    
    Steps:
    1. Query playbook_deps for affected playbooks
    2. Update status_cache in batches (≤100 rows/txn)
    3. Set interrupt_flag on running tasks using affected playbooks
    4. Enqueue relearn jobs for active playbooks
    """
    raise NotImplementedError("job_rule_changed() - Day 10")


async def job_relearn(payload: dict[str, Any]) -> None:
    """
    Re-compile stale playbook under new rules.
    
    Payload: {playbook_id: UUID}
    
    Steps:
    1. Load playbook v1
    2. Synthesize representative task
    3. Run explore mode
    4. Compile v2 with supersedes=v1
    5. POST /internal/sse with playbook.changed
    """
    raise NotImplementedError("job_relearn() - Day 10")


async def job_recheck(payload: dict[str, Any]) -> None:
    """
    Periodic confidence recheck for suspect playbooks.
    
    Payload: {playbook_id: UUID}
    
    Checks if confidence/usage patterns warrant status change.
    """
    raise NotImplementedError("job_recheck() - Day 12")


async def _batch_update_status_cache(
    playbook_ids: list[UUID],
    new_status: str,
    batch_size: int = 100
) -> None:
    """
    Update status_cache in batches to avoid large txns.
    
    Args:
        playbook_ids: Playbooks to update
        new_status: New status value
        batch_size: Max rows per transaction
    """
    raise NotImplementedError("_batch_update_status_cache() - Day 10")
