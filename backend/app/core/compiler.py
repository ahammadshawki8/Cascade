"""Trajectory -> playbook compiler (spec §6.1, §6.2).

OWNER: Shawki (Track B).

A successful explore run is just a list of tool calls. Compiling turns it into
a reusable skill:

    1. extract a PlaybookSpec   (Claude Sonnet, deterministic fallback)
    2. parse it with Pydantic   — unparseable output is rejected, not repaired
    3. ground rule citations    against the rule versions the run actually read
    4. safety lint              (whitelist, bounds, eligibility-before-action)
    5. dedup                    against near-identical existing playbooks
    6. embed + insert           playbooks + playbook_deps + audit, one txn

Step 3 is what makes unlearning possible. A citation the trajectory cannot
corroborate is dropped rather than trusted — a playbook whose provenance is
invented would never go stale when the rule behind it changed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from .confidence import INITIAL_CONFIDENCE
from .models import PlaybookSpec, RuleCitation, Step
from .retrieval import dedup_check, to_vector_literal

log = logging.getLogger(__name__)

ALLOWED_TOOLS = frozenset(
    {
        "get_incident",
        "get_rules",
        "check_remediation_eligibility",
        "apply_remediation",
        "notify_oncall",
    }
)

MAX_STEPS = 8
MIN_STEPS = 2

_INCIDENT_RE = re.compile(r"INC-\d+", re.IGNORECASE)


class CompilationRejected(ValueError):
    """The trajectory did not yield a safe, well-formed playbook."""


async def compile_playbook(
    episode_id: UUID,
    task_id: UUID,
    trajectory: list[dict[str, Any]],
    db,
    task_text: str = "",
    agent_client=None,
    embed_client=None,
    supersedes: UUID | None = None,
) -> UUID | None:
    """Compile one successful episode. Returns the playbook id, or None if deduped.

    Raises CompilationRejected when the trajectory cannot produce a valid spec —
    the caller records that in audit_log rather than retrying forever.
    """
    if not trajectory:
        raise CompilationRejected("empty trajectory")

    spec = await _extract_spec(trajectory, task_text, agent_client)
    deps = _ground_citations(spec, trajectory)
    if not deps:
        raise CompilationRejected(
            "no rule citation could be corroborated against the trajectory"
        )

    violations = _safety_lint(spec)
    if violations:
        raise CompilationRejected("; ".join(violations))

    name = _derive_name(spec, trajectory)
    domain = "incident"

    if embed_client is None:
        from .llm import EmbedClient

        embed_client = EmbedClient()

    # Index by the *request that triggered this skill*, not by its description.
    # Retrieval compares against an operator's phrasing ("Remediate INC-1002"),
    # so the stored vector must live in that same space — query-to-query, not
    # query-to-document. Embedding the goal and preconditions instead put a
    # ~30-token document against a 2-token query, which pushed even
    # exact-family matches past the L2 threshold; and since every playbook
    # shares the same precondition boilerplate, it also made genuinely
    # different runbooks look alike. The goal stays out of the vector and is
    # what the precondition check reads instead.
    embedding_text = (task_text or spec.goal).strip()
    embedding = await embed_client.embed(embedding_text)

    if not supersedes:
        duplicate = await dedup_check(embedding, domain, db)
        if duplicate:
            log.info("playbook %s already covers this trajectory — reinforcing", duplicate)
            await db.q(
                """
                UPDATE playbooks
                SET uses = uses + 1, successes = successes + 1, updated_at = now()
                WHERE playbook_id = %s
                """,
                (str(duplicate),),
            )
            return None

    return await _insert_playbook(
        spec=spec,
        name=name,
        domain=domain,
        embedding=embedding,
        deps=deps,
        supersedes=supersedes,
        db=db,
    )


# ---------------------------------------------------------------------------
# Spec extraction
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """You compile a successful incident-response trajectory \
into a reusable runbook.

Return JSON only, matching exactly:
{
  "goal": "one sentence describing what this runbook accomplishes",
  "preconditions": ["when this runbook applies", ...],   // 1-6 entries
  "params": {"incident_id": "string"},                    // "string" or "int"
  "steps": [{"tool": "...", "args": {"k": "v"}}],         // 2-8 entries
  "rule_citations": [
    {"rule_key": "...", "rule_version": 1, "used_in_step": 0, "why": "..."}
  ]
}

Rules:
- Use only these tools: get_incident, get_rules, check_remediation_eligibility,
  apply_remediation, notify_oncall.
- Replace the concrete incident id with the placeholder {incident_id}.
- apply_remediation must be preceded by check_remediation_eligibility.
- Never include idempotency_key; the executor injects it.
- Cite only rule_keys that appear in the trajectory's get_rules output.
- Preconditions state when this runbook applies IN GENERAL. They must not
  encode incidental properties of the one incident it was learned from: no
  specific severity (P1, P2, ...), no specific service name, no specific
  incident id, no specific timestamp or date. A precondition only the training
  incident can satisfy makes the runbook permanently unreusable.
  Prefer the conditions policy actually gates on: incident kind, incident
  state, service tier, and how long ago the deploy happened."""


async def _extract_spec(
    trajectory: list[dict[str, Any]], task_text: str, agent_client
) -> PlaybookSpec:
    """Claude Sonnet extraction, falling back to a structural derivation."""
    if agent_client is None:
        from .llm import FastClient

        agent_client = FastClient()

    raw = await agent_client.generate(
        system=_EXTRACTION_SYSTEM,
        user=(
            f"Operator request: {task_text}\n\n"
            f"Trajectory:\n{json.dumps(_summarize(trajectory), indent=2, default=str)}"
        ),
        max_tokens=1500,
    )

    if raw:
        from .llm import _parse_json

        parsed = _parse_json(raw)
        if isinstance(parsed, dict):
            try:
                return PlaybookSpec.model_validate(parsed)
            except Exception as exc:
                # A malformed spec is a rejection signal, not something to patch
                # up — fall through to the structural path, which is grounded.
                log.warning("LLM spec failed schema validation, deriving instead: %s", exc)

    return _derive_spec(trajectory, task_text)


def _derive_spec(trajectory: list[dict[str, Any]], task_text: str) -> PlaybookSpec:
    """Build a spec directly from what the run actually did.

    Every field is grounded in observed data, so this is the safe path when the
    model is unavailable — it can under-generalize, never hallucinate.
    """
    incident = _first_output(trajectory, "get_incident") or {}
    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    kind = str(incident.get("kind", "incident"))
    action = str(eligibility.get("action", "remediation"))

    steps: list[Step] = []
    for entry in trajectory:
        tool = entry.get("tool_name")
        if tool not in ALLOWED_TOOLS:
            continue
        steps.append(Step(tool=tool, args=_parameterize(entry.get("tool_input", {}))))

    if len(steps) < MIN_STEPS:
        raise CompilationRejected(
            f"trajectory has {len(steps)} reusable steps, need at least {MIN_STEPS}"
        )
    steps = steps[:MAX_STEPS]

    preconditions = [f"Incident kind is {kind}", "Incident state is open"]
    for reason_source, text in (
        ("incident.auto_remediate_tier", "Service tier is within the automation floor"),
        ("incident.rollback_window", "Last deploy is inside the rollback window"),
    ):
        if reason_source in (eligibility.get("rule_versions_used") or {}):
            preconditions.append(text)

    citations = [
        RuleCitation(
            rule_key=rule_key,
            rule_version=int(version),
            used_in_step=_index_of(steps, "check_remediation_eligibility"),
            why=f"policy gate for {action} on {kind}",
        )
        for rule_key, version in (eligibility.get("rule_versions_used") or {}).items()
    ]
    if not citations:
        raise CompilationRejected("no eligibility check in trajectory — nothing to cite")

    return PlaybookSpec(
        goal=f"Resolve a {kind} incident by applying {action} and notifying on-call",
        preconditions=preconditions[:6],
        params={"incident_id": "string"},
        steps=steps,
        rule_citations=citations,
    )


def _parameterize(args: dict[str, Any]) -> dict[str, str]:
    """Swap concrete incident ids for the {incident_id} placeholder."""
    out: dict[str, str] = {}
    for key, value in args.items():
        if key == "idempotency_key":
            continue  # executor-injected; must never be baked into a spec
        text = str(value)
        out[key] = _INCIDENT_RE.sub("{incident_id}", text)
    return out


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _ground_citations(
    spec: PlaybookSpec, trajectory: list[dict[str, Any]]
) -> list[tuple[str, int, str, float]]:
    """Keep only citations the trajectory corroborates, at the version it saw.

    Two sources of truth are merged: the rule snapshot from get_rules, and the
    versions the eligibility tool reported using. A citation absent from both
    is dropped — that is the difference between provenance and guesswork.
    """
    snapshot: dict[str, int] = {}
    rules_output = _first_output(trajectory, "get_rules") or {}
    for rule in rules_output.get("rules", []):
        snapshot[rule["rule_key"]] = int(rule["version"])

    consulted: dict[str, int] = {}
    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    for rule_key, version in (eligibility.get("rule_versions_used") or {}).items():
        consulted[rule_key] = int(version)

    deps: dict[str, tuple[str, int, str, float]] = {}
    for citation in spec.rule_citations:
        key = citation.rule_key
        if key in consulted:
            version, confidence = consulted[key], 0.95
        elif key in snapshot:
            version, confidence = snapshot[key], 0.75
        else:
            log.info("dropping uncorroborated citation %r", key)
            continue
        deps[key] = (key, version, citation.why, confidence)

    return list(deps.values())


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def _safety_lint(spec: PlaybookSpec) -> list[str]:
    """Static checks. A playbook that fails any of these is never stored."""
    violations: list[str] = []

    if not MIN_STEPS <= len(spec.steps) <= MAX_STEPS:
        violations.append(f"step count {len(spec.steps)} outside {MIN_STEPS}-{MAX_STEPS}")

    seen_eligibility_check = False
    for index, step in enumerate(spec.steps):
        if step.tool not in ALLOWED_TOOLS:
            violations.append(f"step {index}: tool {step.tool!r} not whitelisted")
        if step.tool == "check_remediation_eligibility":
            seen_eligibility_check = True
        elif step.tool == "apply_remediation" and not seen_eligibility_check:
            violations.append(
                f"step {index}: apply_remediation without a preceding eligibility check"
            )
        if "idempotency_key" in step.args:
            violations.append(f"step {index}: spec must not pin an idempotency_key")

    declared = set(spec.params)
    for index, step in enumerate(spec.steps):
        for value in step.args.values():
            for placeholder in re.findall(r"\{(\w+)\}", str(value)):
                if placeholder not in declared:
                    violations.append(
                        f"step {index}: undeclared parameter {{{placeholder}}}"
                    )

    return violations


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _insert_playbook(
    spec: PlaybookSpec,
    name: str,
    domain: str,
    embedding: list[float],
    deps: list[tuple[str, int, str, float]],
    supersedes: UUID | None,
    db,
) -> UUID:
    """Insert playbook + deps + audit atomically.

    All three writes share one transaction: a playbook visible without its
    provenance edges would read as fresh forever, because the freshness join
    would find nothing to compare.
    """
    playbook_id = uuid4()
    version = 1
    if supersedes:
        rows = await db.q(
            "SELECT version FROM playbooks WHERE playbook_id = %s", (str(supersedes),)
        )
        if rows:
            version = rows[0]["version"] + 1

    literal = to_vector_literal(embedding)

    async def txn(cur):
        await cur.execute(
            """
            INSERT INTO playbooks (
                playbook_id, name, domain, version, supersedes,
                status_cache, spec, confidence, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """,
            (
                str(playbook_id),
                name,
                domain,
                version,
                str(supersedes) if supersedes else None,
                "candidate",
                json.dumps(spec.model_dump()),
                INITIAL_CONFIDENCE,
                literal,
            ),
        )

        for rule_key, rule_version, citation, extraction_confidence in deps:
            await cur.execute(
                """
                INSERT INTO playbook_deps (
                    playbook_id, rule_key, rule_version, citation, extraction_confidence
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (str(playbook_id), rule_key, rule_version, citation, extraction_confidence),
            )

        await cur.execute(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, %s, %s)",
            (
                "playbook.compiled",
                "system",
                json.dumps(
                    {
                        "playbook_id": str(playbook_id),
                        "name": name,
                        "version": version,
                        "supersedes": str(supersedes) if supersedes else None,
                        "deps": [d[0] for d in deps],
                    }
                ),
            ),
        )
        return playbook_id

    result = await db.run_txn(txn)
    log.info("compiled playbook %s v%d (%s) with %d deps", result, version, name, len(deps))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_output(trajectory: list[dict[str, Any]], tool: str) -> dict[str, Any] | None:
    for entry in trajectory:
        if entry.get("tool_name") == tool:
            output = entry.get("tool_output")
            if isinstance(output, dict):
                return output
    return None


def _index_of(steps: list[Step], tool: str) -> int:
    for index, step in enumerate(steps):
        if step.tool == tool:
            return index
    return 0


def _derive_name(spec: PlaybookSpec, trajectory: list[dict[str, Any]]) -> str:
    incident = _first_output(trajectory, "get_incident") or {}
    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    kind = str(incident.get("kind", "")).replace("_", " ") or "incident"
    action = str(eligibility.get("action", "")).replace("_", " ")
    name = f"{action} for {kind}".strip() if action else f"remediate {kind}"
    return name[:200]


def _summarize(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim trajectory for the extraction prompt — outputs can be large."""
    return [
        {
            "step": entry.get("step_index"),
            "tool": entry.get("tool_name"),
            "input": entry.get("tool_input"),
            "output": entry.get("tool_output"),
        }
        for entry in trajectory[:12]
    ]
