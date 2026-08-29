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
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.connectors import deliver_for_tool
from app.core.policy import PredicateError, build_incident_facts, evaluate

log = logging.getLogger(__name__)

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
        # Deliberately unchanged by migration 006, despite `enforcement` now
        # existing and looking useful here.
        #
        # This output is the compiler's input as well as the planner's, and
        # adding one field to it moved the model's compiled preconditions enough
        # that a tier-3 incident stopped matching a runbook it had matched
        # before — retrieval hit, precondition miss, silent loss of reuse. The
        # planner does not need it: policy binds through
        # check_remediation_eligibility whatever this says, so the field would
        # buy nothing and cost a behaviour change in a model-shaped surface.
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

    Every enforcing rule in the domain is applied, whatever it is and whoever
    wrote it. This used to name three rule keys and hand-write a comparison for
    each, which meant a rule a user invented was stored, versioned, cascaded and
    correctly reported stale while being enforced by nothing — a policy that
    decided nothing. The three comparisons are now three seeded predicates and
    this loop is all that is left of them.

    Returns the rule versions it consulted — the compiler turns those into
    `playbook_deps` rows, which is what makes staleness derivable later (D1).
    A rule is *consulted* when its `when` gate lets it speak, whether or not it
    then refuses; that is the same set the hardcoded version recorded.
    """
    try:
        if action not in VALID_ACTIONS:
            return {"error": "invalid_action", "action": action}

        incident_rows = await db.q(
            """
            SELECT incident_id, kind, severity, service_name, service_tier,
                   deploy_timestamp, state, error_rate, cpu_usage
            FROM mock_incidents
            WHERE incident_id = %s
            """,
            (incident_id,),
        )
        if not incident_rows:
            return {"error": "incident_not_found", "incident_id": incident_id}
        incident = incident_rows[0]

        # The single-action limit is a fact about the world, not a special case:
        # counting prior actions once here lets any rule reason about it.
        prior = await db.q(
            """
            SELECT count(*)::INT AS count
            FROM mock_action_log
            WHERE incident_id = %s AND action IN ('rollback', 'restart', 'scale_up')
            """,
            (incident_id,),
        )
        facts = build_incident_facts(
            incident, action=action, prior_actions=prior[0]["count"] if prior else 0
        )

        rule_rows = await db.q(
            """
            SELECT rule_key, version, params, predicate, enforcement
            FROM rules
            WHERE domain = 'incident' AND valid_to IS NULL
            ORDER BY rule_key
            """
        )

        reasons: list[str] = []
        shadow: list[dict[str, Any]] = []
        rule_versions_used: dict[str, int] = {}

        for row in rule_rows:
            enforcement = row.get("enforcement") or "advisory"
            if enforcement == "advisory":
                # Prose only. Cited by procedures and cascaded like any other
                # rule, but it has no verdict to give here.
                continue

            try:
                verdict = evaluate(
                    row.get("predicate"), facts, row.get("params") or {}
                )
            except PredicateError as exc:
                # A malformed rule must not decide anything, and must not take
                # the run down either. Authoring validates predicates precisely
                # so this stays unreachable; if it fires, say so out loud.
                log.warning("rule %s has an invalid predicate: %s", row["rule_key"], exc)
                continue

            if not verdict.applies:
                continue

            rule_versions_used[row["rule_key"]] = row["version"]

            if verdict.passed:
                continue
            if enforcement == "shadow":
                # Evaluated and recorded, but not binding. This is how an
                # operator finds out what a rule would have blocked before
                # letting it block anything.
                shadow.append({"rule_key": row["rule_key"], "reason": verdict.reason})
            else:
                reasons.append(verdict.reason or "policy refuses this action")

        # Not a rule: an incident that is not open has nothing to remediate,
        # whatever policy says. Keeping it out of the rules table means nobody
        # can accidentally delete the invariant that stops double-remediation.
        if incident["state"] != "open":
            reasons.append(f"incident is {incident['state']}, not open")

        result: dict[str, Any] = {
            "eligible": not reasons,
            "action": action,
            "reasons": reasons,
            "rule_versions_used": rule_versions_used,
        }
        if shadow:
            result["shadow_refusals"] = shadow
        return result
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

        incident_rows = await db.q(
            """
            SELECT incident_id, kind, severity, service_name, service_tier, state
            FROM mock_incidents WHERE incident_id = %s
            """,
            (incident_id,),
        )
        if not incident_rows:
            return {"error": "incident_not_found", "incident_id": incident_id}
        incident = incident_rows[0]

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

        result: dict[str, Any] = {
            "sent": True,
            "notification_id": str(notification_id),
            "message": message,
        }

        # What actually happened to this incident, read from the action log.
        #
        # Not inferred from the message text. The first version of this looked
        # for "remediat" and titled a card "Cascade remediated INC-1001" on top
        # of a message that said automated remediation was blocked by policy —
        # the notification was correct and the headline above it was a lie.
        # Whether an action was applied is a fact, so read the fact.
        applied = await db.q(
            """
            SELECT count(*)::INT AS n
            FROM mock_action_log
            WHERE incident_id = %s AND action IN ('rollback', 'restart', 'scale_up')
            """,
            (incident_id,),
        )
        acted = bool(applied and applied[0]["n"] > 0)

        # If a real destination is bound to this tool, the message also goes
        # there. Layered on top of the mock write rather than replacing it: the
        # seeded world keeps working with nothing configured, and a connector
        # that is down cannot turn a successful notification into a failure.
        delivery = await deliver_for_tool(
            "notify_oncall",
            message,
            {
                "incident_id": incident["incident_id"],
                "kind": incident["kind"],
                "severity": incident["severity"],
                "service_name": incident["service_name"],
                "service_tier": incident["service_tier"],
                "decision": "remediated" if acted else "no_action",
            },
            idempotency_key or f"notify:{incident_id}:{notification_id}",
            db,
        )
        if delivery is not None:
            result["delivered_to"] = delivery

        return result
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
