"""Two-phase vector retrieval (spec §5.5, D2 + D3).

OWNER: Shawki (Track B).

D3 — never mix a vector ORDER BY with scalar predicates in one statement. The
optimizer will happily drop the vector index and scan. So:

    Phase 1  pure ANN, no WHERE clause  -> 20 candidate ids   (hits pb_embed_idx)
    Phase 2  PK lookup + status filter + re-rank              (hits the PK)
    Phase 3  point-of-use freshness join                      (freshness.py)

D2 — Titan V2 with normalize=true emits unit vectors, so L2 ranking and cosine
ranking are identical. The index is built for L2, therefore every query uses
`<->`. Using `<=>` or `<#>` silently disables the index; don't.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from .models import PlaybookCandidate, PlaybookSpec

log = logging.getLogger(__name__)

# Statuses a playbook must hold to be reusable at all. 'invalidated' and
# 'rejected' are terminal and never retrieved.
RETRIEVABLE_STATUSES = ("active", "candidate", "suspect")


def _thresholds() -> tuple[float, float]:
    from app.config import settings

    return settings.retrieval_l2_threshold, settings.dedup_l2_threshold


_INCIDENT_RE = re.compile(r"\binc[\s\-_]*\d+\b", re.IGNORECASE)


def normalize_for_embedding(text: str, kind: str | None = None) -> str:
    """The text a runbook is indexed by, on both sides of the comparison.

    Two problems, and fixing only the first creates a worse third.

    The incident id is a *parameter*, not meaning: "Remediate INC-1001" and
    "Remediate INC-1004" are the same request about different rows. Embedding
    the digits put those roughly 0.59 apart in L2, which fell between the two
    thresholds and broke both at once:

        0.4 ...... dedup ...... 0.59 ...... 0.85 ...... retrieval

    Above dedup, so every cold run on a new id saved another identical runbook
    and the library filled with clones. Below retrieval, so reuse still worked
    and the duplication stayed silent. It also made retrieval sensitive to
    *typing*: "inc 1001" landed 0.91 away and missed reuse entirely. The id
    pattern is loose about separators for exactly that reason — a human writing
    "inc 1001" means "INC-1001", and only the embedding ever disagreed.

    But stripping the id alone over-corrects. Every request is the word
    "remediate" and an id, so with the id gone a bad deploy and an error spike
    embed *identically* — dedup then merges two genuinely different procedures
    and the system can only ever learn one runbook. The id had been carrying
    the incident kind by accident, and removing it removed the only signal that
    told them apart. The integration suite caught this immediately: the tests
    that need a specific runbook to exist started finding one compiled from a
    different kind of incident.

    So the kind travels explicitly. Callers resolve it from the incident row
    (retrieval) or from the trajectory that produced the runbook (compile), and
    both arrive at the same key.

    Thresholds are deliberately unchanged: matching requests now sit at ~0, so
    both gates have room to spare, and retuning a threshold while changing what
    it measures would make any regression impossible to attribute.
    """
    base = _INCIDENT_RE.sub("{incident}", text or "").strip().lower()
    return f"{base} [{kind}]" if kind else base


def canonical_incident_id(text: str) -> str | None:
    """`inc 1001` and `INC-1001` name the same row; return the canonical form."""
    match = _INCIDENT_RE.search(text or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    return f"INC-{digits}" if digits else None


async def incident_kind(task_text: str, db) -> str | None:
    """The kind of incident this request is about, if it names a known one.

    Retrieval runs before the agent has read anything, so the kind has to come
    from the request itself. A request naming no known incident returns None
    and is indexed on its wording alone, which is the honest fallback.
    """
    incident_id = canonical_incident_id(task_text)
    if not incident_id:
        return None
    try:
        rows = await db.q(
            "SELECT kind FROM mock_incidents WHERE incident_id = %s", (incident_id,)
        )
    except Exception as exc:
        log.warning("could not resolve incident kind for %s: %s", incident_id, exc)
        return None
    return str(rows[0]["kind"]) if rows else None


def to_vector_literal(embedding: list[float]) -> str:
    """Render a Python list as a pgvector literal.

    psycopg has no adapter for CockroachDB's VECTOR type, so the value goes
    over as text and is cast with `::vector` at the call site.
    """
    return "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"


async def retrieve(task_text: str, db, embed_client=None) -> PlaybookCandidate | None:
    """Best reusable playbook for this task, or None to explore instead."""
    if embed_client is None:
        from .llm import EmbedClient

        embed_client = EmbedClient()

    kind = await incident_kind(task_text, db)
    embedding = await embed_client.embed(normalize_for_embedding(task_text, kind))
    candidates = await _phase1_ann_query(embedding, db, limit=20)
    if not candidates:
        return None

    distances = {c["playbook_id"]: c["dist"] for c in candidates}
    ranked = await _phase2_pk_filter(list(distances), distances, db)
    if not ranked:
        return None

    retrieval_threshold, _ = _thresholds()
    best = ranked[0]
    if best.distance > retrieval_threshold:
        log.info(
            "retrieval miss: nearest playbook %s at L2 %.3f > threshold %.3f",
            best.playbook_id,
            best.distance,
            retrieval_threshold,
        )
        return None
    return best


async def _phase1_ann_query(
    embedding: list[float], db, limit: int = 20
) -> list[dict[str, Any]]:
    """Pure ANN. No WHERE clause — that is the whole point (D3).

    Not even `embedding IS NOT NULL`: any scalar predicate here makes the
    optimizer abandon pb_embed_idx and full-scan with a top-k sort. Rows with a
    NULL embedding come back with a NULL distance and are dropped below, which
    costs nothing because phase 2 has to re-read these ids anyway.
    """
    literal = to_vector_literal(embedding)
    try:
        rows = await db.q(
            """
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            (literal, literal, limit),
        )
    except Exception as exc:
        log.warning("phase-1 ANN query failed: %s", exc)
        return []

    return [
        {"playbook_id": _as_uuid(r["playbook_id"]), "dist": float(r["dist"])}
        for r in rows
        if r["dist"] is not None
    ]


async def _phase2_pk_filter(
    playbook_ids: list[UUID], distances: dict[UUID, float], db
) -> list[PlaybookCandidate]:
    """PK lookup + metadata filter, re-ranked by distance then confidence."""
    if not playbook_ids:
        return []

    try:
        rows = await db.q(
            """
            SELECT playbook_id, name, version, confidence, status_cache, spec
            FROM playbooks
            WHERE playbook_id = ANY(%s)
              AND status_cache = ANY(%s)
            """,
            ([str(pid) for pid in playbook_ids], list(RETRIEVABLE_STATUSES)),
        )
    except Exception as exc:
        log.warning("phase-2 PK filter failed: %s", exc)
        return []

    candidates: list[PlaybookCandidate] = []
    for row in rows:
        pid = _as_uuid(row["playbook_id"])
        candidates.append(
            PlaybookCandidate(
                playbook_id=pid,
                name=row["name"],
                version=row["version"],
                confidence=float(row["confidence"]),
                distance=distances.get(pid, float("inf")),
                status_cache=row["status_cache"],
                spec=_parse_spec(row["spec"]),
            )
        )

    candidates.sort(key=lambda c: (c.distance, -c.confidence))
    return candidates


async def dedup_check(embedding: list[float], domain: str, db) -> UUID | None:
    """Does a near-identical playbook already exist in this domain?

    Runs at compile time so a second cold run on the same incident class
    reinforces the existing runbook instead of forking the library.
    """
    _, dedup_threshold = _thresholds()

    # Same two-phase shape as retrieve(): a pure ANN pass, then the domain and
    # status predicates applied over the returned ids. Folding them into the
    # vector query would cost the index here too.
    nearest = await _phase1_ann_query(embedding, db, limit=5)
    if not nearest:
        return None

    close = [c for c in nearest if c["dist"] < dedup_threshold]
    if not close:
        return None

    try:
        rows = await db.q(
            """
            SELECT playbook_id
            FROM playbooks
            WHERE playbook_id = ANY(%s)
              AND domain = %s
              AND status_cache = ANY(%s)
            """,
            (
                [str(c["playbook_id"]) for c in close],
                domain,
                list(RETRIEVABLE_STATUSES),
            ),
        )
    except Exception as exc:
        log.warning("dedup check failed: %s", exc)
        return None

    eligible = {_as_uuid(r["playbook_id"]) for r in rows}
    for candidate in close:  # already distance-ordered
        if candidate["playbook_id"] in eligible:
            return candidate["playbook_id"]
    return None


async def verify_vector_index(db) -> dict[str, Any]:
    """EXPLAIN the phase-1 query and confirm pb_embed_idx is chosen.

    This is the Day-3 gate — the whole "distributed vector search" claim rests
    on the planner actually picking the index, so we assert it rather than
    assume it. Surfaced at GET /api/admin/verify-index.
    """
    literal = to_vector_literal([0.0] * 1024)
    try:
        rows = await db.q(
            """
            EXPLAIN
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT 20
            """,
            (literal, literal),
        )
    except Exception as exc:
        return {"uses_index": False, "plan": "", "error": str(exc)}

    plan = "\n".join(
        str(next(iter(row.values()))) if len(row) == 1 else str(row) for row in rows
    )
    uses_index = "pb_embed_idx" in plan
    return {
        "uses_index": uses_index,
        "plan": plan,
        "error": None if uses_index else "pb_embed_idx not referenced in query plan",
    }


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _parse_spec(raw: Any) -> PlaybookSpec | None:
    if raw is None:
        return None
    try:
        return PlaybookSpec.model_validate(raw)
    except Exception as exc:
        log.warning("stored spec failed validation: %s", exc)
        return None
