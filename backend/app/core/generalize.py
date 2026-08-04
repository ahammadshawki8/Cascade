"""Playbook generalization — collapsing near-duplicates (T3.8).

OWNER: Shawki (Track B).

`dedup_check` stops the *same* trajectory being compiled twice. It does not
stop the library accumulating three runbooks that differ only in which action
they apply — one per incident kind — each carrying its own confidence and each
needing its own re-learn when policy moves.

Generalization folds a cluster like that into one parameterized runbook:

    rollback for bad_deploy          }
    restart for error_spike          }  ->  remediate {incident_kind}
    scale_up for resource_exhaustion }

Three constraints make this safe rather than clever:

  * **Identical step shape only.** Members must call the same tools in the same
    order. Merging runbooks with different control flow would invent a
    procedure nobody verified.
  * **Union of provenance.** The merged runbook depends on every rule any
    member depended on, at the head version. Dropping an edge would make it
    look fresh when it isn't.
  * **Members are archived, not deleted.** `merged_from` records the lineage,
    and the episodes that produced them still reference real rows.

Confidence starts at the *minimum* of the members: a generalization is only as
trustworthy as its weakest constituent.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from .models import PlaybookSpec, RuleCitation, Step
from .retrieval import to_vector_literal

log = logging.getLogger(__name__)

MIN_CLUSTER = 2
# Members must share every tool in order; only their arguments may differ.
_PARAM_PLACEHOLDER = "{incident_kind}"


async def find_generalizable(db) -> list[list[dict[str, Any]]]:
    """Group active runbooks that differ only in their arguments."""
    rows = await db.q(
        """
        SELECT playbook_id, name, domain, version, spec, confidence,
               uses, successes, failures
        FROM playbooks
        WHERE status_cache IN ('active', 'candidate')
          AND NOT generalized
        ORDER BY created_at
        """
    )
    if len(rows) < MIN_CLUSTER:
        return []

    clusters: dict[tuple, list[dict]] = {}
    for row in rows:
        spec = row["spec"]
        if isinstance(spec, str):
            spec = json.loads(spec)
        signature = _step_signature(spec)
        if signature is None:
            continue
        clusters.setdefault((row["domain"], signature), []).append(
            {**dict(row), "parsed_spec": spec}
        )

    return [members for members in clusters.values() if len(members) >= MIN_CLUSTER]


def _step_signature(spec: dict[str, Any]) -> tuple | None:
    """The ordered tool sequence — the part that must match exactly."""
    steps = spec.get("steps") or []
    if not steps:
        return None
    return tuple(step.get("tool") for step in steps)


async def generalize_cluster(members: list[dict[str, Any]], db) -> UUID | None:
    """Compile a cluster into one parameterized runbook. Returns its id."""
    if len(members) < MIN_CLUSTER:
        return None

    template = members[0]["parsed_spec"]
    kinds = sorted({_incident_kind(m["parsed_spec"]) for m in members})
    kinds = [k for k in kinds if k]

    # Nothing to generalize if every member covers the same incident kind —
    # that is a duplicate, which dedup_check should have prevented.
    if len(kinds) < MIN_CLUSTER:
        return None

    steps = [
        Step(tool=step["tool"], args=_generalize_args(step.get("args", {})))
        for step in template.get("steps", [])
    ]

    member_ids = [str(m["playbook_id"]) for m in members]
    deps = await _union_deps(member_ids, db)
    if not deps:
        log.info("generalization skipped: cluster has no provenance to carry")
        return None

    spec = PlaybookSpec(
        goal=(
            "Remediate an incident of kind {incident_kind} using the action its "
            "policy permits, then notify on-call"
        ),
        preconditions=[
            f"Incident kind is one of: {', '.join(kinds)}",
            "Incident state is open",
            "Policy permits the remediation for this service tier",
        ],
        # `action` is declared because the steps reference {action}; the safety
        # lint rejects any placeholder that isn't a declared parameter. The
        # executor binds it from the incident's kind at run time, which is the
        # whole point of the generalization.
        params={
            "incident_id": "string",
            "incident_kind": "string",
            "action": "string",
        },
        steps=steps,
        rule_citations=[
            RuleCitation(
                rule_key=rule_key,
                rule_version=version,
                used_in_step=_index_of(steps, "check_remediation_eligibility"),
                why=f"policy gate carried forward from {len(members)} merged runbooks",
            )
            for rule_key, version in deps
        ],
    )

    from .llm import EmbedClient

    embedding = await EmbedClient().embed(
        f"Remediate incident {' '.join(kinds)}"
    )
    confidence = min(float(m["confidence"]) for m in members)
    playbook_id = uuid4()
    literal = to_vector_literal(embedding)

    async def txn(cur):
        await cur.execute(
            """
            INSERT INTO playbooks (
                playbook_id, name, domain, version, status_cache, spec,
                confidence, embedding, generalized, merged_from,
                uses, successes, failures
            ) VALUES (%s, %s, %s, 1, 'candidate', %s, %s, %s::vector, TRUE, %s,
                      %s, %s, %s)
            """,
            (
                str(playbook_id),
                f"remediate {'/'.join(kinds)}"[:200],
                members[0]["domain"],
                json.dumps(spec.model_dump()),
                confidence,
                literal,
                json.dumps(member_ids),
                sum(m["uses"] for m in members),
                sum(m["successes"] for m in members),
                sum(m["failures"] for m in members),
            ),
        )

        for rule_key, version in deps:
            await cur.execute(
                """
                INSERT INTO playbook_deps (
                    playbook_id, rule_key, rule_version, citation,
                    extraction_confidence
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (str(playbook_id), rule_key, version, "merged provenance", 0.9),
            )

        # Archive members rather than delete: episodes reference them, and the
        # lineage is what makes the merge auditable.
        await cur.execute(
            """
            UPDATE playbooks
            SET status_cache = 'invalidated', updated_at = now()
            WHERE playbook_id = ANY(%s)
            """,
            (member_ids,),
        )

        await cur.execute(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, 'system', %s)",
            (
                "playbook.generalized",
                json.dumps(
                    {
                        "playbook_id": str(playbook_id),
                        "merged_from": member_ids,
                        "incident_kinds": kinds,
                        "confidence": confidence,
                    }
                ),
            ),
        )
        return playbook_id

    result = await db.run_txn(txn)
    log.info(
        "generalized %d runbooks into %s covering %s",
        len(members),
        result,
        ", ".join(kinds),
    )
    return result


async def _union_deps(member_ids: list[str], db) -> list[tuple[str, int]]:
    """Every rule any member depends on, pinned at the current head version.

    Head, not the member's pinned version: the merged runbook is being created
    now, against the policy in force now. Carrying a stale pin would make it
    born stale.
    """
    rows = await db.q(
        """
        SELECT DISTINCT d.rule_key, r.version
        FROM playbook_deps d
        JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        WHERE d.playbook_id = ANY(%s)
        ORDER BY d.rule_key
        """,
        (member_ids,),
    )
    return [(r["rule_key"], r["version"]) for r in rows]


def _incident_kind(spec: dict[str, Any]) -> str | None:
    for precondition in spec.get("preconditions", []):
        text = str(precondition).lower()
        for kind in ("bad_deploy", "error_spike", "resource_exhaustion"):
            if kind in text:
                return kind
    return None


def _generalize_args(args: dict[str, Any]) -> dict[str, str]:
    """Replace the hard-coded action with a parameter the executor binds."""
    out: dict[str, str] = {}
    for key, value in args.items():
        if key == "action":
            out[key] = "{action}"
        else:
            out[key] = str(value)
    return out


def _index_of(steps: list[Step], tool: str) -> int:
    for index, step in enumerate(steps):
        if step.tool == tool:
            return index
    return 0
