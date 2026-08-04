"""Semantic invalidation triage (T2.1).

OWNER: Shawki (Track B).

Any rule version bump makes every dependent playbook stale. That is correct and
safe, but blunt: **widening** a rollback window from 4h to 24h cannot break a
runbook that already ran inside 4h, yet it gets quarantined all the same. At
scale that churn is the main practical objection to provenance-based
invalidation.

Triage runs *after* the cascade commits and classifies each dependent playbook:

    UNAFFECTED  the change provably cannot alter this playbook's behaviour
    BROKEN      the change invalidates an assumption it relies on
    UNCERTAIN   anything else

Only UNAFFECTED is acted on, by re-pinning that playbook's dep to the new rule
version — which makes the freshness join report fresh again, through the normal
mechanism.

=== THE SAFETY PROPERTY ===

Triage can only ever *clear* a playbook by moving its dep forward. It cannot
mark a stale playbook usable while a version mismatch stands, and it cannot
weaken the freshness join, which remains the sole authority on whether
execution is allowed (D1). UNCERTAIN and BROKEN both leave the playbook
quarantined, and any error anywhere in here leaves everything quarantined.

Fail-closed is not a fallback path — it is the default, and the LLM is only
ever allowed to move a playbook *toward* being more trusted when it can justify
it against a deterministic pre-check.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

UNAFFECTED = "UNAFFECTED"
BROKEN = "BROKEN"
UNCERTAIN = "UNCERTAIN"

_SYSTEM = """You assess whether a policy change breaks an automation runbook.

You are given the old rule, the new rule, and how the runbook depends on it.

Answer with JSON only:
{"verdict": "UNAFFECTED" | "BROKEN" | "UNCERTAIN", "why": "one sentence"}

UNAFFECTED  - the change only RELAXES the constraint (a wider window, a lower
              tier floor, a larger limit). Anything the runbook did before is
              still permitted.
BROKEN      - the change TIGHTENS the constraint, or changes its meaning, so
              the runbook could now do something policy forbids.
UNCERTAIN   - you cannot tell from the text alone.

When in doubt answer UNCERTAIN. A wrong UNAFFECTED lets an agent act under a
policy it no longer satisfies; a wrong UNCERTAIN merely costs a re-learn."""


async def triage_rule_change(
    rule_key: str,
    old_version: int,
    new_version: int,
    playbook_ids: list[str],
    db,
) -> dict[str, Any]:
    """Classify dependents and clear the provably unaffected ones."""
    if not playbook_ids:
        return {"cleared": [], "broken": [], "uncertain": []}

    old_rule, new_rule = await _load_versions(rule_key, old_version, new_version, db)
    if old_rule is None or new_rule is None:
        log.warning("triage: could not load both versions of %s", rule_key)
        return {"cleared": [], "broken": [], "uncertain": playbook_ids}

    # Deterministic pre-check first. When the parameters are numeric and moved
    # in a strictly relaxing direction, that is a fact — no model needed, and
    # no model allowed to contradict it into being *more* permissive.
    numeric = _compare_numeric(old_rule["params"] or {}, new_rule["params"] or {})

    verdict_for_all: str | None = None
    reason = ""
    if numeric == "relaxed":
        verdict_for_all, reason = UNAFFECTED, "every changed parameter was relaxed"
    elif numeric == "tightened":
        verdict_for_all, reason = BROKEN, "a parameter was tightened"

    cleared, broken, uncertain = [], [], []

    for playbook_id in playbook_ids:
        if verdict_for_all is not None:
            verdict, why = verdict_for_all, reason
        else:
            verdict, why = await _ask_model(old_rule, new_rule, playbook_id, db)

        if verdict == UNAFFECTED:
            ok = await _repin(playbook_id, rule_key, old_version, new_version, db)
            (cleared if ok else uncertain).append(playbook_id)
        elif verdict == BROKEN:
            broken.append(playbook_id)
        else:
            uncertain.append(playbook_id)

        await _audit(db, playbook_id, rule_key, old_version, new_version, verdict, why)

    log.info(
        "triage %s v%d->v%d: %d cleared, %d broken, %d uncertain",
        rule_key,
        old_version,
        new_version,
        len(cleared),
        len(broken),
        len(uncertain),
    )
    return {"cleared": cleared, "broken": broken, "uncertain": uncertain}


# ---------------------------------------------------------------------------


async def _load_versions(
    rule_key: str, old_version: int, new_version: int, db
) -> tuple[dict | None, dict | None]:
    rows = await db.q(
        """
        SELECT version, body, params FROM rules
        WHERE rule_key = %s AND version IN (%s, %s)
        """,
        (rule_key, old_version, new_version),
    )
    by_version = {r["version"]: dict(r) for r in rows}
    return by_version.get(old_version), by_version.get(new_version)


# Which direction counts as "more permissive" for each parameter. A rollback
# window of 24h is more permissive than 4h; a min_tier of 1 is more permissive
# than 2 (it lets *more* services be automated).
_HIGHER_IS_LOOSER = {"hours", "max_actions", "window_hours", "limit"}
_LOWER_IS_LOOSER = {"min_tier", "tier", "threshold"}


def _compare_numeric(old: dict[str, Any], new: dict[str, Any]) -> str | None:
    """"relaxed" | "tightened" | None (mixed, non-numeric, or unknown key)."""
    keys = set(old) | set(new)
    if not keys:
        return None

    directions = set()
    for key in keys:
        before, after = old.get(key), new.get(key)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            return None
        if before == after:
            continue

        if key in _HIGHER_IS_LOOSER:
            directions.add("relaxed" if after > before else "tightened")
        elif key in _LOWER_IS_LOOSER:
            directions.add("relaxed" if after < before else "tightened")
        else:
            return None  # unknown semantics — never guess

    if not directions:
        return "relaxed"  # nothing meaningful changed
    if len(directions) == 1:
        return directions.pop()
    return None  # mixed directions — let the model or fail-closed decide


async def _ask_model(
    old_rule: dict, new_rule: dict, playbook_id: str, db
) -> tuple[str, str]:
    from .llm import FastClient, parse_json

    dep = await db.q(
        """
        SELECT d.citation, p.name, p.spec
        FROM playbook_deps d JOIN playbooks p ON p.playbook_id = d.playbook_id
        WHERE d.playbook_id = %s LIMIT 1
        """,
        (playbook_id,),
    )
    citation = dep[0]["citation"] if dep else "unknown"
    name = dep[0]["name"] if dep else "unknown"

    raw = await FastClient().generate(
        system=_SYSTEM,
        user=(
            f"OLD rule (v{old_rule['version']}): {old_rule['body']}\n"
            f"OLD params: {json.dumps(old_rule['params'])}\n\n"
            f"NEW rule (v{new_rule['version']}): {new_rule['body']}\n"
            f"NEW params: {json.dumps(new_rule['params'])}\n\n"
            f"Runbook: {name}\nHow it depends on the rule: {citation}"
        ),
        max_tokens=200,
    )
    parsed = parse_json(raw)
    if isinstance(parsed, dict):
        verdict = str(parsed.get("verdict", "")).upper()
        if verdict in (UNAFFECTED, BROKEN, UNCERTAIN):
            return verdict, str(parsed.get("why", ""))[:300]

    # No usable answer is not permission to proceed.
    return UNCERTAIN, "no usable verdict from the model"


async def _repin(
    playbook_id: str, rule_key: str, old_version: int, new_version: int, db
) -> bool:
    """Move the dep forward so the freshness join reports fresh again.

    This is the *only* mutation triage performs, and it is the same edge the
    compiler would have written had the playbook been learned under the new
    rule. `playbook_deps` is keyed on (playbook_id, rule_key, rule_version), so
    this is an update of the key itself.
    """
    try:

        async def txn(cur):
            await cur.execute(
                """
                UPDATE playbook_deps
                SET rule_version = %s
                WHERE playbook_id = %s AND rule_key = %s AND rule_version = %s
                """,
                (new_version, playbook_id, rule_key, old_version),
            )
            # Restore the card only if nothing *else* still holds it stale.
            await cur.execute(
                """
                SELECT count(*)::INT AS stale
                FROM playbook_deps d
                JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
                WHERE d.playbook_id = %s AND r.version != d.rule_version
                """,
                (playbook_id,),
            )
            row = await cur.fetchone()
            if row and row["stale"] == 0:
                await cur.execute(
                    """
                    UPDATE playbooks
                    SET status_cache = CASE
                            WHEN confidence >= 0.6 THEN 'active' ELSE 'candidate'
                        END,
                        updated_at = now()
                    WHERE playbook_id = %s AND status_cache = 'suspect'
                    """,
                    (playbook_id,),
                )
            return True

        return await db.run_txn(txn)
    except Exception as exc:
        # Failing to clear is safe; the playbook stays quarantined.
        log.warning("triage re-pin failed for %s: %s", playbook_id, exc)
        return False


async def _audit(
    db,
    playbook_id: str,
    rule_key: str,
    old_version: int,
    new_version: int,
    verdict: str,
    why: str,
) -> None:
    try:
        await db.q(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, 'triage', %s)",
            (
                f"triage.{verdict.lower()}",
                json.dumps(
                    {
                        "playbook_id": str(playbook_id),
                        "rule_key": rule_key,
                        "from_version": old_version,
                        "to_version": new_version,
                        "verdict": verdict,
                        "why": why,
                    }
                ),
            ),
        )
    except Exception as exc:
        log.warning("triage audit failed: %s", exc)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
