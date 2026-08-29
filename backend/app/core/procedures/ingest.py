"""Importing a procedure, and grounding it in policy.

OWNER: Shawki (Track B).

Parsing a runbook is the easy half. The half that matters is provenance: a
procedure that cites nothing can never be found stale, so importing one without
linking it to policy produces a library that looks governed and is not.

That linking is model output, which makes it a quality surface exactly like the
compiler's preconditions were. So nothing here auto-commits. `propose_citations`
returns candidates with the sentence each was drawn from, and a human confirms
them before `register` writes anything.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_STEP_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ProposedCitation:
    """One provenance edge, and the evidence for it."""

    rule_key: str
    rule_version: int
    evidence: str
    confidence: float
    rule_body: str = ""


@dataclass
class ParsedProcedure:
    name: str
    goal: str
    manual_steps: list[str] = field(default_factory=list)
    citations: list[ProposedCitation] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_document(text: str) -> ParsedProcedure:
    """Pull a name, a goal and a step list out of a pasted runbook.

    Deliberately forgiving and deliberately not a model call. People paste
    Markdown, numbered lists, or a wall of prose, and none of those should need
    an LLM to become a title and some bullet points. Whatever it gets wrong, the
    confirm screen lets the user fix in place.
    """
    text = (text or "").strip()
    if not text:
        return ParsedProcedure(name="Untitled procedure", goal="")

    headings = _HEADING.findall(text)
    name = headings[0].strip() if headings else ""

    steps = [s.strip() for s in _STEP_LINE.findall(text) if s.strip()]

    # No list markers: treat non-empty lines after the first as the steps, which
    # is what a plain-prose runbook looks like.
    if not steps:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        lines = [ln for ln in lines if not ln.startswith("#")]
        steps = lines[1:] if len(lines) > 1 else lines

    if not name:
        first = next(
            (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")),
            "Imported procedure",
        )
        name = first[:80]

    # The goal is the first paragraph that is not a heading and not a step.
    step_set = set(steps)
    goal = ""
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or candidate in step_set:
            continue
        if _STEP_LINE.match(line):
            continue
        goal = candidate
        break

    return ParsedProcedure(
        name=name[:120] or "Imported procedure",
        goal=(goal or name)[:500],
        manual_steps=[s[:400] for s in steps[:64]],
    )


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You link sentences in an operational runbook to the policy rules they "
    "depend on.\n"
    "You are given the runbook text and a list of policy rules.\n"
    'Reply with JSON only: {"links": [{"rule_key": "...", "evidence": "the exact '
    'sentence from the runbook", "confidence": 0.0-1.0}]}\n\n'
    "Rules for linking:\n"
    "- Only link when the runbook sentence depends on what the rule decides. A "
    "sentence that merely mentions a similar word is not a dependency.\n"
    "- `evidence` must be copied verbatim from the runbook, not paraphrased.\n"
    "- A rule may be linked at most once. Prefer the single clearest sentence.\n"
    "- If nothing in the runbook depends on a rule, do not invent a link. An "
    "empty list is a valid and often correct answer."
)


def _keyword_links(
    text: str, rules: list[dict[str, Any]]
) -> list[ProposedCitation]:
    """Deterministic fallback, and the floor under the model.

    Runs on the rule's own distinguishing words. Crude on purpose: it exists so
    that an import still produces something reviewable when the model is
    unavailable, not so that it can compete with one.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]
    out: list[ProposedCitation] = []

    for rule in rules:
        key = rule["rule_key"]
        # "incident.rollback_window" -> {"rollback", "window"}
        terms = {t for t in re.split(r"[._\-]", key.split(".", 1)[-1]) if len(t) > 3}
        if not terms:
            continue
        best: tuple[int, str] = (0, "")
        for sentence in sentences:
            lowered = sentence.lower()
            hits = sum(1 for t in terms if t in lowered)
            if hits > best[0]:
                best = (hits, sentence)
        if best[0]:
            out.append(
                ProposedCitation(
                    rule_key=key,
                    rule_version=rule["version"],
                    evidence=best[1][:300],
                    # Never presented as confident: this is a keyword overlap,
                    # and the confirm screen should show it as the weak signal
                    # it is rather than as an extraction.
                    confidence=round(min(0.5, 0.2 + 0.15 * best[0]), 2),
                    rule_body=rule.get("body", ""),
                )
            )
    return out


async def propose_citations(
    text: str, rules: list[dict[str, Any]], use_model: bool = True
) -> list[ProposedCitation]:
    """Suggest which rules a runbook depends on. Never writes anything."""
    if not rules:
        return []

    by_key = {r["rule_key"]: r for r in rules}
    proposals: list[ProposedCitation] = []

    if use_model:
        try:
            from app.core.llm import FastClient, parse_json

            rules_block = json.dumps(
                [
                    {"rule_key": r["rule_key"], "says": r["body"], "params": r["params"]}
                    for r in rules
                ],
                indent=2,
                default=str,
            )
            raw = await FastClient().generate(
                system=_SYSTEM,
                user=f"Runbook:\n{text[:6000]}\n\nPolicy rules:\n{rules_block}",
                max_tokens=900,
            )
            parsed = parse_json(raw) or {}
            for link in parsed.get("links", []):
                rule = by_key.get(link.get("rule_key"))
                if not rule:
                    continue  # a rule key the model invented
                proposals.append(
                    ProposedCitation(
                        rule_key=rule["rule_key"],
                        rule_version=rule["version"],
                        evidence=str(link.get("evidence", ""))[:300],
                        confidence=float(link.get("confidence", 0.6)),
                        rule_body=rule.get("body", ""),
                    )
                )
        except Exception as exc:
            log.warning("model citation extraction failed, falling back: %s", exc)

    if not proposals:
        proposals = _keyword_links(text, rules)

    # One edge per rule; `playbook_deps` is keyed that way and a duplicate would
    # abort the whole import.
    seen: set[str] = set()
    unique: list[ProposedCitation] = []
    for p in sorted(proposals, key=lambda x: -x.confidence):
        if p.rule_key in seen:
            continue
        seen.add(p.rule_key)
        unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


async def register(
    name: str,
    goal: str,
    steps: list[str],
    citations: list[tuple[str, int]],
    db,
    origin: str = "imported",
    source_ref: str | None = None,
    actor: str = "admin",
    preconditions: list[str] | None = None,
    evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write an imported or authored procedure, with its provenance.

    The playbook row and its dependency edges go in one transaction for the same
    reason the compiler does it: a procedure visible without provenance reads as
    fresh forever, because the freshness join finds nothing to disagree with.
    """
    if not citations:
        raise ValueError(
            "A procedure needs at least one policy citation. Without one it can "
            "never be found stale, which is the only reason to keep it here."
        )

    # Every cited rule must exist at the version claimed, or the FK aborts the
    # insert with an error nobody can act on. Check first and say which.
    wanted = {(k, v) for k, v in citations}
    rows = await db.q(
        """
        SELECT rule_key, version FROM rules
        WHERE rule_key = ANY(%s)
        """,
        ([k for k, _ in citations],),
    )
    have = {(r["rule_key"], r["version"]) for r in rows}
    missing = wanted - have
    if missing:
        raise ValueError(
            "These citations do not match a real rule version: "
            + ", ".join(f"{k} v{v}" for k, v in sorted(missing))
        )

    steps = [s for s in (steps or []) if s and s.strip()][:64]
    spec = {
        "goal": goal or name,
        "preconditions": preconditions or [f"The situation matches: {goal or name}"],
        "params": {},
        # Empty on purpose for an imported procedure: these are the *executable*
        # steps, and a human runbook has none. Guided mode skips it accordingly.
        "steps": [],
        "manual_steps": steps,
        "rule_citations": [
            {
                "rule_key": key,
                "rule_version": version,
                "used_in_step": 0,
                "why": (evidence or {}).get(key, "cited on import"),
            }
            for key, version in citations
        ],
    }

    playbook_id = uuid4()

    # Imported procedures are embedded like compiled ones so they are findable
    # by the same search. They just cannot be executed by it.
    literal = None
    try:
        from app.core.llm import EmbedClient
        from app.core.retrieval import normalize_for_embedding, to_vector_literal

        embedding = await EmbedClient().embed(
            normalize_for_embedding(f"{name}. {goal}", None)
        )
        literal = to_vector_literal(embedding)
    except Exception as exc:
        log.warning("could not embed imported procedure %s: %s", name, exc)

    async def txn(cur):
        await cur.execute(
            """
            INSERT INTO playbooks (
                playbook_id, name, domain, version, status_cache, spec,
                confidence, origin, source_ref, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """,
            (
                str(playbook_id),
                name,
                "incidents",
                1,
                # Imported procedures start active: a human already trusted this
                # enough to run it. What Cascade adds is knowing when to stop.
                "active",
                json.dumps(spec),
                0.5,
                origin,
                source_ref,
                literal,
            ),
        )
        for key, version in citations:
            await cur.execute(
                """
                INSERT INTO playbook_deps (
                    playbook_id, rule_key, rule_version, citation, extraction_confidence
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    str(playbook_id),
                    key,
                    version,
                    (evidence or {}).get(key, "cited on import")[:500],
                    1.0 if origin == "authored" else 0.9,
                ),
            )
        await cur.execute(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, %s, %s)",
            (
                "playbook.imported",
                actor,
                json.dumps(
                    {
                        "playbook_id": str(playbook_id),
                        "name": name,
                        "origin": origin,
                        "source_ref": source_ref,
                        "citations": [f"{k} v{v}" for k, v in citations],
                    }
                ),
            ),
        )

    await db.run_txn(txn)
    log.info("imported procedure %s (%s) with %d citation(s)", name, origin, len(citations))

    return {
        "procedure_id": str(playbook_id),
        "name": name,
        "origin": origin,
        "citations": [{"rule_key": k, "rule_version": v} for k, v in citations],
    }
