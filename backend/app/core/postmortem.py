"""Postmortem generation (T1.3, spec §9).

OWNER: Shawki (Track B).

Turns a finished episode into the writeup an engineer would otherwise spend an
hour on: timeline, which policy was consulted, what the agent decided and why,
and what a human should check.

The body is stored inline in `postmortems.body` and *also* pushed to S3 when a
bucket is configured. Inline is the source of truth for the UI, so the feature
works with no AWS at all; S3 is for durability and for anything downstream that
wants the raw file.

When no model is available the deterministic renderer produces the same
structure from the trajectory. It reads as drier prose, but every fact in it is
grounded in a recorded tool call rather than generated.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

_SYSTEM = """You write concise incident postmortems for an SRE team.

Given a trajectory of tool calls, produce markdown with exactly these sections:

## Summary
One paragraph: what happened and how it ended.

## Timeline
A bullet per step: what was called, what came back.

## Policy applied
Which rules were consulted and what they permitted or blocked. Cite rule keys.

## Outcome
Remediated or escalated, and why.

## Follow-ups
2-4 concrete checks a human should perform.

Be factual. Use only what the trajectory shows. Never invent a cause."""


async def generate_postmortem(episode_id: UUID, db) -> str:
    """Generate and store a postmortem. Returns the S3 key or a local marker.

    Idempotent: `postmortems.episode_id` is UNIQUE, and a second call returns
    the existing record rather than regenerating.
    """
    existing = await db.q(
        "SELECT s3_key FROM postmortems WHERE episode_id = %s", (str(episode_id),)
    )
    if existing:
        return existing[0]["s3_key"] or f"postmortems/{episode_id}.md"

    context = await _load_context(episode_id, db)
    if context is None:
        raise ValueError(f"episode {episode_id} not found")

    body = await _render(context)
    summary = _first_paragraph(body)

    s3_key = await _upload(episode_id, body)

    await db.q(
        """
        INSERT INTO postmortems (episode_id, s3_key, summary, body)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (episode_id) DO NOTHING
        """,
        (str(episode_id), s3_key, summary[:2000], body),
    )
    log.info("postmortem written for episode %s", episode_id)
    return s3_key or f"postmortems/{episode_id}.md"


async def _load_context(episode_id: UUID, db) -> dict[str, Any] | None:
    rows = await db.q(
        """
        SELECT e.episode_id, e.outcome, e.mode, e.steps, e.latency_ms, e.tokens,
               e.created_at, t.task_id, t.input, t.status, t.result
        FROM episodes e
        JOIN tasks t ON t.task_id = e.task_id
        WHERE e.episode_id = %s
        """,
        (str(episode_id),),
    )
    if not rows:
        return None
    context = dict(rows[0])

    # The trajectory lives in the compile outbox payload (episodes has no
    # column for it), so recover it from there when the row still exists.
    payload_rows = await db.q(
        """
        SELECT payload FROM outbox
        WHERE kind = 'compile' AND payload ->> 'episode_id' = %s
        LIMIT 1
        """,
        (str(episode_id),),
    )
    trajectory = []
    if payload_rows:
        payload = payload_rows[0]["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        trajectory = payload.get("trajectory") or []
    context["trajectory"] = trajectory
    return context


async def _render(context: dict[str, Any]) -> str:
    from .llm import FastClient

    trajectory = context.get("trajectory") or []
    if trajectory:
        prompt = (
            f"Request: {context['input']}\n"
            f"Outcome: {context['outcome']} ({context.get('result') or 'n/a'})\n"
            f"Mode: {context['mode']} · {context['steps']} steps · "
            f"{context['latency_ms']}ms\n\n"
            f"Trajectory:\n{json.dumps(_trim(trajectory), indent=2, default=str)}"
        )
        generated = await FastClient().generate(
            system=_SYSTEM, user=prompt, max_tokens=1200
        )
        if generated:
            return generated.strip()

    return _render_locally(context)


def _render_locally(context: dict[str, Any]) -> str:
    """Deterministic renderer — every line grounded in a recorded tool call."""
    trajectory = context.get("trajectory") or []
    outcome = context.get("outcome", "unknown")
    result = context.get("result") or "n/a"

    incident = _first_output(trajectory, "get_incident") or {}
    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    rules_used = eligibility.get("rule_versions_used") or {}
    reasons = eligibility.get("reasons") or []

    lines: list[str] = []
    lines.append(f"# Postmortem — {context.get('input', 'incident')}")
    lines.append("")
    lines.append("## Summary")
    if incident:
        lines.append(
            f"A `{incident.get('kind', 'unknown')}` incident "
            f"(`{incident.get('incident_id', '?')}`, severity "
            f"{incident.get('severity', '?')}) was raised on "
            f"`{incident.get('service_name', '?')}` "
            f"(tier {incident.get('service_tier', '?')}). "
            f"The agent ran in **{context.get('mode')}** mode across "
            f"{context.get('steps')} steps in {context.get('latency_ms')}ms and "
            f"the task ended as **{result}**."
        )
    else:
        lines.append(
            f"The task ended as **{result}** after {context.get('steps')} steps."
        )
    lines.append("")

    lines.append("## Timeline")
    for entry in trajectory:
        tool = entry.get("tool_name", "?")
        args = entry.get("tool_input", {}) or {}
        arg_text = ", ".join(f"{k}={v}" for k, v in args.items() if k != "idempotency_key")
        output = entry.get("tool_output")
        note = ""
        if isinstance(output, dict):
            if output.get("error"):
                note = f" → error: {output['error']}"
            elif "eligible" in output:
                note = f" → eligible={output['eligible']}"
            elif output.get("success") or output.get("sent"):
                note = " → ok"
        lines.append(
            f"- `{tool}({arg_text})` · {entry.get('latency_ms', 0)}ms{note}"
        )
    if not trajectory:
        lines.append("- No trajectory was recorded for this episode.")
    lines.append("")

    lines.append("## Policy applied")
    if rules_used:
        for rule_key, version in rules_used.items():
            lines.append(f"- `{rule_key}` v{version}")
    else:
        lines.append("- No eligibility check was recorded.")
    if reasons:
        lines.append("")
        lines.append("Policy blocked the automated action because:")
        for reason in reasons:
            lines.append(f"- {reason}")
    lines.append("")

    lines.append("## Outcome")
    lines.append(
        f"- Episode outcome: **{outcome}**\n- Task result: **{result}**"
    )
    lines.append("")

    lines.append("## Follow-ups")
    if reasons:
        lines.append("- Confirm whether the blocking policy is still the intent.")
        lines.append("- Decide whether this incident class warrants a policy change.")
    else:
        lines.append("- Verify the remediation actually restored service health.")
        lines.append("- Confirm the on-call notification was received.")
    lines.append("- Check whether a runbook should be compiled or updated from this run.")
    lines.append("")
    lines.append(
        "_Generated by Cascade from the recorded trajectory. "
        "Every statement above is grounded in a logged tool call._"
    )
    return "\n".join(lines)


async def _upload(episode_id: UUID, body: str) -> str | None:
    from app.config import settings

    bucket = settings.episodes_bucket
    if not bucket or bucket.endswith("-local"):
        return None

    key = f"postmortems/{episode_id}.md"
    try:
        import asyncio

        import boto3

        client = boto3.client("s3", region_name=settings.aws_region)
        await asyncio.to_thread(
            client.put_object,
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/markdown",
        )
        return key
    except Exception as exc:
        log.warning("postmortem upload failed: %s", exc)
        return None


def _first_output(trajectory: list[dict], tool: str) -> dict | None:
    for entry in trajectory:
        if entry.get("tool_name") == tool and isinstance(entry.get("tool_output"), dict):
            return entry["tool_output"]
    return None


def _first_paragraph(body: str) -> str:
    for block in body.split("\n\n"):
        cleaned = block.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned
    return body[:400]


def _trim(trajectory: list[dict]) -> list[dict]:
    return [
        {
            "step": e.get("step_index"),
            "tool": e.get("tool_name"),
            "input": e.get("tool_input"),
            "output": e.get("tool_output"),
            "latency_ms": e.get("latency_ms"),
        }
        for e in trajectory[:12]
    ]
