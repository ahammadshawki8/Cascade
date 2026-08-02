"""
CASCADE Track B - Worker Jobs
Day 9 COMPLETE: compile job with compiler integration
Day 10: rule_changed and relearn jobs

Background jobs triggered by outbox events:
- compile: Convert episode to playbook
- rule_changed: Update status_cache, set interrupt flags, queue relearns
- relearn: Synthesize task for stale playbook, run explore, compile v2
- recheck: Periodic confidence updates
"""

import json
from typing import Any
from uuid import UUID


async def job_compile(payload: dict[str, Any], db) -> None:
    """
    Compile episode into playbook.
    
    Payload: {task_id: str, episode_id: str}
    
    Steps:
    1. Load episode from DB + S3
    2. Call compiler.compile_playbook()
    3. POST /internal/sse with playbook.changed event
    
    Args:
        payload: Job payload
        db: Database connection
    """
    import os
    import httpx
    from core.compiler import compile_playbook
    
    task_id = payload.get("task_id")
    episode_id = payload.get("episode_id")
    
    if not task_id or not episode_id:
        raise ValueError("Missing task_id or episode_id in payload")
    
    # Load task and episode
    task_rows = await db.q(
        "SELECT input FROM tasks WHERE task_id = %s",
        (task_id,)
    )
    
    if not task_rows:
        raise ValueError(f"Task {task_id} not found")
    
    episode_rows = await db.q(
        "SELECT outcome, s3_key FROM episodes WHERE episode_id = %s",
        (episode_id,)
    )
    
    if not episode_rows:
        raise ValueError(f"Episode {episode_id} not found")
    
    episode = episode_rows[0]
    
    # Only compile successful episodes
    if episode["outcome"] != "success":
        return
    
    # Load full trajectory from S3 (stub for now - will use episodes table)
    # TODO: Load from S3 when implemented
    # For now, we'll pass task_id and let compiler extract from DB
    
    # Compile playbook
    try:
        playbook_id = await compile_playbook(
            task_id=task_id,
            episode_id=episode_id,
            db=db
        )
        
        # Notify UI via SSE
        api_url = os.getenv("CASCADE_API_URL", "http://localhost:8000")
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{api_url}/internal/sse",
                    json={
                        "event": "playbook.changed",
                        "data": {
                            "playbook_id": str(playbook_id),
                            "action": "created"
                        }
                    },
                    timeout=5.0
                )
        except Exception as e:
            # Non-critical - UI will eventually refresh
            print(f"SSE publish error: {e}")
    
    except Exception as e:
        # Log compilation failure but don't fail job
        # (prevents infinite retries for invalid trajectories)
        print(f"Compilation failed for episode {episode_id}: {e}")
        
        # Insert into audit log
        await db.q(
            """
            INSERT INTO audit_log (kind, actor, details)
            VALUES (%s, %s, %s)
            """,
            (
                "compilation.failed",
                "worker",
                json.dumps({
                    "episode_id": episode_id,
                    "task_id": task_id,
                    "error": str(e)
                })
            )
        )


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
