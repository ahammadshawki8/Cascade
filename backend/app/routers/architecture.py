"""Architecture router — the machinery, read live.

OWNER: Shawki (Track B).

Endpoints:
    GET /api/architecture         — provenance edges, last cascade, outbox, counts
    GET /api/architecture/index   — EXPLAIN proof that the vector index is used

Every number here is read out of the cluster the viewer has just been driving.
A static diagram of an architecture is a claim; this is the architecture
answering for itself.

Deliberately unauthenticated, like the rest of the read surface: the whole
point is that someone evaluating the project can check it without being handed
a token.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


_EMPTY = {
    "counts": {},
    "rules": [],
    "runbooks": [],
    "edges": [],
    "last_cascade": None,
    "outbox": [],
}


@router.get("/architecture")
async def architecture():
    """The provenance graph and the machinery around it."""
    if _stub_mode():
        return _EMPTY

    from app.db import q

    # Head rules only. A rule's older versions still exist — that is what makes
    # a runbook's pin meaningful — but the graph is about what is current.
    rules = await q(
        """
        SELECT rule_key, version, domain
        FROM rules
        WHERE valid_to IS NULL
        ORDER BY rule_key
        """
    )

    runbooks = await q(
        """
        SELECT playbook_id, name, version, status_cache, confidence
        FROM playbooks
        ORDER BY created_at
        """
    )

    # The join that decides staleness, returned as data so the UI can draw it
    # rather than describe it. `is_stale` is computed here exactly as the
    # freshness gate computes it — same comparison, same source.
    edges = await q(
        """
        SELECT d.playbook_id, d.rule_key, d.rule_version AS pinned_version,
               r.version AS head_version,
               (d.rule_version != r.version) AS is_stale
        FROM playbook_deps d
        JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        ORDER BY d.rule_key
        """
    )

    # The most recent cascade, with the two numbers that matter side by side:
    # what it wrote, and how much it invalidated.
    cascade_rows = await q(
        """
        SELECT actor, details, at
        FROM audit_log
        WHERE kind = 'rule.change'
        ORDER BY at DESC
        LIMIT 1
        """
    )
    last_cascade = None
    if cascade_rows:
        row = cascade_rows[0]
        details = row["details"] or {}
        rule_key = details.get("rule_key")
        # Counted as "still stale because of this", not "was affected at the
        # time". The distinction matters after a demo reset, where the audit
        # row survives and the runbooks do not: reporting the historical
        # figure would credit the cascade with invalidating things that no
        # longer exist.
        affected = await q(
            """
            SELECT count(DISTINCT d.playbook_id)::INT AS n
            FROM playbook_deps d
            JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
            WHERE d.rule_key = %s AND d.rule_version != r.version
            """,
            (rule_key,),
        )
        last_cascade = {
            "rule_key": rule_key,
            "from_version": details.get("from_version"),
            "to_version": details.get("to_version"),
            # Older audit rows predate the field; the constant is what the
            # transaction has always done, but say when it was not recorded.
            "writes": details.get("writes"),
            "runbooks_stale": affected[0]["n"] if affected else 0,
            "actor": row["actor"],
            "at": row["at"],
        }

    outbox = await q(
        """
        SELECT kind,
               count(*) FILTER (WHERE processed_at IS NULL)::INT AS pending,
               count(*) FILTER (WHERE processed_at IS NOT NULL)::INT AS processed
        FROM outbox
        GROUP BY kind
        ORDER BY kind
        """
    )

    counts = await q(
        """
        SELECT
          (SELECT count(*)::INT FROM rules WHERE valid_to IS NULL) AS rules_head,
          (SELECT count(*)::INT FROM rules) AS rule_versions,
          (SELECT count(*)::INT FROM playbooks) AS runbooks,
          (SELECT count(*)::INT FROM playbook_deps) AS provenance_edges,
          (SELECT count(*)::INT FROM episodes) AS episodes,
          (SELECT count(*)::INT FROM tasks) AS tasks
        """
    )

    return {
        "counts": counts[0] if counts else {},
        "rules": rules,
        "runbooks": runbooks,
        "edges": edges,
        "last_cascade": last_cascade,
        "outbox": outbox,
    }


@router.get("/architecture/index")
async def architecture_index():
    """Live EXPLAIN of the retrieval query.

    Retrieval claiming to use a vector index is the sort of thing that is true
    right up until a stray predicate silently drops it, so the plan is read
    from the database rather than asserted.
    """
    if _stub_mode():
        return {"uses_index": False, "plan": "", "note": "stub mode"}

    # The same helper the Day-3 gate uses, rather than a second query written
    # to look similar. A near-copy is how you end up proving that some *other*
    # query uses the index: phase 1 deliberately carries no predicate at all,
    # and one stray predicate is enough to drop the index and full-scan. The
    # first version of this endpoint did exactly that and reported FULL SCAN.
    from app import db as db_module
    from app.core.retrieval import verify_vector_index

    result = await verify_vector_index(db_module)
    result["index_name"] = "pb_embed_idx"
    return result
