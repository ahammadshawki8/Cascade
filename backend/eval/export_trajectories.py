"""Export what the agents actually did, from what was recorded at the time.

OWNER: evaluation harness. Not imported by the running application.

    python -m eval.export_trajectories --api https://<host> --out eval/out

WHY THIS READS RATHER THAN RECONSTRUCTS
---------------------------------------
Every run already stores its own trajectory. `episodes.trajectory` (migration
005) holds the calls a run made, in order, with the arguments it passed and what
came back, and `audit_log` holds the retrieval decisions that explain why the
run took the path it did. So a trajectory document is an export, not a write-up.

That distinction is the whole point. A hand-written transcript of what an agent
"would have done" is a plausible reconstruction, and a plausible reconstruction
is exactly what this project exists to be suspicious of. These are the calls
that happened, including the ones that were refused.

WHICH RUNS GET EXPORTED
-----------------------
Four shapes, because they are four different behaviours and a reader needs all
four to see the loop:

  explore    nothing in memory, the planner decides each step
  guided     a runbook matched, was checked, and replayed with no model call
  refused    a runbook matched by meaning and was refused on provenance
  gated      the autonomy gate parked the run for a human

Selection is by what the run turned out to be, read back from `/explain`, not by
incident id. Hardcoding ids would break the moment the demo world is reseeded,
and would also let a run be labelled a refusal without having refused anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

# reason -> (heading, what the reader should take from it)
SHAPES: dict[str, tuple[str, str]] = {
    "explore": (
        "Explore: nothing in memory",
        "The planner decides each step. Policy is consulted through a tool "
        "rather than described in the prompt, so the model cannot talk its way "
        "past a rule it does not like.",
    ),
    "guided": (
        "Guided: a runbook matched and was replayed",
        "No model call anywhere on this path. Retrieval is a vector index, "
        "freshness is a join, and the preconditions are a predicate "
        "evaluation, so the same incident gets the same answer every time.",
    ),
    "refused_stale": (
        "Refused: matched by meaning, refused on provenance",
        "The runbook was still the closest match by vector distance and still "
        "looked healthy. It was refused because a rule it was compiled against "
        "has moved. This is the behaviour the whole system exists for.",
    ),
    "refused_precondition": (
        "Refused: matched, then failed its own preconditions",
        "A retrieval hit followed by a precondition miss is not a near miss. "
        "It is a runbook that cannot be reused, and it is the signal that a "
        "compiled precondition has overfitted to the incident it was learned "
        "from.",
    ),
    "gated": (
        "Gated: parked for a human",
        "Policy permitted the action but the runbook had not yet earned the "
        "right to take it unsupervised. Approving re-runs the task, which is "
        "only safe because every side-effecting tool is idempotent on "
        "(task_id, step_index).",
    ),
}


class Client:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.headers = {"x-admin-token": token} if token else {}
        self.http = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def get(self, path: str) -> Any:
        r = await self.http.get(f"{self.base}{path}", headers=self.headers)
        r.raise_for_status()
        return r.json()


def classify(task: dict[str, Any], explain: dict[str, Any]) -> str:
    """What this run turned out to be.

    Read back from the recorded decision rather than assumed from the input, so
    a run can only be filed as a refusal if something actually refused.
    """
    if task.get("status") == "awaiting_approval":
        return "gated"
    reason = str(explain.get("reason") or "")
    if reason in {"refused_stale", "refused_precondition"}:
        return reason
    if task.get("mode") == "guided":
        return "guided"
    return "explore"


def render(
    shape: str, task: dict[str, Any], explain: dict[str, Any], steps: dict[str, Any]
) -> str:
    heading, takeaway = SHAPES[shape]
    out: list[str] = []
    add = out.append

    add(f"## {heading}\n")
    add(f"{takeaway}\n")

    add("\n### What was asked\n")
    add("```")
    add(str(task.get("input", "")).strip())
    add("```\n")

    incident = explain.get("incident") or {}
    if incident:
        add("\n### The incident, as the tools saw it\n")
        add("```json")
        add(json.dumps(incident, indent=2, default=str))
        add("```\n")

    add("\n### Calls the run made\n")
    entries = steps.get("steps") or []
    if not entries:
        retained = steps.get("retained", True)
        add(
            "_No call detail retained for this run._\n"
            if not retained
            else "_This run made no tool calls._\n"
        )
    for entry in entries:
        idx = entry.get("step_index")
        add(f"\n**Step {idx} — `{entry.get('tool')}`**")
        took = entry.get("duration_ms")
        if took is not None:
            add(f"_{took} ms_\n")
        add("\nArguments:")
        add("```json")
        add(json.dumps(entry.get("args") or {}, indent=2, default=str))
        add("```")
        add("\nWhat the tool returned:")
        add("```json")
        add(json.dumps(entry.get("output"), indent=2, default=str))
        add("```")

    refusal = explain.get("refusal")
    if refusal:
        add("\n### Why it was refused\n")
        add("```json")
        add(json.dumps(refusal, indent=2, default=str))
        add("```\n")
        add(
            "\nNote that the refusal names the rule, the version the runbook "
            "expects and the version that is live. A refusal a reader cannot "
            "act on is only half a refusal.\n"
        )

    episode = explain.get("episode") or {}
    add("\n### Outcome\n")
    add(f"- Mode: `{task.get('mode')}`")
    add(f"- Result: `{task.get('result')}`")
    add(f"- Status: `{task.get('status')}`")
    if episode:
        add(f"- Steps: {episode.get('steps')}")
        add(f"- Wall clock: {episode.get('latency_ms')} ms")
        add(f"- Planner tokens: {episode.get('tokens')}")
    add("")
    return "\n".join(out)


async def main(args: argparse.Namespace) -> int:
    client = Client(args.api, args.admin_token)
    try:
        listing = await client.get("/api/tasks")
        tasks = listing if isinstance(listing, list) else listing.get("tasks", [])
        if not tasks:
            print(
                "No runs recorded. Run some incidents first, or run the "
                "evaluation harness, then export.",
                file=sys.stderr,
            )
            return 1

        chosen: dict[str, tuple[dict, dict, dict]] = {}
        for task in tasks:
            if len(chosen) == len(SHAPES):
                break
            task_id = task.get("task_id")
            if not task_id:
                continue
            try:
                explain = await client.get(f"/api/tasks/{task_id}/explain")
                steps = await client.get(f"/api/tasks/{task_id}/steps")
            except Exception:
                continue
            shape = classify(task, explain)
            # First of each shape wins: the listing is newest-first, so this
            # takes the most recent example of each behaviour.
            chosen.setdefault(shape, (task, explain, steps))

        if not chosen:
            print("No run could be classified.", file=sys.stderr)
            return 1

        doc: list[str] = [
            "# Agent trajectories\n",
            "Exported from what was recorded at the time, not written up "
            "afterwards. Each run stores its own call sequence in "
            "`episodes.trajectory`, and the retrieval decisions that explain "
            "the path it took are audit rows. So these are the calls that "
            "happened, including the refused ones.\n",
            f"\nExported from `{args.api}`.\n",
            "\nRegenerate with:\n",
            "```bash",
            "python -m eval.export_trajectories --api <host> --admin-token <token>",
            "```\n",
        ]
        for shape in SHAPES:
            if shape in chosen:
                task, explain, steps = chosen[shape]
                doc.append("\n---\n")
                doc.append(render(shape, task, explain, steps))

        missing = [s for s in SHAPES if s not in chosen]
        if missing:
            doc.append("\n---\n")
            doc.append("## Not represented in this export\n")
            doc.append(
                "These behaviours exist but no recent run exercised them, so "
                "nothing is shown rather than something being invented:\n"
            )
            for shape in missing:
                doc.append(f"- {SHAPES[shape][0]}")
            doc.append("")

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "AGENT_TRAJECTORIES.md"
        target.write_text("\n".join(doc), encoding="utf-8")
        print(f"wrote {target} covering: {', '.join(sorted(chosen))}")
        return 0
    finally:
        await client.aclose()


def cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--admin-token", default="")
    p.add_argument("--out", default="eval/out")
    return asyncio.run(main(p.parse_args()))


if __name__ == "__main__":
    sys.exit(cli())
