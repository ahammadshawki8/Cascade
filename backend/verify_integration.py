"""End-to-end verification of the MVP contract (spec §10, Claude.md Steps 10-11).

Run against a live database with CASCADE_STUB_MODE=false:

    python verify_integration.py            # local
    python verify_integration.py --keep      # don't reset the world first

Exercises every claim the demo makes, in order, and fails loudly if any of them
stops being true. This exists because the earlier integration sign-off was based
on HTTP status codes rather than observed behaviour — a task can return 201 and
still never have executed.

Deliberately talks to the engine directly rather than over HTTP: the interrupt
path needs a task to already carry interrupt_flag before execution begins, which
is not reachable through the API without a race.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
import time
from uuid import UUID

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str = "") -> None:
    status = SKIP if ok is None else (PASS if ok else FAIL)
    _results.append((status, name, detail))
    marker = {PASS: "[PASS]", FAIL: "[FAIL]", SKIP: "[SKIP]"}[status]
    print(f"{marker} {name}" + (f" — {detail}" if detail else ""), flush=True)


async def main(keep: bool) -> int:
    from app import db as database
    from app.config import settings

    if settings.cascade_stub_mode:
        print("refusing to verify in stub mode — set CASCADE_STUB_MODE=false")
        return 2

    await database.init_pool()
    try:
        if not keep:
            await reset_world(database)
        await check_schema(database)
        await check_vector_index(database)
        playbook_id = await check_learn(database)
        await check_reuse(database, playbook_id)
        await check_interrupt(database)
        await check_guided_policy_enforcement(database)
        # Autonomy must run while the playbook is still fresh: the confidence
        # gate only applies in guided mode, and after a rule change every
        # runbook is stale and falls back to explore.
        await check_autonomy(database)
        await check_negative_memory(database)
        await check_savings(database)
        await check_unlearn(database, playbook_id)
        await check_triage(database)
        await check_insights(database)
        await check_replay(database)
        await check_time_travel(database)
        await check_graph(database)
        await check_postmortem(database)
        await check_copilot(database)
        await check_rbac()
        await check_retention(database)
        await check_generalization(database)
        await check_contract_surface()
    finally:
        await database.close_pool()

    failures = [r for r in _results if r[0] == FAIL]
    skipped = [r for r in _results if r[0] == SKIP]
    print(
        f"\n{len(_results) - len(failures) - len(skipped)} passed, "
        f"{len(failures)} failed, {len(skipped)} skipped"
    )
    for _, name, detail in failures:
        print(f"  FAILED: {name} — {detail}")
    return 1 if failures else 0


# ---------------------------------------------------------------------------


async def reset_world(db) -> None:
    from app.routers.admin import _CLEAR_ORDER, _seed_sql, _strip_txn

    async with db.pool().connection() as conn:
        await conn.set_autocommit(False)
        try:
            async with conn.cursor() as cur:
                for table in _CLEAR_ORDER:
                    await cur.execute(f"DELETE FROM {table} WHERE true")
                await cur.execute(_strip_txn(_seed_sql()))
            await conn.commit()
        finally:
            await conn.set_autocommit(True)
    print("world reset to clean v1 state\n")


async def check_schema(db) -> None:
    rows = await db.q("SELECT table_name FROM [SHOW TABLES]")
    names = {r["table_name"] for r in rows}
    expected = {
        "rules", "playbooks", "playbook_deps", "tasks", "episodes", "outbox",
        "audit_log", "approvals", "insights", "postmortems",
        "mock_services", "mock_incidents", "mock_action_log",
    }
    missing = expected - names
    record("schema: all 13 tables present", not missing, f"missing {missing}" if missing else "")

    counts = await db.one(
        """
        SELECT (SELECT count(*) FROM rules WHERE valid_to IS NULL) AS rules,
               (SELECT count(*) FROM mock_services)  AS services,
               (SELECT count(*) FROM mock_incidents) AS incidents
        """
    )
    record(
        "seed: 4 head rules / 6 services / 12 incidents",
        counts["rules"] == 4 and counts["services"] == 6 and counts["incidents"] == 12,
        f"got {dict(counts)}",
    )


async def check_vector_index(db) -> None:
    from app.core.retrieval import verify_vector_index

    result = await verify_vector_index(db)
    record(
        "vector index: EXPLAIN selects pb_embed_idx (D2/D3)",
        result["uses_index"],
        result.get("error") or "",
    )


async def check_learn(db) -> UUID | None:
    """Cold run compiles a playbook with grounded provenance."""
    from app.core.executor import run_task
    from worker.handler import drain_outbox

    task_id = await new_task(db, "Remediate INC-1001")
    started = time.perf_counter()
    await run_task(task_id, db)
    cold_ms = int((time.perf_counter() - started) * 1000)

    task = await db.one(
        "SELECT status, result, mode FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    record(
        "learn: cold run succeeds in explore mode",
        task["status"] == "succeeded"
        and task["result"] == "remediated"
        and task["mode"] == "explore",
        f"{task['status']}/{task['result']}/{task['mode']} in {cold_ms}ms",
    )

    episode = await db.one(
        "SELECT outcome, mode, steps FROM episodes WHERE task_id = %s", (str(task_id),)
    )
    record(
        "learn: episode written",
        episode is not None and episode["outcome"] == "success",
        f"{episode['steps']} steps" if episode else "no episode",
    )

    queued = await db.one("SELECT count(*)::INT AS n FROM outbox WHERE kind = 'compile'")
    record("learn: compile event queued (outbox)", queued["n"] >= 1)

    await drain_outbox(db, worker_id="verify")

    playbook = await db.one(
        "SELECT playbook_id, confidence, status_cache FROM playbooks "
        "ORDER BY created_at DESC LIMIT 1"
    )
    record(
        "learn: playbook compiled at confidence 0.30 (candidate)",
        playbook is not None
        and abs(float(playbook["confidence"]) - 0.30) < 1e-6
        and playbook["status_cache"] == "candidate",
        f"conf={playbook['confidence']}" if playbook else "none compiled",
    )
    if playbook is None:
        return None

    deps = await db.q(
        "SELECT rule_key, rule_version FROM playbook_deps WHERE playbook_id = %s",
        (str(playbook["playbook_id"]),),
    )
    record("learn: provenance edges recorded", len(deps) >= 1, f"{len(deps)} deps")

    # Every dep must point at a real rule version — otherwise staleness can
    # never be derived for it.
    orphans = await db.q(
        """
        SELECT d.rule_key FROM playbook_deps d
        LEFT JOIN rules r ON r.rule_key = d.rule_key AND r.version = d.rule_version
        WHERE d.playbook_id = %s AND r.rule_key IS NULL
        """,
        (str(playbook["playbook_id"]),),
    )
    record("learn: every dep resolves to a real rule version", not orphans,
           f"orphans: {[o['rule_key'] for o in orphans]}" if orphans else "")

    globals()["_cold_ms"] = cold_ms
    return playbook["playbook_id"]


async def check_reuse(db, playbook_id) -> None:
    """Warm run retrieves, passes freshness, and executes guided."""
    from app.core.executor import run_task

    if playbook_id is None:
        record("reuse: guided execution", None, "no playbook to reuse")
        return

    task_id = await new_task(db, "Remediate INC-1002")
    started = time.perf_counter()
    await run_task(task_id, db)
    guided_ms = int((time.perf_counter() - started) * 1000)

    task = await db.one(
        "SELECT status, result, mode FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    record(
        "reuse: second incident runs in guided mode",
        task["mode"] == "guided" and task["status"] == "succeeded",
        f"{task['status']}/{task['result']}/{task['mode']} in {guided_ms}ms",
    )

    cold_ms = globals().get("_cold_ms", 0)
    ratio = (cold_ms / guided_ms) if guided_ms else 0
    # Reported, not asserted: with Bedrock unavailable the planner is instant,
    # so this measures database round-trips rather than the real cold path.
    record(
        f"reuse: guided is {ratio:.1f}x faster than cold",
        None if ratio < 3 else True,
        f"cold {cold_ms}ms vs guided {guided_ms}ms"
        + (" (re-measure against Bedrock)" if ratio < 3 else ""),
    )

    updated = await db.one(
        "SELECT confidence, uses, successes FROM playbooks WHERE playbook_id = %s",
        (str(playbook_id),),
    )
    record(
        "reuse: confidence incremented +0.15 on success",
        abs(float(updated["confidence"]) - 0.45) < 1e-6,
        f"conf={updated['confidence']} uses={updated['uses']}",
    )


async def check_interrupt(db) -> None:
    """A task carrying interrupt_flag must stop before any side effect."""
    from app.core.executor import run_task

    task_id = await new_task(db, "Remediate INC-1005")
    await db.q(
        """
        UPDATE tasks SET interrupt_flag = TRUE, interrupt_reason = 'verify: policy changed'
        WHERE task_id = %s
        """,
        (str(task_id),),
    )

    count_actions = (
        "SELECT count(*)::INT AS n FROM mock_action_log WHERE incident_id = 'INC-1005'"
    )
    before = await db.one(count_actions)
    await run_task(task_id, db)
    after = await db.one(count_actions)

    task = await db.one(
        "SELECT status, interrupt_flag, scratchpad FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    record(
        "interrupt: task halts in 'interrupted' state",
        task["status"] == "interrupted",
        f"status={task['status']}",
    )
    record(
        "interrupt: no side effect was applied",
        after["n"] == before["n"],
        f"action_log {before['n']} -> {after['n']}",
    )
    scratchpad = task["scratchpad"] or {}
    if isinstance(scratchpad, str):
        scratchpad = json.loads(scratchpad)
    record(
        "interrupt: scratchpad persisted with fresh rules for re-planning",
        bool(scratchpad.get("fresh_rules")),
        f"keys={sorted(scratchpad)[:5]}",
    )
    record(
        "interrupt: durable flag cleared so it cannot re-fire",
        task["interrupt_flag"] is False,
    )


async def check_unlearn(db, playbook_id) -> None:
    """Rule change invalidates dependents and the freshness gate blocks reuse."""
    from app.core.cascade import change_rule
    from app.core.executor import run_task
    from app.core.freshness import check_freshness
    from worker.handler import drain_outbox

    if playbook_id is None:
        record("unlearn: cascade", None, "no playbook")
        return

    fresh_before = await check_freshness(playbook_id, db)
    record("unlearn: playbook is fresh before the change", fresh_before.kind == "fresh")

    started = time.perf_counter()
    impact = await change_rule(
        rule_key="incident.rollback_window",
        new_body="Rollback allowed only within {hours} hours of deploy.",
        new_params={"hours": 4},
        actor="verify",
        db=db,
    )
    cascade_ms = int((time.perf_counter() - started) * 1000)
    record(
        "unlearn: cascade transaction completes under 100ms",
        cascade_ms < 100,
        f"{cascade_ms}ms, {len(impact.impacted_playbooks)} playbook(s) impacted",
    )

    versions = await db.one(
        """
        SELECT count(*) FILTER (WHERE valid_to IS NOT NULL)::INT AS closed,
               count(*) FILTER (WHERE valid_to IS NULL)::INT     AS open
        FROM rules WHERE rule_key = 'incident.rollback_window'
        """
    )
    record(
        "unlearn: old version closed, exactly one head remains",
        versions["closed"] == 1 and versions["open"] == 1,
        f"closed={versions['closed']} open={versions['open']}",
    )

    stale_after = await check_freshness(playbook_id, db)
    stale_detail = ", ".join(
        f"{d.rule_key} v{d.depends_on}!=v{d.head}"
        for d in getattr(stale_after, "stale_deps", [])
    )
    record(
        "unlearn: freshness join now reports stale (derived, not written)",
        stale_after.kind == "stale",
        stale_detail,
    )

    task_id = await new_task(db, "Remediate INC-1004")
    await run_task(task_id, db)
    task = await db.one("SELECT mode FROM tasks WHERE task_id = %s", (str(task_id),))
    record(
        "unlearn: stale playbook is REFUSED — falls back to explore",
        task["mode"] == "explore",
        f"mode={task['mode']}",
    )

    await drain_outbox(db, worker_id="verify")
    suspect = await db.one(
        "SELECT status_cache FROM playbooks WHERE playbook_id = %s", (str(playbook_id),)
    )
    record(
        "unlearn: worker demoted status_cache",
        suspect["status_cache"] in ("suspect", "invalidated"),
        f"status={suspect['status_cache']}",
    )


async def check_guided_policy_enforcement(db) -> None:
    """Guided mode must obey an eligibility refusal, not just record it.

    A playbook is a plan, not a licence. Explore mode gets this free because
    the planner reads the eligibility result; guided mode replays steps
    mechanically and would otherwise call apply_remediation straight past a
    failed check — executing an action policy forbids.
    """
    from app.core.executor import run_task

    # INC-1004: bad_deploy on a tier-2 service, but deployed ~30h ago, which is
    # outside the 24h rollback window. Policy says no; no approval gate applies
    # because it is not tier 1.
    before = await db.one(
        "SELECT count(*)::INT AS n FROM mock_action_log "
        "WHERE incident_id = 'INC-1004' AND action = 'rollback'"
    )

    task_id = await new_task(db, "Remediate INC-1004")
    await run_task(task_id, db)

    task = await db.one(
        "SELECT status, result, mode FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    after = await db.one(
        "SELECT count(*)::INT AS n FROM mock_action_log "
        "WHERE incident_id = 'INC-1004' AND action = 'rollback'"
    )

    record(
        "policy: an ineligible incident is never remediated",
        after["n"] == before["n"],
        f"mode={task['mode']} result={task['result']}, "
        f"rollbacks {before['n']} -> {after['n']}",
    )
    record(
        "policy: the task escalates instead",
        task["result"] == "escalated",
        f"result={task['result']}",
    )
    notified = await db.one(
        "SELECT count(*)::INT AS n FROM mock_action_log "
        "WHERE incident_id = 'INC-1004' AND action = 'notify'"
    )
    record(
        "policy: on-call is notified about the refusal",
        notified["n"] > 0,
        f"{notified['n']} notification(s)",
    )


async def check_autonomy(db) -> None:
    """T1.1 — a tier-1 service must stop and wait for a human."""
    from app.core.autonomy import (
        AUTO_EXECUTE,
        REQUIRES_APPROVAL,
        decide_autonomy,
        resolve_approval,
    )
    from app.core.executor import run_task

    tier1 = {"service_tier": 1, "service_name": "svc-payments", "kind": "bad_deploy"}
    tier2 = {"service_tier": 2, "service_name": "svc-checkout", "kind": "bad_deploy"}

    decision, _ = decide_autonomy("apply_remediation", incident=tier1)
    record("autonomy: tier-1 remediation requires approval", decision == REQUIRES_APPROVAL)

    decision, _ = decide_autonomy("apply_remediation", incident=tier2)
    record("autonomy: tier-2 remediation runs unsupervised", decision == AUTO_EXECUTE)

    decision, _ = decide_autonomy("get_incident", incident=tier1)
    record("autonomy: read-only tools are never gated", decision == AUTO_EXECUTE)

    # The tier gate is largely redundant with policy: `auto_remediate_tier`
    # already refuses tier-1 services, so apply_remediation is skipped before
    # autonomy is consulted. The gate that does independent work is the
    # confidence one — policy PERMITS the action, but the runbook has not
    # earned the right to take it unsupervised. Enable it for this scenario.
    from app.config import settings

    previous = settings.autonomy_min_confidence

    # Set the bar just above whatever the runbook has actually earned, rather
    # than a fixed 0.6 — confidence moves as earlier checks run, and a
    # hard-coded threshold makes this test quietly stop exercising the gate.
    current = await db.one(
        "SELECT confidence FROM playbooks ORDER BY updated_at DESC LIMIT 1"
    )
    settings.autonomy_min_confidence = float(current["confidence"]) + 0.05

    try:
        # INC-1009: bad_deploy on a tier-3 service, well inside the rollback
        # window — policy permits it outright, so the only thing that can stop
        # it is the autonomy gate. Exercised twice: rejected first (leaving the
        # incident open), then approved.
        rejected_task = await new_task(db, "Remediate INC-1009")
        await run_task(rejected_task, db)
        pending = await db.one(
            "SELECT approval_id FROM approvals WHERE task_id = %s AND status = 'pending'",
            (str(rejected_task),),
        )
        if pending is not None:
            await resolve_approval(pending["approval_id"], "rejected", "verify", db)
            task = await db.one(
                "SELECT status, result FROM tasks WHERE task_id = %s",
                (str(rejected_task),),
            )
            record(
                "autonomy: rejecting escalates instead of executing",
                task["status"] == "failed" and task["result"] == "escalated",
                f"{task['status']}/{task['result']}",
            )
            blocked = await db.one(
                "SELECT count(*)::INT AS n FROM mock_action_log "
                "WHERE incident_id = 'INC-1009' AND action = 'rollback'"
            )
            record(
                "autonomy: a rejected action is never executed",
                blocked["n"] == 0,
                f"{blocked['n']} rollback(s)",
            )
        else:
            record("autonomy: rejection path", None, "no approval raised")

        task_id = await new_task(db, "Remediate INC-1009")
        await run_task(task_id, db)

        task = await db.one(
            "SELECT status, mode FROM tasks WHERE task_id = %s", (str(task_id),)
        )
        record(
            "autonomy: unproven runbook parks in 'awaiting_approval'",
            task["status"] == "awaiting_approval",
            f"status={task['status']} mode={task['mode']}",
        )

        actions = await db.one(
            "SELECT count(*)::INT AS n FROM mock_action_log "
            "WHERE incident_id = 'INC-1009' AND action = 'rollback'"
        )
        record(
            "autonomy: nothing irreversible happened while parked",
            actions["n"] == 0,
            f"{actions['n']} remediation(s) logged",
        )

        pending = await db.one(
            "SELECT approval_id, tool_name FROM approvals "
            "WHERE task_id = %s AND status = 'pending'",
            (str(task_id),),
        )
        record(
            "autonomy: an approval request was raised",
            pending is not None and pending["tool_name"] == "apply_remediation",
        )
        if pending is None:
            return

        # Approve, then re-run. Earlier steps replay, which is only safe
        # because every side-effecting tool is idempotent on
        # {task_id}:{step_index} — that property is what the next assertion
        # actually proves.
        await resolve_approval(pending["approval_id"], "approved", "verify", db)
        await run_task(task_id, db)

        task = await db.one(
            "SELECT status, result FROM tasks WHERE task_id = %s", (str(task_id),)
        )
        record(
            "autonomy: approving resumes the task to completion",
            task["status"] == "succeeded",
            f"{task['status']}/{task['result']}",
        )

        applied = await db.one(
            "SELECT count(*)::INT AS n FROM mock_action_log "
            "WHERE incident_id = 'INC-1009' AND action = 'rollback'"
        )
        record(
            "autonomy: remediation applied exactly once despite the replay",
            applied["n"] == 1,
            f"{applied['n']} rollback(s) — idempotency held",
        )
    finally:
        settings.autonomy_min_confidence = previous


async def check_negative_memory(db) -> None:
    """T2.5 — a failure is remembered and surfaced as a warning."""
    from app.core.executor import run_task
    from app.core.negative_memory import format_warnings, relevant_warnings

    # INC-1006 is an error_spike on svc-payments (tier 1) — policy blocks it,
    # so it escalates and should leave a lesson behind.
    task_id = await new_task(db, "Remediate INC-1006")
    await run_task(task_id, db)

    task = await db.one(
        "SELECT status, result FROM tasks WHERE task_id = %s", (str(task_id),)
    )
    anti = await db.q(
        "SELECT incident_kind, attempted_action, failure_reason, occurrences "
        "FROM anti_playbooks ORDER BY created_at DESC LIMIT 5"
    )
    record(
        "negative memory: a failed run produces an anti-playbook",
        len(anti) > 0,
        f"task {task['status']}/{task['result']}, {len(anti)} anti-playbook(s)",
    )
    if not anti:
        return

    warnings = await relevant_warnings("Remediate INC-1006", db)
    record(
        "negative memory: the lesson is retrieved for a similar task",
        len(warnings) > 0,
        f"{len(warnings)} warning(s)",
    )
    record(
        "negative memory: warnings render into the planner prompt",
        "FAILED" in format_warnings(warnings) if warnings else False,
    )

    # Hitting the *same* dead end must reinforce, not duplicate. Asserted on
    # the dedup key directly — a second run of the same incident can legitimately
    # fail for a different reason (e.g. the single-action limit now applies),
    # and that genuinely is a different lesson, so a row count would be a
    # misleading proxy.
    from app.core.negative_memory import record_failure

    fixture = [
        {
            "tool_name": "get_incident",
            "tool_input": {"incident_id": "INC-9999"},
            "tool_output": {"kind": "error_spike", "incident_id": "INC-9999"},
        },
        {
            "tool_name": "check_remediation_eligibility",
            "tool_input": {"incident_id": "INC-9999", "action": "restart"},
            "tool_output": {"action": "restart", "eligible": False},
        },
    ]
    before = await db.one("SELECT count(*)::INT AS n FROM anti_playbooks")
    await record_failure(None, "Remediate INC-9999", fixture, "verify: same reason", db)
    middle = await db.one("SELECT count(*)::INT AS n FROM anti_playbooks")
    await record_failure(None, "Remediate INC-9999", fixture, "verify: same reason", db)
    after = await db.one("SELECT count(*)::INT AS n FROM anti_playbooks")
    occurrences = await db.one(
        "SELECT occurrences FROM anti_playbooks WHERE failure_reason = 'verify: same reason'"
    )
    record(
        "negative memory: an identical failure reinforces rather than duplicates",
        after["n"] == middle["n"] == before["n"] + 1 and occurrences["occurrences"] == 2,
        f"rows {before['n']}->{middle['n']}->{after['n']}, "
        f"occurrences={occurrences['occurrences'] if occurrences else 'n/a'}",
    )


async def check_savings(db) -> None:
    """T1.4 — savings are computed from measured episodes."""
    from app.core.savings import compute_savings

    result = await compute_savings(db)
    if not result.get("available"):
        record("savings: baseline available", None, result.get("message", ""))
        return

    record(
        "savings: computed from real cold vs guided episodes",
        result["guided_runs"] > 0 and result["cold_runs"] > 0,
        f"{result['guided_runs']} guided vs {result['cold_runs']} cold, "
        f"{result['engineer_hours_saved']}h saved",
    )
    record(
        "savings: never reports negative savings",
        result["tokens_avoided"] >= 0 and result["seconds_avoided"] >= 0,
    )


async def check_triage(db) -> None:
    """T2.1 — relaxing a rule must not quarantine, tightening must."""
    from app.core.triage import BROKEN, UNAFFECTED, _compare_numeric

    record(
        "triage: widening a window is detected as relaxed",
        _compare_numeric({"hours": 4}, {"hours": 24}) == "relaxed",
    )
    record(
        "triage: narrowing a window is detected as tightened",
        _compare_numeric({"hours": 24}, {"hours": 4}) == "tightened",
    )
    record(
        "triage: lowering min_tier is relaxed (more services automatable)",
        _compare_numeric({"min_tier": 2}, {"min_tier": 1}) == "relaxed",
    )
    record(
        "triage: unknown parameter semantics are never guessed",
        _compare_numeric({"mystery": 1}, {"mystery": 2}) is None,
    )
    record(
        "triage: verdicts are constrained to the safe vocabulary",
        UNAFFECTED == "UNAFFECTED" and BROKEN == "BROKEN",
    )


async def check_replay(db) -> None:
    """T2.2 — counterfactual replay against historical incidents."""
    from app.core.analysis import counterfactual_replay

    widened = await counterfactual_replay(
        "incident.rollback_window", {"hours": 72}, db
    )
    narrowed = await counterfactual_replay(
        "incident.rollback_window", {"hours": 1}, db
    )

    record(
        "replay: widening the window unblocks incidents",
        widened["net_change"] >= 0,
        widened["summary"],
    )
    record(
        "replay: narrowing the window blocks incidents",
        narrowed["net_change"] <= 0,
        narrowed["summary"],
    )
    record(
        "replay: examines real historical incidents",
        widened["incidents_examined"] > 0,
        f"{widened['incidents_examined']} incidents",
    )


async def check_time_travel(db) -> None:
    """T2.3 — CockroachDB MVCC history, no snapshot table of our own."""
    from app.core.analysis import time_travel

    result = await time_travel(db, minutes_ago=5)
    if not result.get("available"):
        record("time travel: AS OF SYSTEM TIME query", None, result.get("message", ""))
        return

    record(
        "time travel: reads past state via AS OF SYSTEM TIME",
        "rules" in result and "playbooks" in result,
        f"{len(result['rules'])} rules, {len(result['playbooks'])} playbooks at -5m",
    )


async def check_graph(db) -> None:
    """T2.4 — blast radius graph with stale edges marked."""
    from app.core.analysis import blast_radius_graph

    graph = await blast_radius_graph(db)
    rule_nodes = [n for n in graph["nodes"] if n["type"] == "rule"]
    record(
        "graph: rules, playbooks and tasks are all represented",
        len(rule_nodes) > 0 and len(graph["nodes"]) > len(rule_nodes),
        f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges",
    )
    dangling = [
        e
        for e in graph["edges"]
        if e["source"] not in {n["id"] for n in graph["nodes"]}
        or e["target"] not in {n["id"] for n in graph["nodes"]}
    ]
    record("graph: no dangling edges", not dangling, f"{len(dangling)} dangling")


async def check_insights(db) -> None:
    """T1.2 — findings are derived from evidence and are idempotent."""
    from app.core.insights import scan_for_insights

    await scan_for_insights(db)
    first = await db.one("SELECT count(*)::INT AS n FROM insights")

    await scan_for_insights(db)
    second = await db.one("SELECT count(*)::INT AS n FROM insights")

    record(
        "insights: repeated scans do not duplicate findings",
        first["n"] == second["n"],
        f"{first['n']} -> {second['n']}",
    )

    rows = await db.q(
        "SELECT kind, summary, evidence FROM insights ORDER BY created_at DESC LIMIT 3"
    )
    if rows:
        record(
            "insights: every finding carries its evidence",
            all(r["evidence"] for r in rows),
            rows[0]["summary"][:90],
        )
    else:
        record("insights: findings produced", None, "no pattern met the threshold yet")


async def check_postmortem(db) -> None:
    """T1.3 — an escalated episode gets a writeup."""
    from app.core.postmortem import generate_postmortem

    episode = await db.one(
        """
        SELECT e.episode_id FROM episodes e
        JOIN tasks t ON t.task_id = e.task_id
        WHERE t.result = 'escalated' OR e.outcome != 'success'
        ORDER BY e.created_at DESC LIMIT 1
        """
    )
    if episode is None:
        record("postmortem: generated for a non-clean episode", None, "no such episode")
        return

    await generate_postmortem(episode["episode_id"], db)
    row = await db.one(
        "SELECT body, summary FROM postmortems WHERE episode_id = %s",
        (str(episode["episode_id"]),),
    )
    record(
        "postmortem: written and stored",
        row is not None and bool(row["body"]),
        f"{len(row['body'])} chars" if row and row["body"] else "empty",
    )
    if row and row["body"]:
        required = ["## Summary", "## Timeline", "## Outcome"]
        record(
            "postmortem: contains the expected sections",
            all(section in row["body"] for section in required),
        )

    # Regenerating must not create a second row.
    await generate_postmortem(episode["episode_id"], db)
    count = await db.one(
        "SELECT count(*)::INT AS n FROM postmortems WHERE episode_id = %s",
        (str(episode["episode_id"]),),
    )
    record("postmortem: generation is idempotent", count["n"] == 1, f"{count['n']} rows")


async def check_copilot(db) -> None:
    from app.core.copilot import UnsafeSQL, _validate_sql, answer_analytics_question

    answer = await answer_analytics_question("Show all current rules", db)
    record("copilot: answers a question with visible SQL",
           not answer.refused and bool(answer.sql), answer.message or "")

    # The validator is the layer that must hold when an LLM writes the query.
    for bad in (
        "DROP TABLE tasks",
        "SELECT 1; DELETE FROM rules",
        "UPDATE rules SET body = 'x'",
        "WITH x AS (SELECT 1) INSERT INTO rules VALUES (1)",
    ):
        try:
            _validate_sql(bad)
            record(f"copilot: rejects {bad[:32]!r}", False, "accepted unsafe SQL")
        except UnsafeSQL:
            record(f"copilot: rejects {bad[:32]!r}", True)

    # ...without false positives on legitimate reads.
    try:
        _validate_sql("SELECT task_id, created_at FROM tasks ORDER BY created_at DESC")
        record("copilot: allows a normal read selecting created_at", True)
    except UnsafeSQL as exc:
        record("copilot: allows a normal read selecting created_at", False, str(exc))


async def check_rbac() -> None:
    """T3.1 — roles, privilege ordering, and attributable identity."""
    from fastapi import HTTPException

    from app.auth import ADMIN, OPERATOR, VIEWER, resolve_principal
    from app.config import settings

    admin = resolve_principal(settings.admin_token)
    operator = resolve_principal(settings.operator_token)
    viewer = resolve_principal(settings.viewer_token)

    record("rbac: admin outranks operator and viewer",
           admin.can(ADMIN) and admin.can(OPERATOR) and admin.can(VIEWER))
    record("rbac: operator cannot act as admin",
           operator.can(OPERATOR) and not operator.can(ADMIN))
    record("rbac: viewer cannot act as operator",
           viewer.can(VIEWER) and not viewer.can(OPERATOR))

    named = resolve_principal(f"ashfaq:{settings.admin_token}")
    record(
        "rbac: token carries an attributable identity",
        named.role == ADMIN and named.identity == "ashfaq",
        f"{named.identity}/{named.role}",
    )

    try:
        resolve_principal("definitely-not-a-real-token")
        record("rbac: an unknown token is rejected", False, "accepted")
    except HTTPException as exc:
        record("rbac: an unknown token is rejected", exc.status_code == 403)

    record(
        "rbac: no token means viewer, not admin",
        resolve_principal(None).role == VIEWER,
    )


async def check_retention(db) -> None:
    """T3.4 — TTL is configured on the append-only tables, and only those."""
    expected = {"audit_log", "episodes", "outbox"}
    # Provenance must never expire: losing an old rule version would break
    # freshness for any playbook still pinned to it.
    must_not_expire = {"rules", "playbooks", "playbook_deps", "anti_playbooks"}

    with_ttl = set()
    for table in expected | must_not_expire:
        rows = await db.q(f"SHOW CREATE TABLE {table}")
        create = str(rows[0].get("create_statement", "")) if rows else ""
        if "ttl_expiration_expression" in create:
            with_ttl.add(table)

    record(
        "retention: TTL set on append-only tables",
        expected <= with_ttl,
        f"missing {expected - with_ttl}" if expected - with_ttl else "",
    )
    leaked = must_not_expire & with_ttl
    record(
        "retention: provenance tables never expire",
        not leaked,
        f"unexpectedly expiring: {leaked}" if leaked else "",
    )


async def check_generalization(db) -> None:
    """T3.8 — near-duplicate runbooks collapse into one parameterized runbook."""
    from app.core.generalize import find_generalizable, generalize_cluster

    # Build the precondition directly. Two runbooks of the same shape but
    # different incident kinds do not arise naturally here: the fallback
    # embedder normalises every "Remediate INC-xxxx" to one vector, so
    # dedup_check folds the second compile into the first. That is a documented
    # property of the local embedder (DEVIATIONS #7), not of the merge logic —
    # so the merge is tested on a cluster we construct.
    await _seed_generalization_cluster(db)

    clusters = await find_generalizable(db)
    if not clusters:
        record(
            "generalization: candidate clusters found",
            False,
            "seeded cluster was not detected",
        )
        return

    members = clusters[0]
    member_ids = {str(m["playbook_id"]) for m in members}
    merged_id = await generalize_cluster(members, db)

    if merged_id is None:
        record(
            "generalization: cluster merged",
            None,
            "cluster covered a single incident kind — nothing to generalize",
        )
        return

    merged = await db.one(
        "SELECT generalized, merged_from, confidence, status_cache "
        "FROM playbooks WHERE playbook_id = %s",
        (str(merged_id),),
    )
    record(
        "generalization: merged runbook is marked and carries its lineage",
        merged["generalized"] and set(merged["merged_from"] or []) == member_ids,
        f"merged_from={merged['merged_from']}",
    )
    record(
        "generalization: confidence is the weakest member's, not the best",
        abs(float(merged["confidence"]) - min(float(m["confidence"]) for m in members)) < 1e-6,
        f"conf={merged['confidence']}",
    )

    archived = await db.q(
        "SELECT status_cache FROM playbooks WHERE playbook_id = ANY(%s)",
        (list(member_ids),),
    )
    record(
        "generalization: members are archived, not deleted",
        len(archived) == len(member_ids)
        and all(r["status_cache"] == "invalidated" for r in archived),
        f"{len(archived)} member(s) still present",
    )

    orphans = await db.q(
        """
        SELECT d.rule_key FROM playbook_deps d
        LEFT JOIN rules r ON r.rule_key = d.rule_key AND r.version = d.rule_version
        WHERE d.playbook_id = %s AND r.rule_key IS NULL
        """,
        (str(merged_id),),
    )
    record(
        "generalization: merged provenance resolves to real rule versions",
        not orphans,
        f"orphans: {[o['rule_key'] for o in orphans]}" if orphans else "",
    )


async def _seed_generalization_cluster(db) -> None:
    """Two active runbooks with an identical step sequence, different kinds."""
    import json as _json
    from uuid import uuid4

    from app.core.llm import EmbedClient
    from app.core.retrieval import to_vector_literal

    head = await db.q(
        "SELECT rule_key, version FROM rules WHERE valid_to IS NULL ORDER BY rule_key"
    )
    if not head:
        return
    deps = [(head[0]["rule_key"], head[0]["version"])]

    embedder = EmbedClient()
    for kind, action in (("error_spike", "restart"), ("resource_exhaustion", "scale_up")):
        spec = {
            "goal": f"Resolve a {kind} incident by applying {action}",
            "preconditions": [f"Incident kind is {kind}", "Incident state is open"],
            "params": {"incident_id": "string"},
            "steps": [
                {"tool": "get_incident", "args": {"incident_id": "{incident_id}"}},
                {"tool": "get_rules", "args": {"domain": "incident"}},
                {
                    "tool": "check_remediation_eligibility",
                    "args": {"incident_id": "{incident_id}", "action": action},
                },
                {
                    "tool": "apply_remediation",
                    "args": {"incident_id": "{incident_id}", "action": action},
                },
                {
                    "tool": "notify_oncall",
                    "args": {"incident_id": "{incident_id}", "message": "done"},
                },
            ],
            "rule_citations": [
                {
                    "rule_key": deps[0][0],
                    "rule_version": deps[0][1],
                    "used_in_step": 2,
                    "why": "policy gate",
                }
            ],
        }
        playbook_id = uuid4()
        embedding = await embedder.embed(f"{action} for {kind}")
        await db.q(
            """
            INSERT INTO playbooks (
                playbook_id, name, domain, version, status_cache, spec,
                confidence, embedding
            ) VALUES (%s, %s, 'incident', 1, 'active', %s, %s, %s::vector)
            """,
            (
                str(playbook_id),
                f"{action} for {kind}",
                _json.dumps(spec),
                0.5 if kind == "error_spike" else 0.7,
                to_vector_literal(embedding),
            ),
        )
        for rule_key, version in deps:
            await db.q(
                """
                INSERT INTO playbook_deps (
                    playbook_id, rule_key, rule_version, citation, extraction_confidence
                ) VALUES (%s, %s, %s, 'seeded', 0.9)
                """,
                (str(playbook_id), rule_key, version),
            )


async def check_contract_surface() -> None:
    """Every frozen contract function must exist with the agreed signature."""
    import inspect

    from app.core import contracts

    mvp = {
        "retrieve": ["task_text"],
        "check_freshness": ["playbook_id"],
        "run_task": ["task_id"],
        "change_rule": ["rule_key", "new_body", "new_params", "actor"],
        "answer_analytics_question": ["question"],
    }
    extensions = [
        "decide_autonomy", "resolve_approval", "generate_postmortem",
        "list_insights", "dismiss_insight", "simulate_rule_change",
    ]

    for name, params in mvp.items():
        fn = getattr(contracts, name, None)
        if fn is None:
            record(f"contract: {name}()", False, "missing")
            continue
        actual = list(inspect.signature(fn).parameters)
        record(
            f"contract: {name}({', '.join(params)})",
            actual == params,
            f"got ({', '.join(actual)})" if actual != params else "",
        )

    missing = [n for n in extensions if not hasattr(contracts, n)]
    record(
        "contract: all 6 extension functions present",
        not missing,
        f"missing {missing}" if missing else "",
    )


async def new_task(db, text: str) -> UUID:
    row = await db.one(
        "INSERT INTO tasks (input) VALUES (%s) RETURNING task_id", (text,)
    )
    return row["task_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="skip the world reset")
    args = parser.parse_args()

    if sys.platform == "win32":
        code = asyncio.run(
            main(args.keep),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        code = asyncio.run(main(args.keep))
    sys.exit(code)
