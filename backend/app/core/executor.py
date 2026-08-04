"""Task executor — explore and guided paths (spec §5.2, §5.4, D4).

OWNER: Shawki (Track B).

    retrieve -> freshness -> guided        (warm: no planner, just bound steps)
                          -> explore       (cold: Claude plans with tools)

The freshness gate between retrieval and execution is the whole point of the
project: a playbook that matched the query is still refused if any rule it was
compiled against has moved on. Stale knowledge is worse than no knowledge,
because the agent would act on it confidently.

Interrupts are checked immediately before every side-effecting tool call, from
the in-process bus first (microseconds, D4) and the durable
`tasks.interrupt_flag` second. The durable flag is what makes it correct across
processes; the bus is what makes it fast enough to catch a running demo.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from .llm import AgentClient, BudgetExceeded, BudgetTracker, FastClient
from .models import PlaybookCandidate
from .tools import SIDE_EFFECTING, TOOL_DEFINITIONS, TOOL_MAP, get_rules

log = logging.getLogger(__name__)

_INCIDENT_RE = re.compile(r"INC-\d+", re.IGNORECASE)


async def run_task(task_id: UUID, db, sse_bus=None, interrupt_bus=None) -> None:
    """Execute one task end to end, then persist an episode.

    Always leaves the task row in a terminal state — a task stuck in 'running'
    would block the interrupt sweep and skew every metric.
    """
    from app.bus import TOPIC_TASK_STATUS

    started = time.perf_counter()
    interrupt_event = interrupt_bus.register(str(task_id)) if interrupt_bus else None

    try:
        rows = await db.q(
            "SELECT task_id, input, status FROM tasks WHERE task_id = %s",
            (str(task_id),),
        )
        if not rows:
            raise ValueError(f"task {task_id} not found")
        task_text = rows[0]["input"]

        candidate, mode = await _select_mode(task_text, db)

        await db.q(
            "UPDATE tasks SET status = 'running', mode = %s, playbook_id = %s WHERE task_id = %s",
            (mode, str(candidate.playbook_id) if candidate else None, str(task_id)),
        )
        await _publish(
            sse_bus,
            TOPIC_TASK_STATUS.format(task_id=task_id),
            {
                "task_id": str(task_id),
                "status": "running",
                "mode": mode,
                "input": task_text,
                "playbook_id": str(candidate.playbook_id) if candidate else None,
                "playbook_name": candidate.name if candidate else None,
                "playbook_version": candidate.version if candidate else None,
            },
        )

        if mode == "guided":
            status, result, trajectory = await _guided_mode(
                task_id, task_text, candidate, db, sse_bus, interrupt_bus
            )
        else:
            status, result, trajectory = await _explore_mode(
                task_id, task_text, db, sse_bus, interrupt_bus
            )

        # Parked awaiting a human: leave the row in `awaiting_approval` and
        # write nothing terminal. No episode either — the run has not finished,
        # and a half-run recorded as an episode would skew every metric.
        if status == "awaiting_approval":
            await _publish(
                sse_bus,
                TOPIC_TASK_STATUS.format(task_id=task_id),
                {
                    "task_id": str(task_id),
                    "status": "awaiting_approval",
                    "mode": mode,
                    "input": task_text,
                    "steps": len(trajectory),
                },
            )
            log.info("task %s parked awaiting approval", task_id)
            return

        latency_ms = int((time.perf_counter() - started) * 1000)
        outcome = _outcome_for(status)

        episode_id = await _write_episode(
            task_id=task_id,
            mode=mode,
            outcome=outcome,
            trajectory=trajectory,
            latency_ms=latency_ms,
            db=db,
        )

        await db.q(
            """
            UPDATE tasks SET status = %s, result = %s, finished_at = now()
            WHERE task_id = %s
            """,
            (status, result, str(task_id)),
        )

        # A failed or escalated run is also a lesson (T2.5). Recorded as an
        # anti-playbook so the planner is warned next time instead of paying
        # full explore cost to reach the same wall.
        if outcome != "success" or result == "escalated":
            await _record_negative(task_id, task_text, trajectory, result, episode_id, db)

        # Anything that did not cleanly remediate is worth a writeup (T1.3).
        if episode_id and (outcome != "success" or result == "escalated"):
            await db.q(
                "INSERT INTO outbox (kind, payload) VALUES (%s, %s)",
                ("postmortem", json.dumps({"episode_id": str(episode_id)})),
            )

        # Only a cold success teaches us something new worth compiling.
        # The trajectory travels in the payload: `episodes` has no column for
        # it, and inlining keeps compilation working when S3 isn't configured.
        # It is bounded by max_steps_per_task, so the row stays small.
        if mode == "explore" and outcome == "success" and episode_id:
            await db.q(
                "INSERT INTO outbox (kind, payload) VALUES (%s, %s)",
                (
                    "compile",
                    json.dumps(
                        {
                            "task_id": str(task_id),
                            "episode_id": str(episode_id),
                            "task_text": task_text,
                            "trajectory": trajectory,
                        },
                        default=str,
                    ),
                ),
            )

        await _publish(
            sse_bus,
            TOPIC_TASK_STATUS.format(task_id=task_id),
            {
                "task_id": str(task_id),
                "status": status,
                "result": result,
                "mode": mode,
                "input": task_text,
                "latency_ms": latency_ms,
                "steps": len(trajectory),
            },
        )
        await _publish(sse_bus, "metrics.tick", {"task_id": str(task_id)})

        log.info(
            "task %s finished: %s/%s mode=%s steps=%d in %dms",
            task_id,
            status,
            result,
            mode,
            len(trajectory),
            latency_ms,
        )

    except Exception as exc:
        log.exception("task %s failed", task_id)
        await db.q(
            "UPDATE tasks SET status = 'failed', finished_at = now() WHERE task_id = %s",
            (str(task_id),),
        )
        await _publish(
            sse_bus,
            TOPIC_TASK_STATUS.format(task_id=task_id),
            {"task_id": str(task_id), "status": "failed", "error": str(exc)},
        )
        raise
    finally:
        if interrupt_bus:
            interrupt_bus.unregister(str(task_id))
        del interrupt_event


# ---------------------------------------------------------------------------
# Mode selection — retrieval + the freshness gate
# ---------------------------------------------------------------------------


async def _select_mode(task_text: str, db) -> tuple[PlaybookCandidate | None, str]:
    """Decide guided vs explore. Anything short of a fresh hit means explore."""
    from .freshness import check_freshness
    from .retrieval import retrieve

    candidate = await retrieve(task_text, db)
    if candidate is None:
        return None, "explore"

    freshness = await check_freshness(candidate.playbook_id, db)
    if freshness.kind == "stale":
        reason = ", ".join(
            f"{d.rule_key} v{d.depends_on}!=v{d.head}" for d in freshness.stale_deps
        )
        log.info(
            "playbook %s matched but is stale (%s) — exploring instead",
            candidate.playbook_id,
            reason,
        )
        await record_retrieval_event(
            db,
            "retrieval.stale_block",
            {"playbook_id": str(candidate.playbook_id), "stale": reason},
        )
        return None, "explore"

    if candidate.spec is None:
        log.warning("playbook %s has an unparseable spec — exploring", candidate.playbook_id)
        return None, "explore"

    return candidate, "guided"


async def record_retrieval_event(db, kind: str, details: dict[str, Any]) -> None:
    """Log a retrieval decision to audit_log.

    /api/metrics reads these instead of inferring outcomes from task columns.
    Inference was wrong: it counted the cold run that *authored* a playbook as
    a retrieval miss, because that task also carried a playbook_id.
    """
    try:
        await db.q(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, 'system', %s)",
            (kind, json.dumps(details, default=str)),
        )
    except Exception as exc:
        log.warning("could not record %s: %s", kind, exc)


# ---------------------------------------------------------------------------
# Explore (cold)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an on-call operations agent. You resolve incidents \
by calling tools.

Current policy (follow exactly):
{rules}

Non-negotiable:
1. Read the incident before deciding anything.
2. Call check_remediation_eligibility before any apply_remediation, for the same
   incident and action.
3. If policy does not permit automated action, do not force it — notify on-call
   with the reason and finish with outcome='escalated'.
4. Notify on-call after any remediation you apply.
5. Use the fewest tool calls that correctly resolve the incident.

Finish by calling final_answer exactly once.{warnings}"""


async def _explore_mode(
    task_id: UUID, task_text: str, db, sse_bus, interrupt_bus
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Cold path: the planner decides each step."""
    from app.config import settings

    budget = BudgetTracker(
        max_steps=settings.max_steps_per_task,
        max_tokens=settings.max_tokens_per_task,
        max_wall_clock=settings.max_wall_clock_seconds,
    )
    budget.start()

    scratchpad: dict[str, Any] = {"task_text": task_text, "domain": "incident"}
    rules = await get_rules(domain="incident", db=db)
    scratchpad["rules"] = rules.get("rules", [])

    # Pre-resolve the incident so the autonomy gate can weigh blast radius
    # (service tier) without an extra round trip mid-step.
    incident_id = _incident_from(task_text)
    incident = {}
    if incident_id:
        fetched = await TOOL_MAP["get_incident"](incident_id=incident_id, db=db)
        if isinstance(fetched, dict) and not fetched.get("error"):
            incident = fetched

    executor = _ToolExecutor(
        task_id, db, interrupt_bus, scratchpad, sse_bus, incident=incident
    )

    async def on_step(step: dict[str, Any]) -> None:
        await _publish_step(sse_bus, task_id, step, "explore")

    # Negative memory (T2.5): warn the planner about approaches that already
    # failed on this class of incident, so it doesn't pay full explore cost to
    # rediscover the same dead end. Advisory only — policy still decides.
    from .negative_memory import format_warnings, relevant_warnings

    warnings = format_warnings(await relevant_warnings(task_text, db))
    if warnings:
        scratchpad["anti_playbook_warnings"] = True

    try:
        final, trajectory = await AgentClient().converse_with_tools(
            system_prompt=_SYSTEM_PROMPT.format(
                rules=json.dumps(scratchpad["rules"], indent=2, default=str),
                warnings=warnings,
            ),
            initial_message=task_text,
            tools=TOOL_DEFINITIONS,
            tool_executor=executor,
            budget=budget,
            on_step=on_step,
        )
    except _AwaitingApproval:
        # Not a failure: the task is parked and resumes on approval.
        return "awaiting_approval", None, executor.trajectory
    except _Interrupted as exc:
        await _persist_interrupt(task_id, scratchpad, exc.reason, db, sse_bus)
        return "interrupted", None, executor.trajectory
    except BudgetExceeded as exc:
        log.warning("task %s exhausted its budget: %s", task_id, exc)
        return "failed", None, executor.trajectory

    if final.get("outcome") == "success":
        return "succeeded", "remediated", trajectory
    return "succeeded", "escalated", trajectory


# ---------------------------------------------------------------------------
# Guided (warm)
# ---------------------------------------------------------------------------


async def _guided_mode(
    task_id: UUID,
    task_text: str,
    playbook: PlaybookCandidate,
    db,
    sse_bus,
    interrupt_bus,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Warm path: replay a known-good plan with fresh parameters.

    No planner in the loop — that is where the speedup comes from. A
    precondition miss is not a failure of the playbook, so it falls back to
    explore rather than counting against confidence.
    """
    from .confidence import update_confidence

    spec = playbook.spec
    fast = FastClient()

    incident_id = _incident_from(task_text)
    incident = {}
    if incident_id:
        incident = await TOOL_MAP["get_incident"](incident_id=incident_id, db=db)

    precondition = await fast.check_precondition(
        spec.model_dump(), task_text, incident if isinstance(incident, dict) else {}
    )
    if not precondition.get("ok", True):
        failed = precondition.get("failed", [])
        log.info(
            "playbook %s preconditions not met (%s) — falling back to explore",
            playbook.playbook_id,
            "; ".join(failed),
        )
        await record_retrieval_event(
            db,
            "retrieval.precondition_miss",
            {"playbook_id": str(playbook.playbook_id), "failed": failed},
        )
        await db.q(
            "UPDATE tasks SET mode = 'explore', playbook_id = NULL WHERE task_id = %s",
            (str(task_id),),
        )
        return await _explore_mode(task_id, task_text, db, sse_bus, interrupt_bus)

    params = await fast.extract_params(spec.model_dump(), task_text)
    if incident_id:
        params.setdefault("incident_id", incident_id)

    # A generalized runbook (T3.8) declares `incident_kind` and `action` and
    # leaves them to be resolved per incident — that parameterization is what
    # lets one runbook cover several incident classes. Bind them from the
    # incident itself rather than asking a model to guess.
    if isinstance(incident, dict) and incident.get("kind"):
        from .llm import ACTION_FOR_KIND

        params.setdefault("incident_kind", incident["kind"])
        if "action" in spec.params:
            params.setdefault(
                "action", ACTION_FOR_KIND.get(incident["kind"], "restart")
            )

    scratchpad: dict[str, Any] = {
        "task_text": task_text,
        "domain": "incident",
        "playbook_id": str(playbook.playbook_id),
        "params": params,
    }
    executor = _ToolExecutor(
        task_id,
        db,
        interrupt_bus,
        scratchpad,
        sse_bus,
        incident=incident if isinstance(incident, dict) else {},
        playbook_id=playbook.playbook_id,
        playbook_confidence=playbook.confidence,
    )

    budget = BudgetTracker(max_steps=8, max_tokens=5_000, max_wall_clock=30)
    budget.start()

    ineligible_reason: str | None = None

    try:
        for index, step in enumerate(spec.steps):
            # A playbook is a plan, not a licence. If policy has already said no
            # for this incident, the remaining side-effecting steps must not run
            # — guided mode replays steps mechanically, so without this it would
            # call apply_remediation straight past a failed eligibility check.
            # Explore mode gets this for free because the planner reads the
            # result; the guided path has to enforce it explicitly.
            if ineligible_reason and step.tool in SIDE_EFFECTING:
                if step.tool == "apply_remediation":
                    log.info(
                        "guided: skipping %s for task %s — policy says no (%s)",
                        step.tool,
                        task_id,
                        ineligible_reason,
                    )
                    continue

            args = {key: _bind(value, params) for key, value in step.args.items()}
            if ineligible_reason and step.tool == "notify_oncall":
                args["message"] = (
                    f"Manual action required for {params.get('incident_id', 'incident')}: "
                    f"{ineligible_reason}"
                )

            output = await executor(step.tool, args, index)
            await _publish_step(sse_bus, task_id, executor.trajectory[-1], "guided")
            budget.record_step(0)

            if isinstance(output, dict) and output.get("eligible") is False:
                ineligible_reason = (
                    "; ".join(str(r) for r in output.get("reasons", []))
                    or "policy check failed"
                )

            if isinstance(output, dict) and output.get("error"):
                await update_confidence(playbook.playbook_id, success=False, db=db)
                return "failed", None, executor.trajectory

    except _AwaitingApproval:
        # Parked, not failed — confidence must not be penalised for a runbook
        # that was working correctly when a human was asked to confirm.
        return "awaiting_approval", None, executor.trajectory
    except _Interrupted as exc:
        await _persist_interrupt(task_id, scratchpad, exc.reason, db, sse_bus)
        await update_confidence(playbook.playbook_id, success=False, db=db)
        return "interrupted", None, executor.trajectory
    except BudgetExceeded:
        await update_confidence(playbook.playbook_id, success=False, db=db)
        return "failed", None, executor.trajectory

    confidence, status = await update_confidence(
        playbook.playbook_id, success=True, db=db
    )
    await _publish(
        sse_bus,
        "playbook.changed",
        {
            "playbook_id": str(playbook.playbook_id),
            "action": "reinforced",
            "confidence": round(confidence, 3),
            "status": status,
        },
    )

    return (
        "succeeded",
        ("escalated" if ineligible_reason else "remediated"),
        executor.trajectory,
    )


def _bind(value: str, params: dict[str, Any]) -> str:
    """Substitute {param} placeholders declared in the spec."""
    text = str(value)
    for name, bound in params.items():
        text = text.replace(f"{{{name}}}", str(bound))
    return text


# ---------------------------------------------------------------------------
# Tool dispatch with interrupt + idempotency handling
# ---------------------------------------------------------------------------


class _Interrupted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _AwaitingApproval(Exception):
    """A high-risk step was gated; the task parks until a human decides."""

    def __init__(self, approval_id, reason: str) -> None:
        super().__init__(reason)
        self.approval_id = approval_id
        self.reason = reason


class _ToolExecutor:
    """Callable passed to the planner. Owns the trajectory it produces.

    Three responsibilities the planner must not be trusted with: checking for
    interrupts before anything irreversible, minting idempotency keys, and
    enforcing the autonomy gate.
    """

    def __init__(
        self,
        task_id,
        db,
        interrupt_bus,
        scratchpad,
        sse_bus,
        incident: dict[str, Any] | None = None,
        playbook_id=None,
        playbook_confidence: float | None = None,
    ) -> None:
        self.task_id = task_id
        self.db = db
        self.interrupt_bus = interrupt_bus
        self.scratchpad = scratchpad
        self.sse_bus = sse_bus
        self.incident = incident or {}
        self.playbook_id = playbook_id
        self.playbook_confidence = playbook_confidence
        self.trajectory: list[dict[str, Any]] = []

    async def __call__(
        self, tool_name: str, args: dict[str, Any], step_index: int
    ) -> Any:
        if tool_name in SIDE_EFFECTING:
            interrupted, reason = await _check_interrupt(
                self.task_id, self.interrupt_bus, self.db
            )
            if interrupted:
                self.scratchpad["interrupted_at_step"] = step_index
                raise _Interrupted(reason)

            await self._enforce_autonomy(tool_name, args, step_index)

        function = TOOL_MAP.get(tool_name)
        if function is None:
            return {"error": "unknown_tool", "tool": tool_name}

        call_args = dict(args)
        call_args.pop("idempotency_key", None)
        if tool_name in SIDE_EFFECTING:
            # Deterministic per (task, step): a replay after an interrupt
            # collides with the original and is refused by the tool.
            call_args["idempotency_key"] = f"{self.task_id}:{step_index}"

        started = time.perf_counter()
        try:
            output = await function(**call_args, db=self.db)
        except TypeError as exc:
            output = {"error": "bad_arguments", "message": str(exc)}
        duration_ms = int((time.perf_counter() - started) * 1000)

        entry = {
            "step_index": step_index,
            "tool_name": tool_name,
            "tool_input": args,
            "tool_output": output,
            "latency_ms": duration_ms,
            "tokens": 0,
            "at": datetime.now(UTC).isoformat(),
        }
        if len(self.trajectory) <= step_index:
            self.trajectory.append(entry)
        else:
            self.trajectory[step_index] = entry
        return output

    async def _enforce_autonomy(
        self, tool_name: str, args: dict[str, Any], step_index: int
    ) -> None:
        """Park the task if this action needs a human. Raises _AwaitingApproval.

        Cheap check first: an action a human already approved for this task
        proceeds without re-asking, otherwise the resumed run would stop at the
        same gate forever.
        """
        from .autonomy import (
            REQUIRES_APPROVAL,
            decide_autonomy,
            is_pre_approved,
            request_approval,
        )

        incident = self.incident
        if not incident and args.get("incident_id"):
            fetched = await TOOL_MAP["get_incident"](
                incident_id=args["incident_id"], db=self.db
            )
            if isinstance(fetched, dict) and not fetched.get("error"):
                incident = self.incident = fetched

        decision, reason = decide_autonomy(
            tool_name,
            incident=incident,
            playbook_confidence=self.playbook_confidence,
        )
        if decision != REQUIRES_APPROVAL:
            return

        if await is_pre_approved(self.task_id, tool_name, args, self.db):
            log.info(
                "task %s step %d pre-approved by a human, proceeding",
                self.task_id,
                step_index,
            )
            return

        approval_id = await request_approval(
            task_id=self.task_id,
            tool_name=tool_name,
            args=args,
            step_index=step_index,
            reason=reason,
            db=self.db,
            playbook_id=self.playbook_id,
        )
        self.scratchpad["awaiting_approval_at_step"] = step_index
        await self.db.q(
            "UPDATE tasks SET scratchpad = %s WHERE task_id = %s",
            (json.dumps(self.scratchpad, default=str), str(self.task_id)),
        )
        await _publish(
            self.sse_bus,
            "approval.requested",
            {
                "approval_id": str(approval_id),
                "task_id": str(self.task_id),
                "incident_id": args.get("incident_id"),
                "action": f"{tool_name} · {args.get('action', '')}".strip(" ·"),
                "tool": tool_name,
                "reason": reason,
                "risk": "high",
                "confidence": self.playbook_confidence,
                "step_index": step_index,
            },
        )
        raise _AwaitingApproval(approval_id, reason)


async def _check_interrupt(task_id, interrupt_bus, db) -> tuple[bool, str]:
    """In-memory first (D4), durable flag second."""
    if interrupt_bus is not None and interrupt_bus.is_interrupted(str(task_id)):
        return True, interrupt_bus.reason_for(str(task_id)) or "rule changed"

    try:
        rows = await db.q(
            "SELECT interrupt_flag, interrupt_reason FROM tasks WHERE task_id = %s",
            (str(task_id),),
        )
        if rows and rows[0]["interrupt_flag"]:
            return True, rows[0]["interrupt_reason"] or "rule changed"
    except Exception as exc:
        log.warning("durable interrupt check failed for %s: %s", task_id, exc)

    return False, ""


async def _persist_interrupt(
    task_id: UUID, scratchpad: dict[str, Any], reason: str, db, sse_bus
) -> None:
    """Save enough state that the task can be re-planned under the new rules.

    The flag is cleared as the scratchpad lands, so the same interrupt cannot
    fire twice against a task that has already absorbed it.
    """
    rules = await get_rules(domain=scratchpad.get("domain", "incident"), db=db)
    scratchpad["fresh_rules"] = rules.get("rules", [])
    scratchpad["interrupt_reason"] = reason
    scratchpad["interrupted_at"] = datetime.now(UTC).isoformat()

    await db.q(
        """
        UPDATE tasks
        SET scratchpad = %s, interrupt_flag = FALSE, interrupt_reason = %s
        WHERE task_id = %s
        """,
        (json.dumps(scratchpad, default=str), reason, str(task_id)),
    )
    await _publish(
        sse_bus,
        f"task.{task_id}.step",
        {
            "task_id": str(task_id),
            "type": "interrupted",
            "reason": reason,
            "at": scratchpad["interrupted_at"],
        },
    )
    log.info("task %s interrupted: %s", task_id, reason)


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


async def _write_episode(
    task_id: UUID,
    mode: str,
    outcome: str,
    trajectory: list[dict[str, Any]],
    latency_ms: int,
    db,
) -> UUID | None:
    """Persist the run. Returns None when there is nothing to record.

    `episodes.steps` carries a CHECK (steps > 0), so a run that never executed
    a tool has no episode — and correctly contributes nothing to the metrics.
    """
    if not trajectory:
        return None

    episode_id = uuid4()
    tokens = sum(int(entry.get("tokens", 0) or 0) for entry in trajectory)

    # S3 holds the full trajectory; the row keeps the first 10 steps so the
    # dashboard stays useful without a bucket round-trip.
    s3_key = await _upload_trajectory(episode_id, trajectory)

    await db.q(
        """
        INSERT INTO episodes (
            episode_id, task_id, outcome, mode, steps, latency_ms, tokens, s3_key
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(episode_id),
            str(task_id),
            outcome,
            mode,
            len(trajectory),
            max(latency_ms, 0),
            tokens,
            s3_key,
        ),
    )
    return episode_id


async def _upload_trajectory(
    episode_id: UUID, trajectory: list[dict[str, Any]]
) -> str | None:
    from app.config import settings

    bucket = settings.episodes_bucket
    if not bucket or bucket.endswith("-local"):
        return None  # local dev writes no objects

    key = f"episodes/{episode_id}.json"
    try:
        import asyncio

        import boto3

        client = boto3.client("s3", region_name=settings.aws_region)
        await asyncio.to_thread(
            client.put_object,
            Bucket=bucket,
            Key=key,
            Body=json.dumps(trajectory, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return key
    except Exception as exc:
        log.warning("episode trajectory upload failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _record_negative(
    task_id: UUID,
    task_text: str,
    trajectory: list[dict[str, Any]],
    result: str | None,
    episode_id: UUID | None,
    db,
) -> None:
    """Derive why this run did not remediate, and remember it."""
    if not trajectory:
        return

    reason = None
    for entry in trajectory:
        output = entry.get("tool_output")
        if not isinstance(output, dict):
            continue
        if output.get("reasons"):
            reason = "; ".join(str(r) for r in output["reasons"])
            break
        if output.get("error"):
            reason = f"{entry.get('tool_name')}: {output['error']}"
            break

    if reason is None:
        reason = (
            "escalated without an explicit policy reason"
            if result == "escalated"
            else "run did not complete successfully"
        )

    try:
        from .negative_memory import record_failure

        await record_failure(episode_id, task_text, trajectory, reason, db)
    except Exception as exc:
        # Never let bookkeeping fail a task that already finished.
        log.warning("could not record anti-playbook for %s: %s", task_id, exc)


def _outcome_for(status: str) -> str:
    if status == "succeeded":
        return "success"
    if status == "interrupted":
        return "interrupted"
    return "failure"


def _incident_from(task_text: str) -> str | None:
    match = _INCIDENT_RE.search(task_text)
    return match.group(0).upper() if match else None


async def _publish(sse_bus, topic: str, data: dict[str, Any]) -> None:
    if sse_bus is None:
        return
    try:
        await sse_bus.publish(topic, data)
    except Exception as exc:
        log.warning("sse publish to %s failed: %s", topic, exc)


async def _publish_step(
    sse_bus, task_id: UUID, entry: dict[str, Any], mode: str
) -> None:
    output = entry.get("tool_output")
    error = output.get("error") if isinstance(output, dict) else None
    await _publish(
        sse_bus,
        f"task.{task_id}.step",
        {
            "task_id": str(task_id),
            "type": "step",
            "mode": mode,
            "step_index": entry.get("step_index"),
            "tool": entry.get("tool_name"),
            "args": entry.get("tool_input"),
            "output": output,
            "duration_ms": entry.get("latency_ms"),
            "error": error,
        },
    )
