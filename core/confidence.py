"""
CASCADE Track B - Confidence Scoring
Day 6 COMPLETE: Lifecycle-aware confidence math

Constants (FROZEN - from spec):
- New playbook: candidate, confidence 0.30
- Success: confidence += 0.15 (max 0.99)
- Failure: confidence *= 0.6
- Promote to active: successes >= 3 AND confidence >= 0.6
- Reject: confidence < 0.20 (terminal)
- Idle decay: confidence *= 0.98 per 7 days (daily job)
"""

import json
from uuid import UUID


# Lifecycle constants (FROZEN per spec)
INITIAL_CONFIDENCE = 0.30
SUCCESS_INCREMENT = 0.15
FAILURE_MULTIPLIER = 0.6
MAX_CONFIDENCE = 0.99
PROMOTION_THRESHOLD = 0.60
PROMOTION_MIN_SUCCESSES = 3
REJECTION_THRESHOLD = 0.20
IDLE_DECAY_MULTIPLIER = 0.98
IDLE_DAYS = 7


async def update_confidence(
    playbook_id: UUID,
    success: bool,
    db
) -> tuple[float, str]:
    """
    Update playbook confidence after guided execution.
    
    Success path:
    - confidence = min(0.99, confidence + 0.15)
    - successes++, uses++
    - If successes >= 3 AND confidence >= 0.6 → promote to 'active'
    
    Failure path:
    - confidence *= 0.6
    - failures++, uses++
    - If confidence < 0.20 → mark 'rejected' (terminal)
    
    Args:
        playbook_id: Playbook that executed
        success: Whether execution succeeded
        db: Database connection
    
    Returns:
        (new_confidence, new_status)
    """
    # Load current state
    rows = await db.q(
        """
        SELECT confidence, uses, successes, failures, status_cache
        FROM playbooks
        WHERE playbook_id = %s
        """,
        (str(playbook_id),)
    )
    
    if not rows:
        raise ValueError(f"Playbook {playbook_id} not found")
    
    current = rows[0]
    confidence = current["confidence"]
    uses = current["uses"]
    successes = current["successes"]
    failures = current["failures"]
    status = current["status_cache"]
    
    # Update counters
    uses += 1
    
    if success:
        successes += 1
        confidence = min(MAX_CONFIDENCE, confidence + SUCCESS_INCREMENT)
        
        # Check for promotion
        if successes >= PROMOTION_MIN_SUCCESSES and confidence >= PROMOTION_THRESHOLD:
            if status in ("candidate", "suspect"):
                status = "active"
    else:
        failures += 1
        confidence *= FAILURE_MULTIPLIER
        
        # Check for rejection
        if confidence < REJECTION_THRESHOLD:
            status = "rejected"
    
    # Update database
    await db.q(
        """
        UPDATE playbooks
        SET confidence = %s, uses = %s, successes = %s, failures = %s,
            status_cache = %s, updated_at = NOW()
        WHERE playbook_id = %s
        """,
        (confidence, uses, successes, failures, status, str(playbook_id))
    )
    
    # Insert audit if status changed
    if status != current["status_cache"]:
        await db.q(
            """
            INSERT INTO audit_log (kind, actor, details)
            VALUES (%s, %s, %s)
            """,
            (
                f"playbook.{status}",
                "system",
                json.dumps({
                    "playbook_id": str(playbook_id),
                    "old_status": current["status_cache"],
                    "new_status": status,
                    "confidence": confidence,
                    "successes": successes,
                    "failures": failures
                })
            )
        )
    
    return (confidence, status)


async def apply_idle_decay(db, days_threshold: int = IDLE_DAYS) -> int:
    """
    Apply idle decay to playbooks not used recently.
    confidence *= 0.98 per 7 days idle.
    
    Daily worker job (guarded by audit_log marker).
    
    Args:
        db: Database connection
        days_threshold: Days of inactivity before decay
    
    Returns:
        Number of playbooks decayed
    """
    # Find idle playbooks
    rows = await db.q(
        """
        SELECT playbook_id, confidence
        FROM playbooks
        WHERE updated_at < NOW() - INTERVAL '%s days'
          AND status_cache IN ('active', 'candidate')
          AND confidence > %s
        """,
        (days_threshold, REJECTION_THRESHOLD)
    )
    
    if not rows:
        return 0
    
    count = 0
    for row in rows:
        new_confidence = row["confidence"] * IDLE_DECAY_MULTIPLIER
        
        # Check if decay causes rejection
        new_status = "rejected" if new_confidence < REJECTION_THRESHOLD else None
        
        if new_status:
            await db.q(
                """
                UPDATE playbooks
                SET confidence = %s, status_cache = %s, updated_at = NOW()
                WHERE playbook_id = %s
                """,
                (new_confidence, new_status, str(row["playbook_id"]))
            )
        else:
            await db.q(
                """
                UPDATE playbooks
                SET confidence = %s, updated_at = NOW()
                WHERE playbook_id = %s
                """,
                (new_confidence, str(row["playbook_id"]))
            )
        
        count += 1
    
    return count


def calculate_initial_confidence() -> float:
    """
    Calculate confidence for newly compiled playbook.
    
    All new playbooks start at 0.30 (candidate status).
    
    Returns:
        Initial confidence (0.30)
    """
    return INITIAL_CONFIDENCE
