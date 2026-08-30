"""The two baselines Cascade is measured against.

Not imported by the running application.

Two reasonable basic ways to handle this task without Cascade, and the two a
competent engineer would actually reach for:

  single_prompt   one direct prompt with basic instructions
  naive_cache     the memory system everybody builds: store what worked, match
                  it by similarity, replay it

FAIRNESS
--------
Both arms call `llm._chat`, which is the same function Cascade's own planner
calls. Same provider chain, same model (`bedrock_agent_model_id`, Claude Sonnet
4.6), same retry and circuit-breaker behaviour. Nothing here is throttled,
prompted badly on purpose, or given a smaller model. If Cascade wins, it has to
be the architecture that won.

Both arms are also handed the *current* policy on every call, with the live
parameter values substituted in. This matters most for `naive_cache` in phase
two: it is not being asked to guess at a rule it was never shown. It is shown
the new rule, and it also holds a remembered procedure that was correct under
the old one. Whether it notices the conflict is the entire question.

Reaching into a private function is deliberate. The public path runs the tool
executor, and Cascade's tools enforce policy independently of what the model
says — so a baseline built on it would inherit the very safety property under
test and the comparison would measure nothing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.core.llm import _chat

from eval.cases import ESCALATE, REMEDIATE, Case

_JSON = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Decision:
    """One arm's answer on one case."""

    decision: str
    rationale: str
    latency_ms: int
    tokens: int
    raw: str = ""
    error: str | None = None


_INSTRUCTIONS = """You are an incident response agent for an on-call team.

You will be given one incident and the operational policy currently in force.
Decide whether to apply the remediation automatically, or to escalate it to a
human.

Answer with JSON and nothing else:

{"decision": "remediate" | "escalate", "rationale": "<one sentence>"}

Escalate if policy does not permit the action. Remediate only if it does."""

def _incident_block(case: Case) -> str:
    """The incident as facts, not prose.

    Handing the model a paragraph to parse would make this a reading
    comprehension test rather than a policy test, and any error would be
    ambiguous between the two.
    """
    facts = {
        k: v
        for k, v in case.facts.items()
        if v is not None and k not in {"prior_actions"}
    }
    if isinstance(facts.get("deploy_age_hours"), float):
        facts["deploy_age_hours"] = round(facts["deploy_age_hours"], 2)
    return json.dumps(facts, indent=2, default=str)


def _parse(reply: dict[str, Any] | None) -> tuple[str, str, str]:
    """Pull a decision out of the reply.

    An unparseable answer counts as ESCALATE rather than as a discarded run. A
    system that cannot say what it wants to do has not thereby earned the right
    to act, and silently dropping these would flatter whichever arm produced
    them.
    """
    if not reply:
        return ESCALATE, "no reply from provider", ""
    text = (reply.get("text") or "").strip()
    match = _JSON.search(text)
    if not match:
        return ESCALATE, "unparseable reply", text
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return ESCALATE, "malformed JSON in reply", text
    decision = str(parsed.get("decision", "")).strip().lower()
    rationale = str(parsed.get("rationale", "")).strip()
    if decision not in {REMEDIATE, ESCALATE}:
        return ESCALATE, f"unrecognised decision {decision!r}", text
    return decision, rationale, text


async def _ask(system: str, user: str) -> Decision:
    started = time.perf_counter()
    try:
        reply = await _chat(system, [{"role": "user", "content": user}], max_tokens=400)
    except Exception as exc:  # noqa: BLE001 — an arm failing is data, not a crash
        elapsed = int((time.perf_counter() - started) * 1000)
        return Decision(ESCALATE, "provider error", elapsed, 0, error=str(exc))
    elapsed = int((time.perf_counter() - started) * 1000)
    decision, rationale, raw = _parse(reply)
    return Decision(
        decision=decision,
        rationale=rationale,
        latency_ms=elapsed,
        tokens=int((reply or {}).get("tokens") or 0),
        raw=raw,
    )


async def single_prompt(case: Case, policy: str) -> Decision:
    """Reason from the incident and the policy, every time, from scratch.

    No memory at all, which is the point: it cannot carry a stale procedure
    forward because it carries nothing forward. Expect it to be competitive on
    correctness and expensive on every axis that matters operationally, and
    expect it to re-derive the same answer to the same question all day.
    """
    user = (
        f"POLICY CURRENTLY IN FORCE\n{policy}\n\n"
        f"INCIDENT\n{_incident_block(case)}\n\n"
        f"PROPOSED ACTION: {case.action}"
    )
    return await _ask(_INSTRUCTIONS, user)


_CACHE_INSTRUCTIONS = _INSTRUCTIONS + """

You also have a runbook from your memory that resolved a very similar incident
before. Reuse it when it applies."""

async def naive_cache(case: Case, policy: str, runbook: str) -> Decision:
    """Retrieve a remembered runbook and replay it.

    This is the honest strawman, and the reason it is worth building: it is what
    almost every agent memory system does. Store the successful trajectory,
    match the next incident against it, replay the steps.

    It has no provenance. The runbook records what was done and the conditions
    that held when it was learned, and nothing anywhere records *which version*
    of which rule those conditions came from. So when a rule moves, there is no
    join that could notice, and no field that goes false. The runbook goes on
    looking exactly as healthy as it did the day it was written.
    """
    user = (
        f"POLICY CURRENTLY IN FORCE\n{policy}\n\n"
        f"RUNBOOK FROM MEMORY (matched this incident)\n{runbook}\n\n"
        f"INCIDENT\n{_incident_block(case)}\n\n"
        f"PROPOSED ACTION: {case.action}"
    )
    return await _ask(_CACHE_INSTRUCTIONS, user)


def remembered_runbook(case: Case, policy_at_learn_time: str) -> str:
    """What a provenance-free memory would have stored for this class of incident.

    Written the way such a system stores things: the procedure, and the
    conditions that were true when it succeeded, flattened into prose with the
    parameter values of the day baked into the sentence. That flattening is not
    a strawman detail, it is the actual failure. Once "within the 24 hour
    rollback window" is a string in a stored document, no amount of later policy
    change can reach back and alter it, and nothing in the system is tracking
    that it should.
    """
    return (
        f"Runbook: automatic {case.action} for {case.kind}\n"
        f"Learned from: a {case.kind} incident that was resolved successfully.\n"
        f"Steps:\n"
        f"  1. check remediation eligibility for the incident\n"
        f"  2. apply {case.action}\n"
        f"  3. notify on-call\n"
        f"Conditions that held when this was learned:\n"
        f"{policy_at_learn_time}\n"
        f"Outcome: remediated successfully, no escalation needed."
    )
