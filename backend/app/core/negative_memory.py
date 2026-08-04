"""Negative memory — remembering what failed (T2.5).

OWNER: Shawki (Track B).

Only successes were ever compiled. A failed approach was forgotten the moment
the task ended, so the agent could rediscover the same dead end indefinitely —
paying full explore cost each time to reach the same wall.

An anti-playbook records: this class of incident, this action, this is why it
failed. Relevant ones are injected into the explore prompt as warnings.

Two deliberate constraints:

  * Anti-playbooks are **never retrieved for execution**, only for avoidance.
    They live in their own table rather than as a flag on `playbooks` precisely
    so no retrieval path can ever surface one as something to run.

  * They are advisory, never authoritative. The prompt says "a previous attempt
    failed because X" — it does not forbid the action. Policy is enforced by
    `check_remediation_eligibility`, and a stale memory of failure must not be
    able to veto something the rules now permit.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from .retrieval import to_vector_literal

log = logging.getLogger(__name__)

# How close a past failure must be to count as relevant to this task.
RELEVANCE_THRESHOLD = 1.0
MAX_WARNINGS = 3


async def record_failure(
    episode_id: UUID | None,
    task_text: str,
    trajectory: list[dict[str, Any]],
    failure_reason: str,
    db,
) -> UUID | None:
    """Store (or reinforce) an anti-playbook from a failed run.

    Repeated identical failures increment `occurrences` rather than inserting
    duplicates — a dead end hit five times is one lesson, not five.
    """
    incident = _first_output(trajectory, "get_incident") or {}
    kind = str(incident.get("kind") or "unknown")

    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    action = eligibility.get("action") or _attempted_action(trajectory)

    existing = await db.q(
        """
        SELECT anti_id, occurrences FROM anti_playbooks
        WHERE incident_kind = %s
          AND COALESCE(attempted_action, '') = COALESCE(%s, '')
          AND failure_reason = %s
        LIMIT 1
        """,
        (kind, action, failure_reason[:2000]),
    )
    if existing:
        await db.q(
            """
            UPDATE anti_playbooks
            SET occurrences = occurrences + 1, updated_at = now()
            WHERE anti_id = %s
            """,
            (str(existing[0]["anti_id"]),),
        )
        log.info(
            "reinforced anti-playbook %s (%s/%s), now %d occurrences",
            existing[0]["anti_id"],
            kind,
            action,
            existing[0]["occurrences"] + 1,
        )
        return _as_uuid(existing[0]["anti_id"])

    from .llm import EmbedClient

    embedding = await EmbedClient().embed(task_text or f"{kind} {action or ''}")

    rows = await db.q(
        """
        INSERT INTO anti_playbooks (
            incident_kind, attempted_action, failure_reason,
            trajectory_digest, episode_id, embedding
        ) VALUES (%s, %s, %s, %s, %s, %s::vector)
        RETURNING anti_id
        """,
        (
            kind,
            action,
            failure_reason[:2000],
            json.dumps(_digest(trajectory), default=str),
            str(episode_id) if episode_id else None,
            to_vector_literal(embedding),
        ),
    )
    anti_id = _as_uuid(rows[0]["anti_id"])
    log.info("recorded anti-playbook %s: %s/%s — %s", anti_id, kind, action, failure_reason[:80])
    return anti_id


async def relevant_warnings(task_text: str, db, limit: int = MAX_WARNINGS) -> list[dict]:
    """Past failures worth warning the planner about, nearest first.

    Uses the same pure-ANN-then-filter shape as playbook retrieval (D3): no
    predicate in the vector query, or the optimizer drops the index.
    """
    from .llm import EmbedClient

    try:
        embedding = await EmbedClient().embed(task_text)
        literal = to_vector_literal(embedding)
        candidates = await db.q(
            """
            SELECT anti_id, embedding <-> %s::vector AS dist
            FROM anti_playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            (literal, literal, limit * 2),
        )
    except Exception as exc:
        log.warning("anti-playbook lookup failed: %s", exc)
        return []

    close = [
        c
        for c in candidates
        if c["dist"] is not None and float(c["dist"]) <= RELEVANCE_THRESHOLD
    ]
    if not close:
        return []

    rows = await db.q(
        """
        SELECT anti_id, incident_kind, attempted_action, failure_reason, occurrences
        FROM anti_playbooks
        WHERE anti_id = ANY(%s)
        """,
        ([str(c["anti_id"]) for c in close],),
    )
    by_id = {str(r["anti_id"]): dict(r) for r in rows}

    ordered = []
    for candidate in close:
        row = by_id.get(str(candidate["anti_id"]))
        if row:
            row["distance"] = round(float(candidate["dist"]), 3)
            ordered.append(row)
    return ordered[:limit]


def format_warnings(warnings: list[dict]) -> str:
    """Render warnings for the system prompt. Empty string when there are none."""
    if not warnings:
        return ""

    lines = [
        "",
        "Previous attempts on similar incidents that FAILED — do not repeat them "
        "blindly. These are advisory: if current policy permits an action, the "
        "eligibility check is what decides, not this list.",
    ]
    for warning in warnings:
        times = (
            " (seen once)"
            if warning["occurrences"] == 1
            else f" (seen {warning['occurrences']} times)"
        )
        action = warning["attempted_action"] or "an action"
        lines.append(
            f"- On {warning['incident_kind']}: `{action}` failed — "
            f"{warning['failure_reason']}{times}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def _attempted_action(trajectory: list[dict]) -> str | None:
    for entry in reversed(trajectory):
        if entry.get("tool_name") == "apply_remediation":
            return (entry.get("tool_input") or {}).get("action")
    return None


def _first_output(trajectory: list[dict], tool: str) -> dict | None:
    for entry in trajectory:
        if entry.get("tool_name") == tool and isinstance(entry.get("tool_output"), dict):
            return entry["tool_output"]
    return None


def _digest(trajectory: list[dict]) -> dict[str, Any]:
    return {
        "steps": [
            {"tool": e.get("tool_name"), "args": e.get("tool_input")}
            for e in trajectory[:10]
        ],
        "step_count": len(trajectory),
    }


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
