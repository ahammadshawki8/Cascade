"""The facts a rule may reason about.

A predicate names fields; this is what supplies them. Keeping the mapping in one
place means the rule builder in the UI, the validator that rejects a bad rule at
authoring time, and the evaluator that runs it are all talking about the same
vocabulary.

`domain_facts` in the database is the authoritative list, because the UI reads
it and a field that exists only in Python could be offered by neither. The
constant below is the fallback for stub mode, where there is no database at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Fallback vocabulary, mirroring what migration 006 seeds. The database wins
# wherever it is reachable.
DOMAIN_FACTS: dict[str, list[dict[str, Any]]] = {
    "incident": [
        {"field": "kind", "kind": "string", "label": "What kind of failure",
         "choices": ["bad_deploy", "error_spike", "resource_exhaustion"]},
        {"field": "severity", "kind": "string", "label": "Reported severity",
         "choices": ["P1", "P2", "P3"]},
        {"field": "service_name", "kind": "string", "label": "Service name",
         "choices": None},
        {"field": "service_tier", "kind": "number",
         "label": "Service tier (1 = most critical)", "choices": None},
        {"field": "state", "kind": "string", "label": "Incident state",
         "choices": ["open", "mitigated", "resolved", "escalated"]},
        {"field": "deploy_age_hours", "kind": "number",
         "label": "Hours since the last deploy", "choices": None},
        {"field": "error_rate", "kind": "number", "label": "Error rate",
         "choices": None},
        {"field": "cpu_usage", "kind": "number", "label": "CPU usage",
         "choices": None},
        {"field": "action", "kind": "string", "label": "Action being proposed",
         "choices": ["rollback", "restart", "scale_up"]},
        {"field": "prior_actions", "kind": "number",
         "label": "Automated actions already applied", "choices": None},
    ]
}


def build_incident_facts(
    incident: dict[str, Any],
    action: str | None = None,
    prior_actions: int = 0,
) -> dict[str, Any]:
    """Flatten an incident row into the fact dictionary a predicate reads.

    `deploy_age_hours` is derived rather than stored: rules are written about
    how old a deploy is, not about when it happened, and doing the subtraction
    here means a rule author never has to express a date comparison.

    A missing deploy timestamp yields None rather than a sentinel, so the
    evaluator reports it as unknown instead of treating a service that has never
    deployed as one that deployed at the epoch.
    """
    deployed_at = incident.get("deploy_timestamp")
    deploy_age_hours: float | None = None
    if isinstance(deployed_at, datetime):
        now = datetime.now(deployed_at.tzinfo or UTC)
        deploy_age_hours = (now - deployed_at).total_seconds() / 3600

    return {
        "incident_id": incident.get("incident_id"),
        "kind": incident.get("kind"),
        "severity": incident.get("severity"),
        "service_name": incident.get("service_name"),
        "service_tier": incident.get("service_tier"),
        "state": incident.get("state"),
        "deploy_age_hours": deploy_age_hours,
        "error_rate": incident.get("error_rate"),
        "cpu_usage": incident.get("cpu_usage"),
        "action": action,
        "prior_actions": prior_actions,
    }


async def known_fields(db, domain: str = "incident") -> set[str]:
    """The field names a rule in this domain may reference.

    Falls back to the constant when `domain_facts` is unreachable — a validator
    that fails open on an infrastructure hiccup would let a typo through, but
    one that fails closed would block rule authoring entirely on a table that is
    pure metadata. The constant is the same list, so falling back to it is not a
    weakening.
    """
    try:
        rows = await db.q(
            "SELECT field FROM domain_facts WHERE domain = %s", (domain,)
        )
        if rows:
            return {r["field"] for r in rows}
    except Exception:
        pass
    return {f["field"] for f in DOMAIN_FACTS.get(domain, [])}
