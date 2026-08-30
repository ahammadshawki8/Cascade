"""Analysis surfaces — counterfactual replay, time travel, blast radius.

T2.2 counterfactual_replay  what a proposed policy would have done to history
T2.3 time_travel            what the system believed at a past timestamp
T2.4 blast_radius_graph     rules -> playbooks -> tasks, as a graph

All three are read-only and none of them call a model. An operator about to
change production policy is entitled to an exact answer, not a plausible one
(decision D6).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

_INCIDENT_RE = re.compile(r"INC-\d+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# T2.2 — Counterfactual replay
# ---------------------------------------------------------------------------


async def counterfactual_replay(
    rule_key: str, new_params: dict[str, Any], db, limit: int = 200
) -> dict[str, Any]:
    """Re-decide historical incidents under a proposed rule.

    The impact preview answers "which runbooks go stale". This answers the
    question an SRE actually has: *what would have happened differently?*

    Deterministic — it re-evaluates the same eligibility predicates the tool
    uses, against each incident's recorded state. No LLM, no re-execution, no
    side effects.
    """
    head = await db.q(
        "SELECT version, params FROM rules WHERE rule_key = %s AND valid_to IS NULL",
        (rule_key,),
    )
    if not head:
        raise ValueError(f"rule {rule_key!r} has no current version")

    current_params = head[0]["params"] or {}
    merged = {**current_params, **new_params}

    incidents = await db.q(
        """
        SELECT incident_id, kind, severity, service_name, service_tier,
               deploy_timestamp, state
        FROM mock_incidents
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )

    other_rules = await db.q(
        """
        SELECT rule_key, params FROM rules
        WHERE domain = 'incident' AND valid_to IS NULL AND rule_key != %s
        """,
        (rule_key,),
    )
    baseline = {r["rule_key"]: (r["params"] or {}) for r in other_rules}

    now_allowed, would_allow = [], []
    newly_blocked, newly_allowed = [], []

    for incident in incidents:
        before = _eligible(incident, {**baseline, rule_key: current_params})
        after = _eligible(incident, {**baseline, rule_key: merged})

        if before:
            now_allowed.append(incident["incident_id"])
        if after:
            would_allow.append(incident["incident_id"])

        if before and not after:
            newly_blocked.append(
                {
                    "incident_id": incident["incident_id"],
                    "kind": incident["kind"],
                    "service": incident["service_name"],
                    "tier": incident["service_tier"],
                }
            )
        elif after and not before:
            newly_allowed.append(
                {
                    "incident_id": incident["incident_id"],
                    "kind": incident["kind"],
                    "service": incident["service_name"],
                    "tier": incident["service_tier"],
                }
            )

    return {
        "rule_key": rule_key,
        "current_params": current_params,
        "proposed_params": merged,
        "incidents_examined": len(incidents),
        "auto_remediated_before": len(now_allowed),
        "auto_remediated_after": len(would_allow),
        "newly_allowed": newly_allowed,
        "newly_blocked": newly_blocked,
        "net_change": len(would_allow) - len(now_allowed),
        "summary": _replay_summary(len(newly_allowed), len(newly_blocked), len(incidents)),
    }


def _eligible(incident: dict[str, Any], rules: dict[str, dict]) -> bool:
    """Mirror of check_remediation_eligibility, without side effects.

    Kept deliberately in lockstep with tools.check_remediation_eligibility —
    if the two drift, the preview stops predicting the real system.
    """
    if incident["state"] != "open":
        return False

    tier_rule = rules.get("incident.auto_remediate_tier", {})
    min_tier = int(tier_rule.get("min_tier", 2))
    if int(incident["service_tier"]) < min_tier:
        return False

    if incident["kind"] == "bad_deploy":
        window_rule = rules.get("incident.rollback_window", {})
        window_hours = float(window_rule.get("hours", 24))
        deployed = incident["deploy_timestamp"]
        if deployed is None:
            return False

        now = datetime.now(deployed.tzinfo or UTC)
        if (now - deployed).total_seconds() / 3600 > window_hours:
            return False

    return True


def _replay_summary(allowed: int, blocked: int, examined: int) -> str:
    if not allowed and not blocked:
        return f"No change: all {examined} historical incidents decide the same way."
    parts = []
    if allowed:
        parts.append(f"{allowed} incident(s) would now be auto-remediated")
    if blocked:
        parts.append(f"{blocked} incident(s) would now be blocked")
    return f"Across {examined} historical incidents, " + " and ".join(parts) + "."


# ---------------------------------------------------------------------------
# T2.3 — Time travel
# ---------------------------------------------------------------------------

# CockroachDB's default GC window. Beyond this the MVCC history is gone, and
# asking for it returns a "batch timestamp must be after replica GC threshold"
# error rather than empty data.
MAX_LOOKBACK = timedelta(hours=25)


async def time_travel(db, minutes_ago: int) -> dict[str, Any]:
    """Re-read core state as it was N minutes ago, via MVCC.

    Uses CockroachDB's `AS OF SYSTEM TIME` — the history is already in the
    database, so answering "what did the agent believe when it made that call?"
    needs no event-sourcing layer of our own.

    The interval is inlined rather than parameterised: AS OF SYSTEM TIME must
    be a constant expression, so it cannot take a placeholder. The value is
    coerced to a bounded int here, never interpolated from user text.
    """
    minutes = max(1, min(int(minutes_ago), int(MAX_LOOKBACK.total_seconds() // 60)))
    clause = f"AS OF SYSTEM TIME '-{minutes}m'"

    try:
        playbooks = await db.q(
            f"""
            SELECT playbook_id, name, version, status_cache, confidence,
                   uses, successes, failures
            FROM playbooks {clause}
            ORDER BY confidence DESC
            """
        )
        rules = await db.q(
            f"""
            SELECT rule_key, version, body, params
            FROM rules {clause}
            WHERE valid_to IS NULL
            ORDER BY rule_key
            """
        )
        tasks = await db.q(
            f"""
            SELECT task_id, input, status, result, mode, created_at
            FROM tasks {clause}
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
    except Exception as exc:
        message = str(exc)
        if "GC threshold" in message or "must be after" in message:
            return {
                "available": False,
                "minutes_ago": minutes,
                "message": (
                    f"No MVCC history {minutes} minutes back — beyond the "
                    "cluster's garbage-collection window."
                ),
            }
        log.warning("time travel failed: %s", exc)
        return {"available": False, "minutes_ago": minutes, "message": message}

    return {
        "available": True,
        "minutes_ago": minutes,
        "as_of": f"-{minutes}m",
        "playbooks": [dict(r) for r in playbooks],
        "rules": [dict(r) for r in rules],
        "tasks": [dict(r) for r in tasks],
        "note": (
            "Read directly from CockroachDB MVCC history with AS OF SYSTEM "
            "TIME — no snapshot table, no event log."
        ),
    }


# ---------------------------------------------------------------------------
# T2.4 — Blast radius graph
# ---------------------------------------------------------------------------


async def blast_radius_graph(db, focus_rule: str | None = None) -> dict[str, Any]:
    """rules -> playbooks -> tasks as nodes and edges.

    Makes the project's central claim visible in one frame: which runbooks a
    policy governs, and which work is in flight underneath them.
    """
    rules = await db.q(
        """
        SELECT rule_key, version, body FROM rules
        WHERE valid_to IS NULL ORDER BY rule_key
        """
    )
    playbooks = await db.q(
        """
        SELECT playbook_id, name, version, status_cache, confidence
        FROM playbooks ORDER BY confidence DESC
        """
    )
    deps = await db.q(
        """
        SELECT d.playbook_id, d.rule_key, d.rule_version, r.version AS head_version
        FROM playbook_deps d
        LEFT JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        """
    )
    tasks = await db.q(
        """
        SELECT task_id, input, status, playbook_id
        FROM tasks
        WHERE playbook_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 40
        """
    )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for rule in rules:
        nodes.append(
            {
                "id": f"rule:{rule['rule_key']}",
                "type": "rule",
                "label": rule["rule_key"],
                "version": rule["version"],
                "focused": rule["rule_key"] == focus_rule,
            }
        )

    for playbook in playbooks:
        nodes.append(
            {
                "id": f"playbook:{playbook['playbook_id']}",
                "type": "playbook",
                "label": playbook["name"],
                "version": playbook["version"],
                "status": playbook["status_cache"],
                "confidence": round(float(playbook["confidence"]), 2),
            }
        )

    for task in tasks:
        nodes.append(
            {
                "id": f"task:{task['task_id']}",
                "type": "task",
                "label": task["input"][:48],
                "status": task["status"],
            }
        )
        edges.append(
            {
                "source": f"playbook:{task['playbook_id']}",
                "target": f"task:{task['task_id']}",
                "kind": "executed",
                "stale": False,
            }
        )

    for dep in deps:
        stale = (
            dep["head_version"] is not None
            and dep["rule_version"] != dep["head_version"]
        )
        edges.append(
            {
                "source": f"rule:{dep['rule_key']}",
                "target": f"playbook:{dep['playbook_id']}",
                "kind": "governs",
                "stale": stale,
                "pinned_version": dep["rule_version"],
                "head_version": dep["head_version"],
            }
        )

    known = {node["id"] for node in nodes}
    edges = [e for e in edges if e["source"] in known and e["target"] in known]

    return {
        "nodes": nodes,
        "edges": edges,
        "focus_rule": focus_rule,
        "stale_edges": sum(1 for e in edges if e["stale"]),
    }


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
