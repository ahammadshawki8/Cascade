"""Head-to-head evaluation: two baselines against Cascade, same cases, same model.

OWNER: evaluation harness. Not imported by the running application.

    python -m eval.run_eval --api https://<host> --admin-token <token>
    python -m eval.run_eval --arm baseline          # skip the Cascade arm
    python -m eval.run_eval --dry-run               # print the plan, call nothing

WHAT IS BEING MEASURED
----------------------
Primary metric: **policy-correct decision rate**. For an on-call engineer,
success is not speed. It is not running the wrong procedure.

Secondary: unsafe-action rate (remediated where policy forbids it -- the error
that actually hurts), wall-clock latency, planner tokens.

THE SHAPE OF THE EXPERIMENT
---------------------------
Every incident is decided twice, under two policy states:

    phase 1   rollback_window = 24h    the policy the runbooks were learned under
    phase 2   rollback_window = 4h     the same world, one rule tightened

Phase 1 establishes that all three arms can read a rule and apply it. It is not
the interesting half, and it is not meant to be: if an arm fails here it is
broken in some ordinary way and the phase 2 result would say nothing.

Phase 2 is the experiment. Nothing about the incidents changes. One rule moves,
and the question is which arms notice. An arm holding a remembered procedure
that was correct yesterday has to work out that it is not correct today, and
the only thing that can tell it so is a mechanism that records what the
procedure was derived from.

WHY THE ORDER WITHIN A PHASE MATTERS
------------------------------------
Cascade cannot reuse a runbook it has not learned, so each phase begins by
resetting the world and running INC-1001 cold to compile one. Skip that and
every case runs in explore mode, the reuse path is never exercised at all, and
the run measures nothing it claims to.

The reset is also load-bearing for a duller reason: `002_seed.sql` writes deploy
timestamps as `NOW() - INTERVAL '2 hours'`, which ages. Without a reset at the
top of each phase, every bad deploy is already outside the window and both
phases produce the same answer for the wrong reason.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from eval import baseline as base
from eval.cases import (
    ESCALATE,
    REMEDIATE,
    Case,
    build_cases,
    policy_prose,
)

WINDOW_RULE = "incident.rollback_window"
PHASE_ONE_HOURS = 24
PHASE_TWO_HOURS = 4
LEARN_INCIDENT = "INC-1001"

ARMS = ("single_prompt", "naive_cache", "cascade")


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclass
class Outcome:
    """One arm's answer on one case, scored."""

    arm: str
    phase: int
    incident_id: str
    expected: str
    actual: str
    correct: bool
    unsafe: bool
    """Remediated where policy forbids it. Strictly worse than the other kind of
    error: over-escalating wastes a human's time, this one takes an action
    nobody sanctioned."""
    latency_ms: int
    tokens: int
    mode: str | None = None
    rationale: str = ""
    expected_reasons: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class Report:
    started_at: str
    api: str
    model_note: str
    outcomes: list[Outcome] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


class Api:
    """Thin client for the deployed stack.

    Deliberately talks HTTP rather than importing the engine. The Cascade arm
    has to be measured the way anything else would consume it, and an in-process
    call would quietly exclude serialisation, the queue and the worker from the
    latency it reports.
    """

    def __init__(self, base_url: str, admin_token: str, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.headers = {"x-admin-token": admin_token}
        self.client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def get(self, path: str) -> Any:
        r = await self.client.get(f"{self.base}{path}", headers=self.headers)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, body: dict | None = None) -> Any:
        r = await self.client.post(
            f"{self.base}{path}", json=body or {}, headers=self.headers
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    # -- operations ---------------------------------------------------------

    async def reset(self) -> None:
        await self.post("/api/admin/reset")

    async def incidents(self) -> list[dict[str, Any]]:
        return (await self.get("/api/mock/incidents")).get("incidents", [])

    async def rules(self) -> list[dict[str, Any]]:
        data = await self.get("/api/rules")
        return data if isinstance(data, list) else data.get("rules", [])

    async def set_window(self, hours: int) -> dict[str, Any]:
        """Commit the cascade that tightens the rollback window."""
        return await self.post(
            f"/api/rules/{WINDOW_RULE}", {"params": {"hours": hours}}
        )

    async def run_task(self, text: str, poll: float = 1.5, limit: float = 180.0) -> dict:
        """Submit an incident and wait for it to reach a terminal state."""
        created = await self.post("/api/tasks", {"input": text})
        task_id = created["task_id"]
        deadline = time.monotonic() + limit
        terminal = {"succeeded", "failed", "interrupted", "awaiting_approval"}
        while time.monotonic() < deadline:
            task = await self.get(f"/api/tasks/{task_id}")
            if task.get("status") in terminal:
                return task
            await asyncio.sleep(poll)
        return {"task_id": task_id, "status": "timeout", "result": None, "mode": None}

    async def explain(self, task_id: str) -> dict[str, Any]:
        try:
            return await self.get(f"/api/tasks/{task_id}/explain")
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


def _score(arm: str, phase: int, case: Case, actual: str, **kw: Any) -> Outcome:
    correct = actual == case.expected
    return Outcome(
        arm=arm,
        phase=phase,
        incident_id=case.incident_id,
        expected=case.expected,
        actual=actual,
        correct=correct,
        unsafe=(actual == REMEDIATE and case.expected == ESCALATE),
        expected_reasons=list(case.reasons),
        **kw,
    )


async def run_cascade(api: Api, phase: int, cases: list[Case]) -> list[Outcome]:
    out: list[Outcome] = []
    for case in cases:
        started = time.perf_counter()
        try:
            task = await api.run_task(f"Remediate {case.incident_id}")
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.perf_counter() - started) * 1000)
            out.append(
                _score(
                    "cascade", phase, case, ESCALATE,
                    latency_ms=elapsed, tokens=0, error=str(exc),
                )
            )
            continue
        elapsed = int((time.perf_counter() - started) * 1000)

        # `awaiting_approval` is not a decision. The autonomy gate parked the
        # run for a human, which is a refusal to act unsupervised -- scored as
        # escalation because that is what it is from the user's side.
        result = task.get("result")
        actual = REMEDIATE if result == "remediated" else ESCALATE

        detail = await api.explain(str(task.get("task_id")))
        episode = detail.get("episode") or {}
        out.append(
            _score(
                "cascade", phase, case, actual,
                latency_ms=int(episode.get("latency_ms") or elapsed),
                tokens=int(episode.get("tokens") or 0),
                mode=task.get("mode"),
                rationale=str(task.get("interrupt_reason") or result or ""),
            )
        )
    return out


async def run_baselines(
    phase: int, cases: list[Case], policy_now: str, policy_at_learn: str
) -> list[Outcome]:
    out: list[Outcome] = []
    for case in cases:
        single = await base.single_prompt(case, policy_now)
        out.append(
            _score(
                "single_prompt", phase, case, single.decision,
                latency_ms=single.latency_ms, tokens=single.tokens,
                rationale=single.rationale, error=single.error,
            )
        )

        runbook = base.remembered_runbook(case, policy_at_learn)
        cached = await base.naive_cache(case, policy_now, runbook)
        out.append(
            _score(
                "naive_cache", phase, case, cached.decision,
                latency_ms=cached.latency_ms, tokens=cached.tokens,
                rationale=cached.rationale, error=cached.error,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _rate(rows: list[Outcome], pred) -> float:
    return (100.0 * sum(1 for r in rows if pred(r)) / len(rows)) if rows else 0.0


def summarise(report: Report) -> dict[str, Any]:
    summary: dict[str, Any] = {"by_arm": {}, "by_phase": {}}
    for arm in ARMS:
        rows = [o for o in report.outcomes if o.arm == arm]
        if not rows:
            continue
        summary["by_arm"][arm] = {
            "cases": len(rows),
            "correct_pct": round(_rate(rows, lambda r: r.correct), 1),
            "unsafe_actions": sum(1 for r in rows if r.unsafe),
            "median_latency_ms": int(statistics.median(r.latency_ms for r in rows)),
            "total_tokens": sum(r.tokens for r in rows),
        }
        for phase in (1, 2):
            sub = [r for r in rows if r.phase == phase]
            if not sub:
                continue
            summary["by_phase"].setdefault(f"phase{phase}", {})[arm] = {
                "correct_pct": round(_rate(sub, lambda r: r.correct), 1),
                "unsafe_actions": sum(1 for r in sub if r.unsafe),
            }
    return summary


def to_markdown(report: Report, summary: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Evaluation results\n")
    add(f"Run {report.started_at} against `{report.api}`.\n")
    add(f"{report.model_note}\n")

    add("\n## Headline\n")
    add("| Metric | " + " | ".join(ARMS) + " |")
    add("|---|" + "---|" * len(ARMS))
    for label, key, fmt in (
        ("Policy-correct decisions", "correct_pct", lambda v: f"{v}%"),
        ("Unsafe actions", "unsafe_actions", str),
        ("Median latency", "median_latency_ms", lambda v: f"{v:,} ms"),
        ("Planner tokens", "total_tokens", lambda v: f"{v:,}"),
    ):
        cells = []
        for arm in ARMS:
            stats = summary["by_arm"].get(arm)
            cells.append(fmt(stats[key]) if stats else "-")
        add(f"| {label} | " + " | ".join(cells) + " |")

    add("\n## By phase\n")
    add("Phase 1 is the policy the runbooks were learned under. Phase 2 is the")
    add("same world with `rollback_window` tightened from 24h to 4h. Nothing")
    add("else changes.\n")
    add("| Phase | " + " | ".join(ARMS) + " |")
    add("|---|" + "---|" * len(ARMS))
    for phase in (1, 2):
        block = summary["by_phase"].get(f"phase{phase}", {})
        cells = []
        for arm in ARMS:
            stats = block.get(arm)
            if not stats:
                cells.append("-")
            else:
                unsafe = stats["unsafe_actions"]
                mark = f" ({unsafe} unsafe)" if unsafe else ""
                cells.append(f"{stats['correct_pct']}%{mark}")
        add(f"| Phase {phase} | " + " | ".join(cells) + " |")

    add("\n## Every case\n")
    add("| Phase | Incident | Expected | " + " | ".join(ARMS) + " |")
    add("|---|---|---|" + "---|" * len(ARMS))
    seen = sorted({(o.phase, o.incident_id) for o in report.outcomes})
    for phase, inc in seen:
        row = [f"| {phase} | `{inc}` |"]
        expected = next(
            (o.expected for o in report.outcomes if o.phase == phase and o.incident_id == inc),
            "?",
        )
        row.append(f" {expected} |")
        for arm in ARMS:
            hit = next(
                (
                    o
                    for o in report.outcomes
                    if o.arm == arm and o.phase == phase and o.incident_id == inc
                ),
                None,
            )
            if hit is None:
                row.append(" - |")
            else:
                mark = "ok" if hit.correct else ("**UNSAFE**" if hit.unsafe else "**wrong**")
                row.append(f" {hit.actual} {mark} |")
        add("".join(row))

    if report.notes:
        add("\n## Notes\n")
        for note in report.notes:
            add(f"- {note}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def _phase(
    api: Api,
    phase: int,
    hours: int,
    arms: set[str],
    report: Report,
    policy_at_learn: str | None,
) -> str:
    print(f"\n=== phase {phase}: rollback_window = {hours}h ===", flush=True)

    await api.reset()
    if hours != PHASE_ONE_HOURS:
        impact = await api.set_window(hours)
        report.notes.append(
            f"Phase {phase}: cascade committed in {impact.get('writes', '?')} writes, "
            f"invalidating {len(impact.get('impacted_playbooks', []))} runbook(s)."
        )

    if "cascade" in arms:
        print(f"  learning a runbook from {LEARN_INCIDENT} ...", flush=True)
        learned = await api.run_task(f"Remediate {LEARN_INCIDENT}")
        report.notes.append(
            f"Phase {phase}: learn run finished {learned.get('status')}"
            f"/{learned.get('result')} in mode {learned.get('mode')}."
        )

    incidents = await api.incidents()
    rules = await api.rules()
    cases = build_cases(incidents, rules)
    policy_now = policy_prose(rules)
    learn_policy = policy_at_learn or policy_now

    print(f"  {len(cases)} cases", flush=True)

    if {"single_prompt", "naive_cache"} & arms:
        report.outcomes += [
            o
            for o in await run_baselines(phase, cases, policy_now, learn_policy)
            if o.arm in arms
        ]
    if "cascade" in arms:
        report.outcomes += await run_cascade(api, phase, cases)

    return policy_now


async def main(args: argparse.Namespace) -> int:
    arms = set(ARMS) if args.arm == "both" else (
        {"cascade"} if args.arm == "cascade" else {"single_prompt", "naive_cache"}
    )

    report = Report(
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        api=args.api,
        model_note=(
            "Both baselines call the same provider chain and the same model as "
            "Cascade's planner (`bedrock_agent_model_id`), through "
            "`app.core.llm._chat`. No arm is given a weaker model."
        ),
    )

    if args.dry_run:
        print(json.dumps({"arms": sorted(arms), "phases": [1, 2]}, indent=2))
        return 0

    api = Api(args.api, args.admin_token)
    try:
        learn_policy = await _phase(api, 1, PHASE_ONE_HOURS, arms, report, None)
        await _phase(api, 2, PHASE_TWO_HOURS, arms, report, learn_policy)
        if not args.keep:
            await api.reset()
            report.notes.append("World restored to the sample after the run.")
    finally:
        await api.aclose()

    summary = summarise(report)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(
            {
                "started_at": report.started_at,
                "api": report.api,
                "model_note": report.model_note,
                "summary": summary,
                "notes": report.notes,
                "outcomes": [asdict(o) for o in report.outcomes],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "RESULTS.md").write_text(to_markdown(report, summary), encoding="utf-8")

    print("\n" + to_markdown(report, summary))
    print(f"wrote {out_dir / 'results.json'} and {out_dir / 'RESULTS.md'}")
    return 0


def cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    p.add_argument("--admin-token", default="dev-admin-token")
    p.add_argument("--arm", choices=("both", "baseline", "cascade"), default="both")
    p.add_argument("--out", default="eval/out", help="where to write results")
    p.add_argument("--keep", action="store_true", help="do not reset when finished")
    p.add_argument("--dry-run", action="store_true")
    return asyncio.run(main(p.parse_args()))


if __name__ == "__main__":
    sys.exit(cli())
