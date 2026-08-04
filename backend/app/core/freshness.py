"""Point-of-use freshness — the authoritative staleness check (spec §5.6, D1).

OWNER: Shawki (Track B).

Staleness is a JOIN, never a column. `playbooks.status_cache` is an async UI
convenience that may lag; this join is what decides whether a playbook is
allowed to execute. It runs immediately before every guided run.

Returns Fresh | Stale — never a bool, so callers must handle the reason. The
UI renders `stale_deps` to explain *why* a runbook went red, and the worker
uses it to decide what to re-learn.
"""

from __future__ import annotations

import logging
from uuid import UUID

from .models import Fresh, FreshnessResult, Stale, StaleDep

log = logging.getLogger(__name__)

# The provenance join (D1). Empty result set == fresh.
_FRESHNESS_SQL = """
    SELECT d.rule_key,
           d.rule_version AS depends_on,
           r.version      AS head
    FROM playbook_deps d
    JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
    WHERE d.playbook_id = %s
      AND r.version != d.rule_version
"""


async def check_freshness(playbook_id: UUID, db) -> FreshnessResult:
    """Is every dep of this playbook pinned to a head rule version?"""
    try:
        rows = await db.q(_FRESHNESS_SQL, (str(playbook_id),))
    except Exception as exc:
        # Fail closed: an unverifiable playbook must not execute.
        log.warning("freshness check failed for %s: %s", playbook_id, exc)
        return Stale(
            stale_deps=[StaleDep(rule_key="<check-failed>", depends_on=0, head=0)]
        )

    if not rows:
        return Fresh()

    return Stale(
        stale_deps=[
            StaleDep(
                rule_key=r["rule_key"],
                depends_on=r["depends_on"],
                head=r["head"],
            )
            for r in rows
        ]
    )


async def bulk_check_freshness(
    playbook_ids: list[UUID], db
) -> dict[UUID, FreshnessResult]:
    """Same join across many playbooks — one query, for the worker's sweep."""
    if not playbook_ids:
        return {}

    try:
        rows = await db.q(
            """
            SELECT d.playbook_id,
                   d.rule_key,
                   d.rule_version AS depends_on,
                   r.version      AS head
            FROM playbook_deps d
            JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
            WHERE d.playbook_id = ANY(%s)
              AND r.version != d.rule_version
            """,
            ([str(pid) for pid in playbook_ids],),
        )
    except Exception as exc:
        log.warning("bulk freshness check failed: %s", exc)
        return {
            pid: Stale(
                stale_deps=[StaleDep(rule_key="<check-failed>", depends_on=0, head=0)]
            )
            for pid in playbook_ids
        }

    stale_by_playbook: dict[UUID, list[StaleDep]] = {}
    for row in rows:
        pid = row["playbook_id"]
        if isinstance(pid, str):
            pid = UUID(pid)
        stale_by_playbook.setdefault(pid, []).append(
            StaleDep(
                rule_key=row["rule_key"],
                depends_on=row["depends_on"],
                head=row["head"],
            )
        )

    return {
        pid: (
            Stale(stale_deps=stale_by_playbook[pid])
            if pid in stale_by_playbook
            else Fresh()
        )
        for pid in playbook_ids
    }
