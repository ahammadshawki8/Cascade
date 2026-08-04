"""Mock world — the five tools the agent may call (spec §5.3, D7).

OWNER: Shawki (Track B).

Zero external dependencies by design (edge case #15): every tool is backed by
`mock_incidents` / `mock_action_log`, so a demo can never hang on someone
else's network. Policy lives in `rules`, not in this file — these tools read
the head rule versions and report what policy says.

The two side-effecting tools (`apply_remediation`, `notify_oncall`) are
idempotent on an `idempotency_key` the executor supplies. Replaying a step
after an interrupt must not double-remediate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

# Which remediation each incident class calls for.
ACTION_FOR_KIND = {
    "bad_deploy": "rollback",
    "error_spike": "restart",
    "resource_exhaustion": "scale_up",
}

VALID_ACTIONS = ("rollback", "restart", "scale_up")


async def get_incident(incident_id: str, db) -> dict[str, Any]:
    """Fetch one incident from the mock world."""
    try:
        rows = await db.q(
            """
            SELECT incident_id, kind, severity, service_name, service_tier,
                   deploy_timestamp, state, error_rate, cpu_usage, created_at
            FROM mock_incidents
            WHERE incident_id = %s
            """,
            (incident_id,),
        )
        if not rows:
            return {"error": "incident_not_found", "incident_id": incident_id}

        row = rows[0]
        return {
            "incident_id": row["incident_id"],
            "kind": row["kind"],
            "severity": row["severity"],
            "service_name": row["service_name"],
            "service_tier": row["service_tier"],
            "deploy_timestamp": _iso(row["deploy_timestamp"]),
            "state": row["state"],
            "error_rate": row["error_rate"],
            "cpu_usage": row["cpu_usage"],
            "created_at": _iso(row["created_at"]),
        }
    except Exception as exc:
        return {"error": "database_error", "message": str(exc)}


async def get_rules(domain: str = "incident", db=None) -> dict[str, Any]:
    """Head (current) policy rules for a domain.

    The versions returned here become the playbook's provenance edges, so this
    must only ever return rows with `valid_to IS NULL`.
    """
    try:
        rows = await db.q(
            """
            SELECT rule_key, version, body, params
            FROM rules
            WHERE domain = %s AND valid_to IS NULL
            ORDER BY rule_key
            """,
            (domain,),
        )
        return {
            "domain": domain,
            "rules": [
                {
                    "rule_key": r["rule_key"],
                    "version": r["version"],
                    "body": r["body"],
                    "params": r["params"],
                }
                for r in rows
            ],
        }
    except Exception as exc:
        return {"error": "database_error", "message": str(exc)}


async def check_remediation_eligibility(
    incident_id: str, action: str, db
) -> dict[str, Any]:
    """Evaluate current policy against a proposed action.

    Returns the rule versions it consulted — the compiler turns those into
    `playbook_deps` rows, which is what makes staleness derivable later (D1).
    """
    try:
        if action not in VALID_ACTIONS:
            return {"error": "invalid_action", "action": action}

        incident_rows = await db.q(
            """
            SELECT kind, severity, service_name, service_tier,
                   deploy_timestamp, state
            FROM mock_incidents
            WHERE incident_id = %s
            """,
            (incident_id,),
        )
        if not incident_rows:
            return {"error": "incident_not_found", "incident_id": incident_id}
        incident = incident_rows[0]

        rule_rows = await db.q(
            """
            SELECT rule_key, version, params
            FROM rules
            WHERE domain = 'incident' AND valid_to IS NULL
            """
        )
        rules = {
            r["rule_key"]: {"version": r["version"], "params": r["params"] or {}}
            for r in rule_rows
        }

        reasons: list[str] = []
        rule_versions_used: dict[str, int] = {}

        # Tier gate — service_tier is an INT (1 = production-critical).
        rule = rules.get("incident.auto_remediate_tier")
        if rule:
            rule_versions_used["incident.auto_remediate_tier"] = rule["version"]
            min_tier = int(rule["params"].get("min_tier", 2))
            tier = int(incident["service_tier"])
            if tier < min_tier:
                reasons.append(
                    f"service tier {tier} is below the automation floor of "
                    f"tier {min_tier} — manual approval required"
                )

        # Rollback window.
        rule = rules.get("incident.rollback_window")
        if action == "rollback" and rule:
            rule_versions_used["incident.rollback_window"] = rule["version"]
            window_hours = float(rule["params"].get("hours", 24))
            deployed_at = incident["deploy_timestamp"]
            if deployed_at is None:
                reasons.append("no deploy timestamp — rollback window unverifiable")
            else:
                now = datetime.now(deployed_at.tzinfo or UTC)
                hours = (now - deployed_at).total_seconds() / 3600
                if hours > window_hours:
                    reasons.append(
                        f"deploy was {hours:.1f}h ago, outside the {window_hours:.0f}h "
                        "rollback window"
                    )

        # One automated action per incident.
        rule = rules.get("incident.single_action")
        if rule:
            rule_versions_used["incident.single_action"] = rule["version"]
            existing = await db.q(
                """
                SELECT count(*)::INT AS count
                FROM mock_action_log
                WHERE incident_id = %s AND action IN ('rollback', 'restart', 'scale_up')
                """,
                (incident_id,),
            )
            if existing and existing[0]["count"] > 0:
                reasons.append(
                    "incident already has an automated remediation — single-action "
                    "limit reached"
                )

        if incident["state"] != "open":
            reasons.append(f"incident is {incident['state']}, not open")

        return {
            "eligible": not reasons,
            "action": action,
            "reasons": reasons,
            "rule_versions_used": rule_versions_used,
        }
    except Exception as exc:
        return {"error": "database_error", "message": str(exc)}


async def apply_remediation(
    incident_id: str, action: str, idempotency_key: str = "", db=None, **_ignored
) -> dict[str, Any]:
    """Execute a remediation. Idempotent on `idempotency_key`.

    The key is stored in `mock_action_log.details` rather than a dedicated
    column because the Day-0 schema is frozen; replaying the same step returns
    the original action_id instead of acting twice.
    """
    try:
        if action not in VALID_ACTIONS:
            return {"error": "invalid_action", "action": action}

        if idempotency_key:
            prior = await db.q(
                """
                SELECT action_id, outcome
                FROM mock_action_log
                WHERE incident_id = %s AND details ->> 'idempotency_key' = %s
                LIMIT 1
                """,
                (incident_id, idempotency_key),
            )
            if prior:
                return {
                    "success": prior[0]["outcome"] == "success",
                    "action_id": str(prior[0]["action_id"]),
                    "outcome": prior[0]["outcome"],
                    "note": "idempotent_replay",
                }

        incident_rows = await db.q(
            "SELECT state FROM mock_incidents WHERE incident_id = %s",
            (incident_id,),
        )
        if not incident_rows:
            return {"error": "incident_not_found", "incident_id": incident_id}
        if incident_rows[0]["state"] != "open":
            return {"error": "incident_not_open", "state": incident_rows[0]["state"]}

        action_id = uuid4()
        await db.q(
            """
            INSERT INTO mock_action_log (action_id, incident_id, action, outcome, details)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                str(action_id),
                incident_id,
                action,
                "success",
                json.dumps({"idempotency_key": idempotency_key}),
            ),
        )
        # 'mitigated' is the schema's post-remediation state; 'remediated' is
        # not in the CHECK constraint and would abort the write.
        await db.q(
            "UPDATE mock_incidents SET state = 'mitigated' WHERE incident_id = %s",
            (incident_id,),
        )

        return {
            "success": True,
            "action_id": str(action_id),
            "action": action,
            "outcome": "success",
            "incident_state": "mitigated",
        }
    except Exception as exc:
        return {"error": "execution_failed", "message": str(exc)}


async def notify_oncall(
    incident_id: str, message: str, idempotency_key: str = "", db=None, **_ignored
) -> dict[str, Any]:
    """Page the on-call channel. Idempotent on `idempotency_key`."""
    try:
        if idempotency_key:
            prior = await db.q(
                """
                SELECT action_id
                FROM mock_action_log
                WHERE incident_id = %s
                  AND action = 'notify'
                  AND details ->> 'idempotency_key' = %s
                LIMIT 1
                """,
                (incident_id, idempotency_key),
            )
            if prior:
                return {
                    "sent": True,
                    "notification_id": str(prior[0]["action_id"]),
                    "note": "idempotent_replay",
                }

        exists = await db.q(
            "SELECT 1 FROM mock_incidents WHERE incident_id = %s", (incident_id,)
        )
        if not exists:
            return {"error": "incident_not_found", "incident_id": incident_id}

        notification_id = uuid4()
        await db.q(
            """
            INSERT INTO mock_action_log (action_id, incident_id, action, outcome, details)
            VALUES (%s, %s, 'notify', 'success', %s)
            """,
            (
                str(notification_id),
                incident_id,
                json.dumps({"idempotency_key": idempotency_key, "message": message}),
            ),
        )
        return {
            "sent": True,
            "notification_id": str(notification_id),
            "message": message,
        }
    except Exception as exc:
        return {"error": "notification_failed", "message": str(exc)}


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


# ---------------------------------------------------------------------------
# Tool schemas handed to Claude (spec §5.3)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_incident",
        "description": (
            "Fetch incident details: kind, severity, service, tier, deploy time, state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Incident identifier, e.g. INC-1001",
                }
            },
            "required": ["incident_id"],
        },
    },
    {
        "name": "get_rules",
        "description": "Get the current policy rules governing incident response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Defaults to 'incident'"}
            },
        },
    },
    {
        "name": "check_remediation_eligibility",
        "description": (
            "Check whether policy permits an action on an incident. "
            "MUST be called before apply_remediation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "action": {"type": "string", "enum": list(VALID_ACTIONS)},
            },
            "required": ["incident_id", "action"],
        },
    },
    {
        "name": "apply_remediation",
        "description": (
            "Execute a remediation action. Only call after "
            "check_remediation_eligibility returns eligible=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "action": {"type": "string", "enum": list(VALID_ACTIONS)},
            },
            "required": ["incident_id", "action"],
        },
    },
    {
        "name": "notify_oncall",
        "description": "Notify the on-call engineer about an incident or decision.",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["incident_id", "message"],
        },
    },
    {
        "name": "final_answer",
        "description": "Finish the task. Call exactly once, as the last step.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["success", "escalated"]},
                "summary": {"type": "string"},
            },
            "required": ["outcome", "summary"],
        },
    },
]

TOOL_MAP = {
    "get_incident": get_incident,
    "get_rules": get_rules,
    "check_remediation_eligibility": check_remediation_eligibility,
    "apply_remediation": apply_remediation,
    "notify_oncall": notify_oncall,
}

# Steps that touch the world — the executor checks for interrupts before these
# and injects an idempotency key (spec §5.3, D4).
SIDE_EFFECTING = frozenset({"apply_remediation", "notify_oncall"})
