"""Trajectory -> playbook compiler (spec §6.1, §6.2).

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
from .retrieval import dedup_check, normalize_for_embedding, to_vector_literal

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

    if supersedes:
        await _assert_provenance_not_weaker(supersedes, deps, db)

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
    # Normalised identically to the query side. These two calls are the only
    # places a vector enters this space, and if they ever disagree retrieval
    # silently degrades rather than failing, so they share one function.
    #
    # The kind comes from the trajectory rather than a second database read:
    # this run already fetched the incident, and using what it actually saw
    # keeps the runbook indexed by the situation it was genuinely learned from.
    learned_from = _first_output(trajectory, "get_incident") or {}
    kind = str(learned_from.get("kind")) if learned_from.get("kind") else None
    embedding_text = normalize_for_embedding(task_text or spec.goal, kind)
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
        task_id=task_id,
        episode_id=episode_id,
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
  ],
  "precondition_predicate": {                             // the checkable form
    "all": [
      {"field": "kind", "op": "eq", "value": "bad_deploy"},
      {"field": "state", "op": "eq", "value": "open"},
      {"field": "deploy_age_hours", "op": "lte", "param": "rollback_window.hours"}
    ]
  }
}

Rules:
- Use only these tools: get_incident, get_rules, check_remediation_eligibility,
  apply_remediation, notify_oncall.
- Replace the concrete incident id with the placeholder {incident_id}.
- apply_remediation must be preceded by check_remediation_eligibility.
- Never include idempotency_key; the executor injects it.
- Cite only rule_keys that appear in the trajectory's get_rules output.
- Preconditions state when this runbook applies IN GENERAL. There are two ways
  to get this wrong, and both make the runbook permanently unreusable:
  (a) Encoding incidental properties of the one incident it was learned from:
      a specific severity (P1, P2, ...), service name, incident id, timestamp
      or date. Only the training incident would ever satisfy them.
  (b) Freezing a policy value into the text: "service tier is 1", "deploy was
      within the last 4 hours". Policy thresholds are checked at run time
      against the live rules by check_remediation_eligibility, so restating a
      number here is redundant, and it becomes wrong the moment policy moves.
  State the shape of the situation instead.
  Good: "incident kind is 'bad_deploy'"
        "incident state is 'open'"
        "the service tier is within what the auto_remediate_tier policy allows"
        "the deploy is recent enough for the rollback window to permit rollback"
  Bad:  "severity is P1"
        "service is svc-checkout"
        "service tier is 1"
        "deploy occurred within the last 4 hours"
- precondition_predicate is the same conditions in checkable form, and it is
  what actually decides whether this runbook applies. The prose above is for a
  person to read; this is for the engine, so that reuse never depends on a
  model re-reading English at run time.
  Fields you may use: kind, severity, service_name, service_tier, state,
  deploy_age_hours, error_rate, cpu_usage, action.
  Operators: eq, neq, lt, lte, gt, gte, in, nin, contains, exists, missing.
  Combine with {"all": [...]}, {"any": [...]}, {"not": {...}}.
  Compare against a literal with "value", or against a live policy parameter
  with "param", written as <rule name without its domain>.<parameter>:
      {"field": "deploy_age_hours", "op": "lte", "param": "rollback_window.hours"}
      {"field": "service_tier", "op": "gte", "param": "auto_remediate_tier.min_tier"}
  Always use "param" for anything policy controls, never a frozen number: the
  number changes when policy changes, and the predicate must change with it."""

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
                spec = PlaybookSpec.model_validate(parsed)
            except Exception as exc:
                # A malformed spec is a rejection signal, not something to patch
                # up — fall through to the structural path, which is grounded.
                log.warning("LLM spec failed schema validation, deriving instead: %s", exc)
            else:
                return _with_checked_predicate(spec, trajectory)

    return _derive_spec(trajectory, task_text)


def _params_from(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Live policy parameters, named the way a predicate cites them."""
    rules = _first_output(trajectory, "get_rules") or {}
    out: dict[str, Any] = {}
    for rule in rules.get("rules", []):
        key = str(rule.get("rule_key", ""))
        short = key.split(".", 1)[-1]
        for name, value in (rule.get("params") or {}).items():
            out[f"{short}.{name}"] = value
            out[f"{key}.{name}"] = value
            out.setdefault(name, value)
    return out


def _derive_predicate(trajectory: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build a precondition predicate from what the run actually did.

    Structural, not generated. The incident's kind and the rules the eligibility
    check consulted are both observed facts, so this cannot hallucinate and
    cannot cite a parameter that does not exist.

    It exists because the model kept writing `auto_remediate_tier.max_tier`
    when the parameter is `min_tier`. Validation caught it every time and the
    runbook fell back to the prose check, which is safe and defeats the point:
    the goal is that reuse is deterministic, and a predicate that is usually
    absent does not deliver that. So this is the default, and a model-written
    predicate is only an override when it validates.
    """
    incident = _first_output(trajectory, "get_incident") or {}
    eligibility = _first_output(trajectory, "check_remediation_eligibility") or {}
    kind = incident.get("kind")
    if not kind:
        return None

    used = eligibility.get("rule_versions_used") or {}
    conditions: list[dict[str, Any]] = [
        {"field": "kind", "op": "eq", "value": str(kind)},
        {"field": "state", "op": "eq", "value": "open"},
    ]
    if "incident.auto_remediate_tier" in used:
        conditions.append(
            {"field": "service_tier", "op": "gte", "param": "auto_remediate_tier.min_tier"}
        )
    if "incident.rollback_window" in used:
        conditions.append(
            {"field": "deploy_age_hours", "op": "lte", "param": "rollback_window.hours"}
        )
    return {"all": conditions}


def _with_checked_predicate(
    spec: PlaybookSpec, trajectory: list[dict[str, Any]]
) -> PlaybookSpec:
    """Validate the compiled predicate here, or drop it.

    This is the whole reason compiling a predicate is safer than interpreting
    prose. The model writes it once; if it is wrong we find out now, where the
    cost is falling back to the prose check, rather than on the tenth reuse.

    Two checks, and the second is the one that catches real mistakes.

    Structural: the fields exist, the operators exist, and every policy
    parameter it cites is real. A predicate citing `max_tier` when the rule has
    `min_tier` resolves to nothing and silently passes forever, which looks like
    a working gate and is not one.

    Behavioural: **the predicate must hold for the incident it was learned
    from.** A runbook compiled from an incident it does not itself match is
    incoherent, and this catches inverted comparisons, wrong fields and wrong
    parameters in one cheap evaluation. It is the closest thing to a unit test
    the compiler can run against its own output.
    """
    from .policy import PredicateError, evaluate_condition, validate_condition
    from .policy.facts import DOMAIN_FACTS

    known_fields = {f["field"] for f in DOMAIN_FACTS["incident"]}
    params = _params_from(trajectory)
    derived = _derive_predicate(trajectory)

    def drop(reason: str) -> PlaybookSpec:
        # Fall back to the *derived* predicate, not to prose. Reuse staying
        # deterministic is the whole objective; dropping to a model call every
        # time the model writes a bad predicate would mean the feature is
        # absent exactly when it is most needed.
        log.warning(
            "compiled predicate rejected (%s); using the derived one instead", reason
        )
        spec.precondition_predicate = derived
        return spec

    if spec.precondition_predicate is None:
        spec.precondition_predicate = derived
        return spec

    try:
        validate_condition(spec.precondition_predicate, known_fields, set(params))
    except PredicateError as exc:
        return drop(str(exc))

    incident = _first_output(trajectory, "get_incident") or {}
    if not incident:
        # Nothing to check it against. Structurally sound is all we can say.
        return spec

    facts = dict(incident)
    deployed_at = facts.get("deploy_timestamp")
    if isinstance(deployed_at, str) and deployed_at:
        try:
            from datetime import UTC, datetime

            parsed = datetime.fromisoformat(deployed_at)
            now = datetime.now(parsed.tzinfo or UTC)
            facts["deploy_age_hours"] = round((now - parsed).total_seconds() / 3600, 1)
        except ValueError:
            pass

    if evaluate_condition(spec.precondition_predicate, facts, params) is False:
        return drop("it does not hold for the incident it was compiled from")

    return spec


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

    used = eligibility.get("rule_versions_used") or {}

    preconditions = [f"Incident kind is {kind}", "Incident state is open"]
    for reason_source, text in (
        ("incident.auto_remediate_tier", "Service tier is within the automation floor"),
        ("incident.rollback_window", "Last deploy is inside the rollback window"),
    ):
        if reason_source in used:
            preconditions.append(text)

    citations = [
        RuleCitation(
            rule_key=rule_key,
            rule_version=int(version),
            used_in_step=_index_of(steps, "check_remediation_eligibility"),
            why=f"policy gate for {action} on {kind}",
        )
        for rule_key, version in used.items()
    ]
    if not citations:
        raise CompilationRejected("no eligibility check in trajectory — nothing to cite")

    return PlaybookSpec(
        goal=f"Resolve a {kind} incident by applying {action} and notifying on-call",
        preconditions=preconditions[:6],
        params={"incident_id": "string"},
        steps=steps,
        rule_citations=citations,
        # One derivation, shared with the model path's fallback, so the two can
        # never disagree about what this runbook's preconditions mean.
        precondition_predicate=_derive_predicate(trajectory),
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


async def _assert_provenance_not_weaker(
    supersedes: UUID, deps: list[tuple[str, int, str, float]], db
) -> None:
    """A replacement must depend on at least what it replaces.

    Re-learning re-solves the incident and compiles the result, and the new
    provenance is whatever that run could corroborate. When the re-solve takes
    a shorter path — escalating, say, instead of rolling back — it never reads
    the rules the original consulted, so the successor is grounded on fewer of
    them and every dropped rule is one that can no longer invalidate it.

    Observed: a v2 compiled from an escalation cited only auto_remediate_tier
    and notify, where v1 had cited rollback_window too. That v2 would survive a
    rollback_window change untouched — the runbook would look healthy while
    resting on policy nobody had checked. Silently trading away the ability to
    go stale is the one regression this system must not ship, since going stale
    correctly is the entire point.

    Rejecting leaves the predecessor quarantined and visibly un-relearned,
    which is the honest state: nothing was proven, so nothing is trusted.

    Only rules that have *moved* are enforced, not the whole predecessor set.
    Citations come from a model, and which rules it chooses to list varies run
    to run: an early version of this check demanded an exact superset and
    rejected a perfectly good v2 because that run had not listed
    `incident.notify`, even though it did notify. Blocking a correct relearn
    over phrasing variance is worse than the gap it closes.

    A rule that has changed since the predecessor was compiled is the one that
    caused the quarantine. If the replacement does not cite it, the relearn has
    produced a runbook that the very change prompting it could not invalidate —
    which is the failure this guards against.
    """
    rows = await db.q(
        """
        SELECT d.rule_key, d.rule_version,
               (SELECT max(version) FROM rules WHERE rule_key = d.rule_key) AS head
        FROM playbook_deps d
        WHERE d.playbook_id = %s
        """,
        (str(supersedes),),
    )
    moved = {
        r["rule_key"]
        for r in rows
        if r["head"] is not None and r["rule_version"] < r["head"]
    }
    proposed = {d[0] for d in deps}
    lost = moved - proposed
    if lost:
        raise CompilationRejected(
            "provenance weaker than the version it replaces: "
            f"{', '.join(sorted(lost))} changed since the original was compiled "
            "but is not cited by the replacement, which therefore could not be "
            "invalidated by that rule."
        )


async def _insert_playbook(
    spec: PlaybookSpec,
    name: str,
    domain: str,
    embedding: list[float],
    deps: list[tuple[str, int, str, float]],
    supersedes: UUID | None,
    db,
    task_id: UUID,
    episode_id: UUID,
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
                        # Which run taught this. /api/tasks/{id}/explain uses it
                        # to close the loop: an explore run is only worth its
                        # cost if it left something reusable behind.
                        "task_id": str(task_id),
                        "episode_id": str(episode_id),
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
