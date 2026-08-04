"""Insight engine — the agent proposes policy changes (T1.2, spec §9).

OWNER: Shawki (Track B).

Learn / reuse / unlearn is reactive: policy changes, memory adapts. This closes
the loop in the other direction — memory notices a pattern and asks a human
whether the *policy* should change.

Every insight is derived from recorded evidence (episodes, audit events, the
mock action log) by deterministic SQL. A model may only phrase the summary, and
only when one is available; it never invents the finding, because a fabricated
policy recommendation is far worse than a dull one.

Insights are idempotent on `fingerprint`, so the periodic scan updates a
standing finding instead of stacking duplicates in the reviewer's queue.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# Don't nag on a single data point — a "trend" of one is noise.
MIN_SAMPLES = 3

# The threshold detector is judged on impact, not sample size: a policy that is
# demonstrably blocking even two remediations it could safely permit is worth
# surfacing, because the recommendation is verifiable by replay rather than
# extrapolated. Raise this in a busier environment.
MIN_BLOCKED = 2


async def scan_for_insights(db) -> list[dict[str, Any]]:
    """Run every detector and upsert what they find. Returns new/updated rows."""
    found: list[dict[str, Any]] = []
    for detector in (
        _detect_blocking_rule,
        _detect_failure_pattern,
        _detect_coverage_gap,
    ):
        try:
            found.extend(await detector(db))
        except Exception as exc:
            log.warning("insight detector %s failed: %s", detector.__name__, exc)

    stored = []
    for insight in found:
        if await _upsert(insight, db):
            stored.append(insight)
    if stored:
        log.info("insight scan produced %d finding(s)", len(stored))
    return stored


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


async def _detect_blocking_rule(db) -> list[dict[str, Any]]:
    """A threshold that is costing more automation than it is buying safety.

    Built on the counterfactual engine (T2.2) rather than a hand-rolled band:
    for each candidate widening, actually re-decide every historical incident
    and count how many the change would recover. The recommendation is then a
    measurement — "widening to 8h recovers 3 incidents" — not an extrapolation,
    and it is the same computation the operator can re-run from the Policy
    Panel before committing.
    """
    from .analysis import counterfactual_replay

    window_rule = await db.q(
        """
        SELECT version, params FROM rules
        WHERE rule_key = 'incident.rollback_window' AND valid_to IS NULL
        """
    )
    if not window_rule:
        return []

    params = window_rule[0]["params"] or {}
    current = float(params.get("hours", 24))

    # Derive candidate windows from the incidents actually being blocked, so
    # the suggestion lands on the real cluster instead of an arbitrary
    # multiple. Fixed multipliers miss whenever the blocked incidents sit far
    # from the current threshold.
    blocked = await db.q(
        """
        SELECT ceil(EXTRACT(EPOCH FROM (now() - deploy_timestamp)) / 3600)::INT AS age_hours
        FROM mock_incidents
        WHERE kind = 'bad_deploy'
          AND state = 'open'
          AND deploy_timestamp IS NOT NULL
          AND EXTRACT(EPOCH FROM (now() - deploy_timestamp)) / 3600 > %s
        ORDER BY age_hours
        """,
        (current,),
    )
    if len(blocked) < MIN_BLOCKED:
        return []

    # One candidate per blocked incident's age (+1h of headroom), smallest
    # first, so the recommendation is the least change that clears the bar.
    candidates = sorted({int(r["age_hours"]) + 1 for r in blocked})

    best: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate <= current:
            continue
        try:
            replay = await counterfactual_replay(
                "incident.rollback_window", {"hours": candidate}, db
            )
        except Exception:
            continue

        recovered = len(replay["newly_allowed"])
        # Only ever recommend a strictly safer-or-equal trade: a widening that
        # also blocks something is not a clean win and must not be suggested.
        if recovered >= MIN_BLOCKED and not replay["newly_blocked"]:
            # Candidates are ascending, so the first qualifying one is the
            # smallest sufficient change — stop rather than over-recommending.
            best = {
                "hours": candidate,
                "recovered": recovered,
                "incidents": [i["incident_id"] for i in replay["newly_allowed"]],
                "examined": replay["incidents_examined"],
            }
            break

    if best is None:
        return []

    return [
        {
            "kind": "threshold_trend",
            "fingerprint": f"rollback_window:{int(current)}",
            "summary": (
                f"The {int(current)}h rollback window is currently blocking "
                f"{best['recovered']} bad-deploy incidents that policy would "
                f"otherwise auto-remediate. Widening it to {best['hours']}h "
                f"recovers all {best['recovered']} and blocks nothing new."
            ),
            "related_rule_key": "incident.rollback_window",
            "suggested_params": {"hours": best["hours"]},
            "evidence": {
                "current_window_hours": current,
                "suggested_window_hours": best["hours"],
                "incidents_recovered": best["recovered"],
                "incident_ids": best["incidents"],
                "incidents_examined": best["examined"],
                "method": "counterfactual replay over recorded incidents",
            },
        }
    ]


async def _detect_failure_pattern(db) -> list[dict[str, Any]]:
    """A runbook failing often enough that it should not be trusted."""
    rows = await db.q(
        """
        SELECT playbook_id, name, version, uses, successes, failures, confidence,
               status_cache
        FROM playbooks
        WHERE uses >= %s AND failures > successes
        """,
        (MIN_SAMPLES,),
    )
    insights = []
    for row in rows:
        rate = row["failures"] / max(1, row["uses"])
        insights.append(
            {
                "kind": "failure_pattern",
                "fingerprint": f"failing_playbook:{row['playbook_id']}",
                "summary": (
                    f"Runbook '{row['name']}' v{row['version']} has failed "
                    f"{row['failures']} of {row['uses']} runs "
                    f"({rate:.0%}). Its confidence is {row['confidence']:.2f}. "
                    "Consider re-learning it or retiring it."
                ),
                "related_rule_key": None,
                "suggested_params": None,
                "evidence": {
                    "playbook_id": str(row["playbook_id"]),
                    "uses": row["uses"],
                    "failures": row["failures"],
                    "successes": row["successes"],
                    "failure_rate": round(rate, 3),
                },
            }
        )
    return insights


async def _detect_coverage_gap(db) -> list[dict[str, Any]]:
    """An incident class the system keeps exploring but never learns."""
    rows = await db.q(
        """
        SELECT i.kind, count(*)::INT AS explored
        FROM episodes e
        JOIN tasks t ON t.task_id = e.task_id
        JOIN mock_incidents i
          ON position(i.incident_id in t.input) > 0
        WHERE e.mode = 'explore'
        GROUP BY i.kind
        HAVING count(*) >= %s
        """,
        (MIN_SAMPLES,),
    )
    if not rows:
        return []

    insights = []
    for row in rows:
        covered = await db.q(
            """
            SELECT count(*)::INT AS n FROM playbooks
            WHERE status_cache IN ('active', 'candidate')
              AND spec::STRING ILIKE %s
            """,
            (f"%{row['kind']}%",),
        )
        if covered and covered[0]["n"] > 0:
            continue
        insights.append(
            {
                "kind": "coverage_gap",
                "fingerprint": f"coverage_gap:{row['kind']}",
                "summary": (
                    f"'{row['kind']}' incidents have been explored from scratch "
                    f"{row['explored']} times without producing a reusable "
                    "runbook. The compiler may be rejecting these trajectories."
                ),
                "related_rule_key": None,
                "suggested_params": None,
                "evidence": {"incident_kind": row["kind"], "explorations": row["explored"]},
            }
        )
    return insights


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _upsert(insight: dict[str, Any], db) -> bool:
    """Insert, or refresh an existing finding. False if nothing changed."""
    existing = await db.q(
        "SELECT insight_id, summary, dismissed FROM insights WHERE fingerprint = %s",
        (insight["fingerprint"],),
    )

    if existing:
        row = existing[0]
        # A dismissed insight stays dismissed — re-raising it every scan would
        # make the feature nagware and train operators to ignore the rail.
        if row["dismissed"] or row["summary"] == insight["summary"]:
            return False
        await db.q(
            """
            UPDATE insights
            SET summary = %s, suggested_params = %s, evidence = %s
            WHERE insight_id = %s
            """,
            (
                insight["summary"],
                json.dumps(insight["suggested_params"]) if insight["suggested_params"] else None,
                json.dumps(insight["evidence"], default=str),
                str(row["insight_id"]),
            ),
        )
        return True

    await db.q(
        """
        INSERT INTO insights (
            kind, summary, related_rule_key, suggested_params, evidence, fingerprint
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            insight["kind"],
            insight["summary"],
            insight["related_rule_key"],
            json.dumps(insight["suggested_params"]) if insight["suggested_params"] else None,
            json.dumps(insight["evidence"], default=str),
            insight["fingerprint"],
        ),
    )
    return True
