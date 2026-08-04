"""Playbook confidence lifecycle (spec §6.3).

OWNER: Shawki (Track B).

Constants are frozen by the spec:

    new playbook      candidate, confidence 0.30
    guided success    confidence += 0.15, capped at 0.99
    guided failure    confidence *= 0.6
    promote  active   successes >= 3 AND confidence >= 0.60
    reject   terminal confidence < 0.20
    idle decay        confidence *= 0.98 per 7 idle days

The read-modify-write runs inside run_txn so two concurrent guided runs on the
same playbook can't lose an increment — CockroachDB's SERIALIZABLE isolation
turns the race into a 40001 retry rather than a silently dropped success.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

log = logging.getLogger(__name__)

INITIAL_CONFIDENCE = 0.30
SUCCESS_INCREMENT = 0.15
FAILURE_MULTIPLIER = 0.6
MAX_CONFIDENCE = 0.99
PROMOTION_THRESHOLD = 0.60
PROMOTION_MIN_SUCCESSES = 3
REJECTION_THRESHOLD = 0.20
IDLE_DECAY_MULTIPLIER = 0.98
IDLE_DAYS = 7


async def update_confidence(playbook_id: UUID, success: bool, db) -> tuple[float, str]:
    """Record one guided outcome. Returns (confidence, status_cache)."""

    async def txn(cur):
        await cur.execute(
            """
            SELECT confidence, uses, successes, failures, status_cache
            FROM playbooks
            WHERE playbook_id = %s
            """,
            (str(playbook_id),),
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError(f"playbook {playbook_id} not found")

        confidence = float(row["confidence"])
        uses = row["uses"] + 1
        successes = row["successes"]
        failures = row["failures"]
        previous_status = row["status_cache"]
        status = previous_status

        if success:
            successes += 1
            confidence = min(MAX_CONFIDENCE, confidence + SUCCESS_INCREMENT)
            if (
                successes >= PROMOTION_MIN_SUCCESSES
                and confidence >= PROMOTION_THRESHOLD
                and status in ("candidate", "suspect")
            ):
                status = "active"
        else:
            failures += 1
            confidence *= FAILURE_MULTIPLIER
            if confidence < REJECTION_THRESHOLD:
                status = "rejected"

        await cur.execute(
            """
            UPDATE playbooks
            SET confidence = %s, uses = %s, successes = %s, failures = %s,
                status_cache = %s, updated_at = now()
            WHERE playbook_id = %s
            """,
            (confidence, uses, successes, failures, status, str(playbook_id)),
        )

        if status != previous_status:
            await cur.execute(
                "INSERT INTO audit_log (kind, actor, details) VALUES (%s, %s, %s)",
                (
                    f"playbook.{status}",
                    "system",
                    json.dumps(
                        {
                            "playbook_id": str(playbook_id),
                            "old_status": previous_status,
                            "new_status": status,
                            "confidence": round(confidence, 4),
                            "successes": successes,
                            "failures": failures,
                        }
                    ),
                ),
            )

        return confidence, status, previous_status

    confidence, status, previous_status = await db.run_txn(txn)

    if status != previous_status:
        log.info(
            "playbook %s: %s -> %s (confidence %.2f)",
            playbook_id,
            previous_status,
            status,
            confidence,
        )
    return confidence, status


async def apply_idle_decay(db, days_threshold: int = IDLE_DAYS) -> int:
    """Decay playbooks nobody has used lately. Returns the number touched.

    Runs from the EventBridge daily sweep. A runbook that stops being used is
    usually a runbook the world moved past.
    """
    rows = await db.q(
        """
        SELECT playbook_id, confidence
        FROM playbooks
        WHERE updated_at < now() - (%s * INTERVAL '1 day')
          AND status_cache IN ('active', 'candidate')
          AND confidence > %s
        """,
        (days_threshold, REJECTION_THRESHOLD),
    )
    if not rows:
        return 0

    decayed = 0
    for row in rows:
        confidence = float(row["confidence"]) * IDLE_DECAY_MULTIPLIER
        status = "rejected" if confidence < REJECTION_THRESHOLD else None
        if status:
            await db.q(
                """
                UPDATE playbooks
                SET confidence = %s, status_cache = %s, updated_at = now()
                WHERE playbook_id = %s
                """,
                (confidence, status, str(row["playbook_id"])),
            )
        else:
            await db.q(
                "UPDATE playbooks SET confidence = %s, updated_at = now() WHERE playbook_id = %s",
                (confidence, str(row["playbook_id"])),
            )
        decayed += 1

    log.info("idle decay applied to %d playbooks", decayed)
    return decayed


def calculate_initial_confidence() -> float:
    """Every freshly compiled playbook starts here."""
    return INITIAL_CONFIDENCE
