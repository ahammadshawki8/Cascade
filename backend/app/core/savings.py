"""Savings accounting (T1.4).

OWNER: Shawki (Track B).

Turns the architecture story into a business case using data already on disk.
Every guided run is compared against the *measured* cold baseline for the same
mode of work:

    tokens avoided   = guided_runs x (avg_cold_tokens - avg_guided_tokens)
    seconds avoided  = guided_runs x (avg_cold_ms    - avg_guided_ms)

Both baselines come from `episodes`, so this is measurement, not modelling.

Two honesty rules:
  * With fewer than one cold and one guided success there is no baseline, and
    the endpoint says so rather than reporting zero.
  * Token pricing is a published rate multiplied by observed usage. It is
    labelled an estimate because the *rate* is an assumption even though the
    *usage* is not.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Bedrock on-demand, us-east-1, USD per 1M tokens. Blended input/output at a
# 3:1 ratio, which is roughly what the explore loop produces.
# Override with CASCADE_USD_PER_MTOK if the model mix changes.
DEFAULT_USD_PER_MTOK = 1.60

# What an engineer would otherwise spend hand-running a runbook end to end.
# Deliberately conservative: the claim should survive an SRE pushing back on it.
MANUAL_MINUTES_PER_INCIDENT = 12.0


async def compute_savings(db) -> dict[str, Any]:
    """Cumulative savings attributable to reuse."""
    from app.config import settings

    rows = await db.q(
        """
        SELECT mode,
               count(*)::INT        AS runs,
               avg(tokens)::FLOAT   AS avg_tokens,
               avg(latency_ms)::FLOAT AS avg_ms,
               sum(tokens)::INT     AS total_tokens
        FROM episodes
        WHERE outcome = 'success'
        GROUP BY mode
        """
    )
    by_mode = {r["mode"]: r for r in rows}
    cold = by_mode.get("explore")
    guided = by_mode.get("guided")

    if not cold or not guided or not guided["runs"]:
        return {
            "available": False,
            "message": (
                "Need at least one successful cold run and one guided run "
                "before a baseline exists."
            ),
            "guided_runs": (guided or {}).get("runs", 0),
            "cold_runs": (cold or {}).get("runs", 0),
        }

    guided_runs = guided["runs"]
    tokens_per_run = max(0.0, (cold["avg_tokens"] or 0) - (guided["avg_tokens"] or 0))
    ms_per_run = max(0.0, (cold["avg_ms"] or 0) - (guided["avg_ms"] or 0))

    tokens_avoided = int(tokens_per_run * guided_runs)
    seconds_avoided = (ms_per_run * guided_runs) / 1000.0

    usd_per_mtok = float(
        getattr(settings, "usd_per_mtok", None) or DEFAULT_USD_PER_MTOK
    )
    usd_saved = (tokens_avoided / 1_000_000.0) * usd_per_mtok

    # Toil is counted per *automated* incident, not per guided run: the value is
    # that a human never opened the runbook, regardless of which mode resolved it.
    automated = (cold["runs"] or 0) + guided_runs
    engineer_minutes = automated * MANUAL_MINUTES_PER_INCIDENT

    speedup = (
        (cold["avg_ms"] / guided["avg_ms"]) if guided["avg_ms"] else None
    )

    return {
        "available": True,
        "guided_runs": guided_runs,
        "cold_runs": cold["runs"],
        "tokens_avoided": tokens_avoided,
        "usd_saved": round(usd_saved, 4),
        "usd_per_mtok": usd_per_mtok,
        "seconds_avoided": round(seconds_avoided, 1),
        "engineer_hours_saved": round(engineer_minutes / 60.0, 2),
        "incidents_automated": automated,
        "speedup": round(speedup, 1) if speedup else None,
        "avg_cold_ms": round(cold["avg_ms"] or 0, 1),
        "avg_guided_ms": round(guided["avg_ms"] or 0, 1),
        "avg_cold_tokens": round(cold["avg_tokens"] or 0, 1),
        "avg_guided_tokens": round(guided["avg_tokens"] or 0, 1),
        "basis": (
            "Token and latency deltas are measured from recorded episodes. "
            "The USD figure applies a published per-token rate to that measured "
            "usage and is therefore an estimate."
        ),
    }
