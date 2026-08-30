"""What a notification looks like on the other end.

Three destinations, one HTTP transport. The only thing that differs between
Slack, Discord and a bare webhook is the JSON shape, which is why adding a
fourth is a function in this file rather than a change to anything that calls
it.
"""

from __future__ import annotations

from typing import Any

# Incident severity to a colour the destination understands. Slack takes a hex
# string on an attachment; Discord takes the same value as an integer.
_COLOURS = {
    "P1": "#e5484d",
    "P2": "#e6a84a",
    "P3": "#5dd181",
}
_DEFAULT_COLOUR = "#7c7f93"


def _colour(severity: str | None) -> str:
    return _COLOURS.get((severity or "").upper(), _DEFAULT_COLOUR)


def _headline(context: dict[str, Any]) -> str:
    """Say only what is known to have happened.

    Every branch here corresponds to a fact the caller looked up, never to a
    guess about what a message meant. A notification card that overstates the
    outcome is worse than a vague one: it is the only part of this an on-call
    engineer reads before deciding whether to get out of bed.
    """
    incident = context.get("incident_id") or "an incident"
    decision = context.get("decision")
    if decision == "remediated":
        return f"Cascade remediated {incident}"
    if decision == "no_action":
        return f"Cascade took no automated action on {incident}"
    if decision == "refused":
        return f"Cascade refused an automated action on {incident}"
    if decision == "escalated":
        return f"Cascade escalated {incident}"
    return f"Cascade update on {incident}"


def slack(message: str, context: dict[str, Any]) -> dict[str, Any]:
    """Block Kit. Renders as a card rather than a line of text.

    The fields are the ones an on-call engineer needs before deciding whether to
    open the console: what happened, to what, and what the system did about it.
    """
    fields = []
    for label, key in (
        ("Service", "service_name"),
        ("Tier", "service_tier"),
        ("Kind", "kind"),
        ("Severity", "severity"),
    ):
        value = context.get(key)
        if value not in (None, ""):
            fields.append({"type": "mrkdwn", "text": f"*{label}*\n{value}"})

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": _headline(context)[:150]},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message[:2900]}},
    ]
    if fields:
        blocks.append({"type": "section", "fields": fields[:10]})

    rule = context.get("rule_basis")
    if rule:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Policy consulted: `{rule}`"}
                ],
            }
        )

    return {
        "text": _headline(context),  # notification fallback, and required
        "attachments": [
            {"color": _colour(context.get("severity")), "blocks": blocks}
        ],
    }


def discord(message: str, context: dict[str, Any]) -> dict[str, Any]:
    """Embed. Same information, Discord's shape."""
    fields = []
    for label, key in (
        ("Service", "service_name"),
        ("Tier", "service_tier"),
        ("Kind", "kind"),
        ("Severity", "severity"),
    ):
        value = context.get(key)
        if value not in (None, ""):
            fields.append({"name": label, "value": str(value), "inline": True})

    embed: dict[str, Any] = {
        "title": _headline(context)[:250],
        "description": message[:4000],
        "color": int(_colour(context.get("severity")).lstrip("#"), 16),
    }
    if fields:
        embed["fields"] = fields[:25]
    if context.get("rule_basis"):
        embed["footer"] = {"text": f"Policy consulted: {context['rule_basis']}"[:2000]}

    return {"username": "Cascade", "embeds": [embed]}


def webhook(message: str, context: dict[str, Any]) -> dict[str, Any]:
    """Structured JSON, for anything that is not a chat product."""
    return {
        "source": "cascade",
        "event": "incident.notification",
        "headline": _headline(context),
        "message": message,
        **{k: v for k, v in context.items() if v not in (None, "")},
    }


BUILDERS = {"slack": slack, "discord": discord, "webhook": webhook}
KINDS = tuple(BUILDERS)


def build(kind: str, message: str, context: dict[str, Any]) -> dict[str, Any]:
    return BUILDERS.get(kind, webhook)(message, context)
