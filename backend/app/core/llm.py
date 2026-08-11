"""LLM clients — planner, fast calls, embeddings (spec §2, §5.4).

OWNER: Shawki (Track B).

Three capabilities, each with a provider chain (see `providers.py`):

    AgentClient  plan with tools   bedrock -> groq -> openrouter -> local planner
    FastClient   short completion  bedrock -> groq -> openrouter -> caller's fallback
    EmbedClient  1024-d vector     bedrock -> huggingface        -> local embedder

DEGRADED MODE
-------------
Falling back is never silent. `llm_status()` reports "degraded" the moment
anything below the primary provider serves a request, `/api/metrics` carries it
as `llm`, the metric bar shows an amber dot, and `/api/admin/smoke` names the
provider actually in use.

The local planner is not a latency simulation. It makes the same tool calls a
competent planner would, instantly — so cold-vs-guided timing is only
meaningful when a real model is serving.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Callable
from typing import Any

from . import providers
from .providers import EMBED_DIM

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Budgets & failure handling (spec §5.4)
# ---------------------------------------------------------------------------


class BudgetExceeded(Exception):
    """Task hit its step / token / wall-clock ceiling."""


class CircuitBreakerOpen(Exception):
    """Too many consecutive failures; stop calling for a while."""


class CircuitBreaker:
    """Opens after `failure_threshold` consecutive failures, for `timeout` s."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 30) -> None:
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time: float | None = None
        self.state = "closed"

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"

    def check(self) -> None:
        if self.state != "open":
            return
        if self.last_failure_time and time.time() - self.last_failure_time > self.timeout:
            self.state = "half_open"
            self.failures = 0
            return
        raise CircuitBreakerOpen("llm circuit breaker open")


_circuit_breaker = CircuitBreaker()


class BudgetTracker:
    """Per-task resource ceiling. `record_step` raises once a limit is hit."""

    def __init__(
        self,
        max_steps: int = 15,
        max_tokens: int = 25_000,
        max_wall_clock: int = 60,
    ) -> None:
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.max_wall_clock = max_wall_clock
        self.steps = 0
        self.tokens = 0
        self.start_time: float | None = None

    def start(self) -> None:
        self.start_time = time.time()

    def check(self) -> None:
        if self.steps >= self.max_steps:
            raise BudgetExceeded(f"step budget: {self.steps} >= {self.max_steps}")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"token budget: {self.tokens} >= {self.max_tokens}")
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            if elapsed >= self.max_wall_clock:
                raise BudgetExceeded(
                    f"wall clock: {elapsed:.1f}s >= {self.max_wall_clock}s"
                )

    def record_step(self, tokens_used: int = 0) -> None:
        self.steps += 1
        self.tokens += tokens_used
        self.check()


# ---------------------------------------------------------------------------
# Degradation tracking
# ---------------------------------------------------------------------------

_degraded_reason: str | None = None
_active_provider: str | None = None


def mark_degraded(reason: str) -> None:
    global _degraded_reason
    if _degraded_reason is None:
        log.warning("LLM degraded: %s", reason)
    _degraded_reason = reason


def note_provider(name: str) -> None:
    """Record which provider served the most recent call."""
    global _active_provider
    _active_provider = name
    if name != "bedrock":
        mark_degraded(f"served by {name} rather than Bedrock")


def llm_status() -> str:
    """"ok" only while Bedrock is serving; anything else is degraded."""
    if _degraded_reason is None and _active_provider is None:
        # Probe rather than wait for the first call, so a freshly started
        # process reports honestly instead of showing green until something runs.
        if providers.bedrock_client() is None:
            chain = providers.available_openai_providers()
            if chain:
                mark_degraded(f"no Bedrock credentials; using {chain[0]}")
            else:
                mark_degraded("no LLM provider configured; using local planner")
    return "degraded" if _degraded_reason else "ok"


def active_provider() -> str | None:
    return _active_provider


def serving_provider() -> str:
    """Which provider is serving *chat*, for the persistent status indicator.

    Deliberately not `active_provider()`, which records whichever provider was
    hit most recently. Chat and embeddings fall back independently, so that
    value flaps between "groq" and "huggingface" depending on whether the last
    thing to run was a plan or an embed, and a status light that changes on its
    own tells the operator nothing.

    It also answers before the first call, where `active_provider()` is still
    None: reporting "local" then would name the deterministic planner while a
    perfectly good Groq key sits configured. `/api/admin/smoke` remains the
    place that reports chat and embeddings separately.
    """
    if providers.bedrock_client() is not None:
        return "bedrock"
    chain = providers.available_openai_providers()
    if chain:
        return chain[0]
    return "local"


def degraded_reason() -> str | None:
    return _degraded_reason


def reset_degraded() -> None:
    """Test helper — clears the sticky degraded flags."""
    global _degraded_reason, _active_provider
    _degraded_reason = None
    _active_provider = None


# ---------------------------------------------------------------------------
# Deterministic local embedding
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """a an the and or of to for in on at is are be was were with by from as that this
    it its if then than so we you i they he she them us our your their""".split()
)

_INCIDENT_RE = re.compile(r"\binc[-_ ]?\d+\b", re.IGNORECASE)
_NUM_RE = re.compile(r"\b\d+\b")
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Normalize away instance identifiers, then split into content tokens.

    Incident ids are *parameters*, not intent: "Remediate INC-1001" and
    "Remediate INC-1002" describe the same skill and must land on the same
    vector. Collapsing them is what lets the guided path recognise a second
    incident of a class it has already learned.
    """
    lowered = _INCIDENT_RE.sub(" incidentref ", text.lower())
    lowered = _NUM_RE.sub(" num ", lowered)
    return [t for t in _TOKEN_RE.findall(lowered) if t not in _STOPWORDS and len(t) > 1]


def _hash_bucket(token: str) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % EMBED_DIM, 1.0 if (value >> 63) & 1 else -1.0


def local_embed(text: str) -> list[float]:
    """L2-normalized 1024-d signed-hash bag of unigrams + bigrams.

    Deterministic, dependency-free, and metric-compatible with a real embedder
    (unit vectors => L2 ranking equals cosine ranking, decision D2).
    """
    tokens = _tokenize(text)
    vector = [0.0] * EMBED_DIM

    for token in tokens:
        idx, sign = _hash_bucket(token)
        vector[idx] += sign
    # strict=False is intentional: tokens[1:] is one shorter by construction.
    for left, right in zip(tokens, tokens[1:], strict=False):
        idx, sign = _hash_bucket(f"{left}_{right}")
        vector[idx] += sign * 0.5

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


# ---------------------------------------------------------------------------
# Shared chat routing
# ---------------------------------------------------------------------------


def _settings() -> Any:
    from app.config import settings

    return settings


async def _chat(
    system: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1024,
    fast: bool = False,
) -> dict[str, Any] | None:
    """Try each provider in order. Returns a normalized reply, or None.

    Normalized shape:
        {"text": str, "tool_calls": [{"id","name","args"}], "tokens": int}
    """
    settings = _settings()

    try:
        _circuit_breaker.check()
    except CircuitBreakerOpen as exc:
        mark_degraded(str(exc))
        return None

    # 1. Bedrock (Anthropic message API)
    if providers.bedrock_client() is not None:
        model = settings.bedrock_fast_model_id if fast else settings.bedrock_agent_model_id
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        try:
            payload = await providers.bedrock_invoke(model, body)
            if payload:
                _circuit_breaker.record_success()
                note_provider("bedrock")
                return _normalize_anthropic(payload)
        except Exception:
            _circuit_breaker.record_failure()

    # 2. OpenAI-compatible providers
    openai_messages = _to_openai_messages(system, messages)
    openai_tools = providers.to_openai_tools(tools) if tools else None

    for name in providers.available_openai_providers():
        spec = providers._OPENAI_COMPATIBLE[name]
        model = spec["default_fast"] if fast else spec["default_chat"]
        try:
            reply = await providers.openai_chat(
                name,
                openai_messages,
                model=model,
                tools=openai_tools,
                max_tokens=max_tokens,
            )
            if reply:
                _circuit_breaker.record_success()
                note_provider(name)
                return _normalize_openai(reply)
        except Exception:
            _circuit_breaker.record_failure()
            continue

    mark_degraded("no chat provider available")
    return None


def _normalize_anthropic(payload: dict[str, Any]) -> dict[str, Any]:
    text_parts, tool_calls = [], []
    for block in payload.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "name": block.get("name", ""),
                    "args": block.get("input") or {},
                }
            )
    usage = payload.get("usage", {})
    return {
        "text": "\n".join(p for p in text_parts if p).strip(),
        "tool_calls": tool_calls,
        "tokens": int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        "raw_content": payload.get("content", []),
    }


def _normalize_openai(reply: dict[str, Any]) -> dict[str, Any]:
    message = reply.get("message", {})
    tool_calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        raw_args = function.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            {"id": call.get("id"), "name": function.get("name", ""), "args": args}
        )
    usage = reply.get("usage", {})
    return {
        "text": (message.get("content") or "").strip(),
        "tool_calls": tool_calls,
        "tokens": int(usage.get("total_tokens", 0)),
        "raw_message": message,
    }


def _to_openai_messages(
    system: str, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Anthropic-style history -> OpenAI chat history."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            out.append({"role": message["role"], "content": content})
            continue
        # Structured content is already OpenAI-shaped when it came from us.
        out.append(message)
    return out


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


class EmbedClient:
    """1024-d unit-length embeddings (D2)."""

    def __init__(self) -> None:
        self.dimension = EMBED_DIM

    async def embed(self, text: str) -> list[float]:
        text = (text or "").strip()[:8000] or "empty"
        settings = _settings()

        if providers.bedrock_client() is not None:
            try:
                payload = await providers.bedrock_invoke(
                    settings.bedrock_embed_model_id,
                    {"inputText": text, "dimensions": EMBED_DIM, "normalize": True},
                )
                if payload and isinstance(payload.get("embedding"), list):
                    note_provider("bedrock")
                    return [float(x) for x in payload["embedding"]]
            except Exception:
                pass

        if providers.huggingface_available():
            try:
                vector = await providers.huggingface_embed(text)
                if vector:
                    note_provider("huggingface")
                    return vector
            except Exception:
                pass

        mark_degraded("no embedding provider; using local hashed embedder")
        return local_embed(text)


class FastClient:
    """Short, cheap, structured calls."""

    async def generate(
        self, system: str, user: str, max_tokens: int = 512
    ) -> str | None:
        reply = await _chat(
            system,
            [{"role": "user", "content": user}],
            max_tokens=max_tokens,
            fast=True,
        )
        return reply["text"] if reply and reply["text"] else None

    async def check_precondition(
        self,
        spec: dict[str, Any],
        task_text: str,
        incident: dict[str, Any],
        rules: Any = None,
    ) -> dict[str, Any]:
        """-> {"ok": bool, "failed": [str]}

        This is a ROUTING decision (reuse vs explore), not a safety gate. Policy
        is enforced downstream and independently: the freshness join refuses
        stale playbooks, and the tools re-verify head rules on every call, so
        `apply_remediation` refuses an ineligible incident no matter what this
        check returns (spec 5.3). Failing closed here therefore buys no safety
        and costs the reuse the whole design exists to produce.

        `rules` is the current head rule set. Without it, a precondition like
        "deploy occurred within rollback window" is unevaluable, because the
        window lives in the rules rather than on the incident, and the model
        answers false for lack of data.
        """
        preconditions = spec.get("preconditions", [])
        if not preconditions:
            return {"ok": True, "failed": []}

        rules_block = ""
        if rules:
            rules_block = f"\nCurrent policy rules:\n{json.dumps(rules, indent=2, default=str)}\n"

        raw = await self.generate(
            system=(
                "You check whether an incident satisfies a runbook's preconditions. "
                'Reply with JSON only: {"ok": true|false, "failed": ["..."]}. '
                "List a precondition in `failed` ONLY when the data you were given "
                "clearly and specifically violates it. If a precondition cannot be "
                "evaluated from the data provided, treat it as satisfied and do NOT "
                "list it: the execution tools re-check every policy rule themselves "
                "and will refuse an ineligible action, so a missed check here is "
                "caught downstream, whereas a false failure blocks a valid runbook."
            ),
            user=(
                f"Preconditions:\n{json.dumps(preconditions, indent=2)}\n\n"
                f"Task: {task_text}\n"
                f"{rules_block}\n"
                f"Incident:\n{json.dumps(incident, indent=2, default=str)}"
            ),
            max_tokens=300,
        )
        parsed = parse_json(raw)
        if isinstance(parsed, dict) and "ok" in parsed:
            return {
                "ok": bool(parsed["ok"]),
                "failed": [str(f) for f in parsed.get("failed", [])],
            }
        return _local_precondition_check(preconditions, incident)

    async def extract_params(
        self, spec: dict[str, Any], task_text: str
    ) -> dict[str, Any]:
        declared = spec.get("params", {}) or {}
        if not declared:
            return {}

        raw = await self.generate(
            system=(
                "Extract parameter values from an operator's request. "
                "Reply with a JSON object only, one key per requested parameter."
            ),
            user=f"Parameters: {json.dumps(declared)}\nRequest: {task_text}\nReturn JSON.",
            max_tokens=200,
        )
        parsed = parse_json(raw)
        if isinstance(parsed, dict) and parsed:
            return {k: parsed[k] for k in declared if k in parsed}
        return _local_extract_params(declared, task_text)


class AgentClient:
    """The explore-loop planner, with tool calling."""

    async def converse_with_tools(
        self,
        system_prompt: str,
        initial_message: str,
        tools: list[dict[str, Any]],
        tool_executor: Callable,
        budget: BudgetTracker,
        on_step: Callable | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Loop until final_answer or budget exhaustion.

        Returns (final_answer, trajectory). Falls through to the deterministic
        planner when no provider can serve — including mid-run, so a provider
        dying does not leave the task wedged.
        """
        has_provider = (
            providers.bedrock_client() is not None
            or bool(providers.available_openai_providers())
        )
        if not has_provider:
            return await _local_plan(initial_message, tool_executor, budget, on_step)

        messages: list[dict[str, Any]] = [{"role": "user", "content": initial_message}]
        trajectory: list[dict[str, Any]] = []

        while True:
            budget.check()

            reply = await _chat(
                system_prompt, messages, tools=tools, max_tokens=1024
            )
            if reply is None:
                return await _local_plan(
                    initial_message, tool_executor, budget, on_step, trajectory
                )

            tokens = reply["tokens"]
            calls = reply["tool_calls"]

            if not calls:
                budget.record_step(tokens)
                return (
                    {"outcome": "escalated", "summary": reply["text"]},
                    trajectory,
                )

            messages.append(_assistant_turn(reply))

            results = []
            for call in calls:
                if call["name"] == "final_answer":
                    budget.record_step(tokens)
                    args = call["args"]
                    return (
                        {
                            "outcome": args.get("outcome", "success"),
                            "summary": args.get("summary", ""),
                        },
                        trajectory,
                    )

                started = time.time()
                output = await tool_executor(call["name"], call["args"], len(trajectory))
                step = {
                    "step_index": len(trajectory),
                    "tool_name": call["name"],
                    "tool_input": call["args"],
                    "tool_output": output,
                    "latency_ms": int((time.time() - started) * 1000),
                    "tokens": tokens,
                }
                trajectory.append(step)
                if on_step:
                    await on_step(step)
                tokens = 0  # attribute the turn's tokens to its first tool call

                results.append((call, output))

            messages.extend(_tool_result_turns(reply, results))
            budget.record_step(reply["tokens"])


def _assistant_turn(reply: dict[str, Any]) -> dict[str, Any]:
    """Echo the assistant turn back in whichever dialect produced it."""
    if "raw_content" in reply:
        return {"role": "assistant", "content": reply["raw_content"]}
    return reply.get("raw_message") or {"role": "assistant", "content": reply["text"]}


def _tool_result_turns(
    reply: dict[str, Any], results: list[tuple[dict[str, Any], Any]]
) -> list[dict[str, Any]]:
    """Tool results, shaped for the dialect that produced the call."""
    if "raw_content" in reply:  # Anthropic: one user turn holding every result
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": json.dumps(output, default=str),
                    }
                    for call, output in results
                ],
            }
        ]
    # OpenAI: one `tool` message per call
    return [
        {
            "role": "tool",
            "tool_call_id": call["id"],
            "content": json.dumps(output, default=str),
        }
        for call, output in results
    ]


# ---------------------------------------------------------------------------
# Deterministic fallbacks
# ---------------------------------------------------------------------------


def parse_json(raw: str | None) -> Any:
    """Best-effort JSON out of a model reply that may be fenced or chatty."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\{\[].*[\}\]]", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


# Kept for import compatibility.
_parse_json = parse_json

ACTION_FOR_KIND = {
    "bad_deploy": "rollback",
    "error_spike": "restart",
    "resource_exhaustion": "scale_up",
}


def _local_precondition_check(
    preconditions: list[str], incident: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate preconditions against incident fields, without a model.

    Only checks it can ground in data are enforced; anything it cannot
    interpret passes, because the eligibility tool re-checks policy anyway and
    a false block is worse than a redundant pass.
    """
    failed: list[str] = []
    kind = str(incident.get("kind", ""))
    state = str(incident.get("state", ""))

    for precondition in preconditions:
        text = precondition.lower()
        for known in ACTION_FOR_KIND:
            if known.replace("_", " ") in text.replace("_", " ") and kind != known:
                failed.append(precondition)
                break
        else:
            if "open" in text and state and state != "open":
                failed.append(precondition)

    return {"ok": not failed, "failed": failed}


def _local_extract_params(declared: dict[str, Any], task_text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    incident_match = re.search(r"INC-\d+", task_text, re.IGNORECASE)
    for name, kind in declared.items():
        if "incident" in name.lower() and incident_match:
            params[name] = incident_match.group(0).upper()
        elif kind == "int":
            number = re.search(r"\b\d+\b", task_text)
            if number:
                params[name] = int(number.group(0))
    return params


async def _local_plan(
    task_text: str,
    tool_executor: Callable,
    budget: BudgetTracker,
    on_step: Callable | None = None,
    trajectory: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Policy-faithful planner used when no model is available.

    Follows the same sequence the system prompt demands: inspect the incident,
    read the rules, check eligibility, then either remediate + notify, or
    escalate. Never remediates without a passing eligibility check.
    """
    trajectory = trajectory if trajectory is not None else []

    async def call(name: str, args: dict[str, Any]) -> Any:
        started = time.time()
        output = await tool_executor(name, args, len(trajectory))
        step = {
            "step_index": len(trajectory),
            "tool_name": name,
            "tool_input": args,
            "tool_output": output,
            "latency_ms": int((time.time() - started) * 1000),
            "tokens": 0,
        }
        trajectory.append(step)
        if on_step:
            await on_step(step)
        budget.record_step(0)
        return output

    match = re.search(r"INC-\d+", task_text, re.IGNORECASE)
    if not match:
        return (
            {"outcome": "escalated", "summary": "No incident reference in request."},
            trajectory,
        )
    incident_id = match.group(0).upper()

    incident = await call("get_incident", {"incident_id": incident_id})
    if isinstance(incident, dict) and incident.get("error"):
        return (
            {"outcome": "escalated", "summary": f"Incident {incident_id} not found."},
            trajectory,
        )

    await call("get_rules", {"domain": "incident"})

    action = ACTION_FOR_KIND.get(str(incident.get("kind", "")), "restart")
    eligibility = await call(
        "check_remediation_eligibility",
        {"incident_id": incident_id, "action": action},
    )

    if not (isinstance(eligibility, dict) and eligibility.get("eligible")):
        reasons = "; ".join(eligibility.get("reasons", [])) or "policy check failed"
        await call(
            "notify_oncall",
            {
                "incident_id": incident_id,
                "message": f"Manual action required for {incident_id}: {reasons}",
            },
        )
        return (
            {"outcome": "escalated", "summary": f"Escalated {incident_id}: {reasons}"},
            trajectory,
        )

    remediation = await call(
        "apply_remediation", {"incident_id": incident_id, "action": action}
    )
    if isinstance(remediation, dict) and remediation.get("error"):
        return (
            {
                "outcome": "escalated",
                "summary": f"{action} failed: {remediation['error']}",
            },
            trajectory,
        )

    await call(
        "notify_oncall",
        {"incident_id": incident_id, "message": f"Applied {action} to {incident_id}"},
    )
    return (
        {
            "outcome": "success",
            "summary": f"Applied {action} to {incident_id} and notified on-call.",
        },
        trajectory,
    )


async def llm_smoke_test() -> dict[str, Any]:
    """Which provider actually answers. Surfaced at /api/admin/smoke."""
    configured = providers.configured_providers()
    results: dict[str, Any] = {
        "configured": configured,
        "chat": False,
        "embed": False,
        "chat_provider": None,
        "embed_provider": None,
        "errors": [],
    }

    reply = await _chat("Reply with OK.", [{"role": "user", "content": "ping"}], max_tokens=16)
    results["chat"] = bool(reply)
    results["chat_provider"] = active_provider() if reply else "local-deterministic"

    before = active_provider()
    vector = await EmbedClient().embed("cascade smoke test")
    results["embed"] = len(vector) == EMBED_DIM
    after = active_provider()
    results["embed_provider"] = (
        after if after != before else ("local-deterministic" if not after else after)
    )

    if degraded_reason():
        results["errors"].append(degraded_reason())
    return results


# Back-compat alias — older callers imported this name.
bedrock_smoke_test = llm_smoke_test


__all__ = [
    "AgentClient",
    "FastClient",
    "EmbedClient",
    "BudgetTracker",
    "BudgetExceeded",
    "CircuitBreakerOpen",
    "ACTION_FOR_KIND",
    "llm_smoke_test",
    "bedrock_smoke_test",
    "llm_status",
    "active_provider",
    "degraded_reason",
    "local_embed",
    "parse_json",
    "EMBED_DIM",
]
