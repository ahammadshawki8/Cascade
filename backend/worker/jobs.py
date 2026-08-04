"""Outbox job handlers (spec §7.2, D5).

OWNER: Shawki (Track B).

Four jobs, all driven by rows in `outbox`:

    compile         successful cold run  -> new playbook
    rule_changed    rule version bump    -> status_cache sweep, interrupts, relearn
    relearn         stale active playbook-> re-explore under new rules, compile v2
    recheck_suspect suspect playbook     -> re-derive freshness, settle status_cache

Jobs must be idempotent. The outbox claim is the primary guard, but SQS
delivers at-least-once and a Lambda can die between doing the work and marking
the row processed, so every job is written to tolerate a second run.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)


async def job_compile(payload: dict[str, Any], db) -> None:
    """Turn a successful explore trajectory into a reusable playbook."""
    from app.core.compiler import CompilationRejected, compile_playbook

    task_id = payload.get("task_id")
    episode_id = payload.get("episode_id")
    if not task_id or not episode_id:
        raise ValueError("compile payload needs task_id and episode_id")

    episode = await db.q(
        "SELECT outcome, mode FROM episodes WHERE episode_id = %s", (episode_id,)
    )
    if not episode:
        log.warning("compile: episode %s is gone, dropping", episode_id)
        return
    if episode[0]["outcome"] != "success":
        return  # only successes are worth learning from

    trajectory = payload.get("trajectory") or []
    task_text = payload.get("task_text") or ""
    if not task_text:
        rows = await db.q("SELECT input FROM tasks WHERE task_id = %s", (task_id,))
        task_text = rows[0]["input"] if rows else ""

    if not trajectory:
        trajectory = await _load_trajectory_from_s3(episode_id, db)
    if not trajectory:
        log.warning("compile: no trajectory available for episode %s", episode_id)
        return

    try:
        playbook_id = await compile_playbook(
            episode_id=UUID(episode_id),
            task_id=UUID(task_id),
            trajectory=trajectory,
            db=db,
            task_text=task_text,
        )
    except CompilationRejected as exc:
        # A trajectory that cannot produce a safe playbook is a dead end, not a
        # transient failure — record it and let the row be marked processed
        # rather than retrying forever.
        log.warning("compile rejected for episode %s: %s", episode_id, exc)
        await _audit(db, "compilation.rejected", {"episode_id": episode_id, "reason": str(exc)})
        return

    if playbook_id is None:
        return  # deduped into an existing playbook

    # Deliberately NOT stamping tasks.playbook_id here. That column means "the
    # playbook this task executed", and the cold run that produced the playbook
    # did not execute it. Writing it back conflated authorship with reuse and
    # made every successful cold run count as a retrieval miss in /api/metrics.
    await _notify_sse(
        "playbook.changed", {"playbook_id": str(playbook_id), "action": "created"}
    )


async def job_rule_changed(payload: dict[str, Any], db) -> None:
    """Fan the cascade out asynchronously, in bounded batches.

    The rule-change transaction itself stayed O(1) (D1). This is the part that
    can afford to be O(n): status_cache is only a UI hint, so it is updated
    100 rows at a time, well after the commit that made those playbooks stale.
    """
    rule_key = payload.get("rule_key")
    old_version = payload.get("old_version")
    new_version = payload.get("new_version")
    if not rule_key:
        raise ValueError("rule_changed payload needs rule_key")

    affected = await db.q(
        """
        SELECT DISTINCT playbook_id
        FROM playbook_deps
        WHERE rule_key = %s AND rule_version <= %s
        """,
        (rule_key, old_version),
    )
    if not affected:
        log.info("rule %s changed but no playbook depends on it", rule_key)
        return

    playbook_ids = [str(row["playbook_id"]) for row in affected]
    reason = f"{rule_key} changed v{old_version} -> v{new_version}"

    # Only demote things that were trusted; already-rejected playbooks stay put.
    for batch in _chunks(playbook_ids, 100):
        await db.q(
            """
            UPDATE playbooks
            SET status_cache = 'suspect', updated_at = now()
            WHERE playbook_id = ANY(%s)
              AND status_cache IN ('active', 'candidate')
            """,
            (batch,),
        )

    await db.q(
        """
        UPDATE tasks
        SET interrupt_flag = TRUE, interrupt_reason = %s
        WHERE status = 'running' AND playbook_id = ANY(%s)
        """,
        (reason, playbook_ids),
    )

    # Semantic triage (T2.1): a change that only *relaxes* a constraint cannot
    # break a runbook that already satisfied the tighter one. Clearing those
    # avoids quarantining — and re-learning — work that was never at risk.
    # Fails closed: only provably-unaffected playbooks are cleared.
    cleared: list[str] = []
    try:
        from app.core.triage import triage_rule_change

        verdicts = await triage_rule_change(
            rule_key, old_version, new_version, playbook_ids, db
        )
        cleared = verdicts["cleared"]
        if cleared:
            log.info(
                "triage cleared %d/%d playbooks as unaffected by %s",
                len(cleared),
                len(playbook_ids),
                rule_key,
            )
    except Exception as exc:
        log.warning("triage failed, leaving everything quarantined: %s", exc)

    still_suspect = [pid for pid in playbook_ids if pid not in set(cleared)]

    # Re-learn only what was proven — relearning every candidate would burn the
    # token budget on runbooks nobody trusted anyway.
    relearn_targets = (
        await db.q(
            """
            SELECT playbook_id
            FROM playbooks
            WHERE playbook_id = ANY(%s)
              AND status_cache = 'suspect'
              AND confidence >= 0.6
            """,
            (still_suspect,),
        )
        if still_suspect
        else []
    )
    for row in relearn_targets:
        await db.q(
            "INSERT INTO outbox (kind, payload) VALUES (%s, %s)",
            ("relearn", json.dumps({"playbook_id": str(row["playbook_id"])})),
        )

    await _notify_sse(
        "playbook.changed",
        {
            "action": "invalidated",
            "rule_key": rule_key,
            "playbook_ids": still_suspect,
            "cleared_by_triage": cleared,
            "relearn_queued": len(relearn_targets),
        },
    )
    log.info(
        "rule_changed: %d affected, %d cleared by triage, %d suspect, %d relearns",
        len(playbook_ids),
        len(cleared),
        len(still_suspect),
        len(relearn_targets),
    )


async def job_relearn(payload: dict[str, Any], db) -> None:
    """Re-derive a stale playbook under the current rules, as v2.

    Runs a real explore pass rather than patching the old spec: the point is to
    discover what the *new* policy permits, which may differ in shape and not
    just in parameters.
    """
    from app.core.executor import run_task

    playbook_id = payload.get("playbook_id")
    if not playbook_id:
        raise ValueError("relearn payload needs playbook_id")

    rows = await db.q(
        "SELECT name, domain, spec, status_cache FROM playbooks WHERE playbook_id = %s",
        (playbook_id,),
    )
    if not rows:
        return
    playbook = rows[0]

    already = await db.q(
        "SELECT playbook_id FROM playbooks WHERE supersedes = %s", (playbook_id,)
    )
    if already:
        log.info("relearn: %s already superseded, skipping", playbook_id)
        return

    task_text = await _synthesize_task(playbook["spec"], db)
    if task_text is None:
        # Nothing in the mock world exercises this playbook right now, so there
        # is no honest way to re-derive it. Leave it suspect — the freshness
        # gate already stops it executing — and try again on a later sweep.
        log.info("relearn: no representative incident for %s, deferring", playbook_id)
        return

    task_rows = await db.q(
        "INSERT INTO tasks (input, status) VALUES (%s, 'queued') RETURNING task_id",
        (task_text,),
    )
    task_id = task_rows[0]["task_id"]

    try:
        await run_task(task_id, db)
    except Exception as exc:
        log.warning("relearn explore run failed for %s: %s", playbook_id, exc)
        await _audit(db, "relearn.failed", {"playbook_id": playbook_id, "error": str(exc)})
        return

    # The explore run enqueued its own compile event; claim it here so the new
    # playbook is linked as v2 instead of landing as an unrelated v1.
    pending = await db.q(
        """
        SELECT event_id, payload
        FROM outbox
        WHERE kind = 'compile'
          AND processed_at IS NULL
          AND payload ->> 'task_id' = %s
        """,
        (str(task_id),),
    )
    if not pending:
        log.info("relearn: explore run produced nothing to compile for %s", playbook_id)
        return

    from app.core.compiler import CompilationRejected, compile_playbook

    event = pending[0]
    compile_payload = event["payload"]
    await db.q(
        "UPDATE outbox SET processed_at = now(), claimed_by = 'relearn' WHERE event_id = %s",
        (str(event["event_id"]),),
    )

    try:
        new_id = await compile_playbook(
            episode_id=UUID(compile_payload["episode_id"]),
            task_id=UUID(compile_payload["task_id"]),
            trajectory=compile_payload.get("trajectory") or [],
            db=db,
            task_text=compile_payload.get("task_text", task_text),
            supersedes=UUID(playbook_id),
        )
    except CompilationRejected as exc:
        log.warning("relearn compile rejected for %s: %s", playbook_id, exc)
        await _audit(db, "relearn.rejected", {"playbook_id": playbook_id, "reason": str(exc)})
        return

    if new_id is None:
        return

    await db.q(
        """
        UPDATE playbooks SET status_cache = 'invalidated', updated_at = now()
        WHERE playbook_id = %s
        """,
        (playbook_id,),
    )
    await _notify_sse(
        "playbook.changed",
        {
            "playbook_id": str(new_id),
            "supersedes": playbook_id,
            "action": "relearned",
        },
    )
    log.info("relearn: %s superseded by %s", playbook_id, new_id)


async def job_recheck_suspect(payload: dict[str, Any], db) -> None:
    """Settle a suspect playbook's status_cache against the freshness join.

    status_cache drifts; this reconciles it. A suspect playbook whose deps all
    match head again (because the rule was reverted) becomes usable without
    needing to be relearned.
    """
    from app.core.freshness import bulk_check_freshness

    playbook_id = payload.get("playbook_id")
    if playbook_id:
        targets = [UUID(playbook_id)]
    else:
        rows = await db.q(
            "SELECT playbook_id FROM playbooks WHERE status_cache = 'suspect' LIMIT 200"
        )
        targets = [
            r["playbook_id"] if isinstance(r["playbook_id"], UUID) else UUID(str(r["playbook_id"]))
            for r in rows
        ]
    if not targets:
        return

    results = await bulk_check_freshness(targets, db)
    recovered = [str(pid) for pid, result in results.items() if result.kind == "fresh"]
    if recovered:
        await db.q(
            """
            UPDATE playbooks
            SET status_cache = CASE WHEN confidence >= 0.6 THEN 'active' ELSE 'candidate' END,
                updated_at = now()
            WHERE playbook_id = ANY(%s) AND status_cache = 'suspect'
            """,
            (recovered,),
        )
        await _notify_sse(
            "playbook.changed", {"action": "recovered", "playbook_ids": recovered}
        )
        log.info("recheck: %d playbooks returned to service", len(recovered))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


_KINDS = ("bad_deploy", "error_spike", "resource_exhaustion")


async def _synthesize_task(spec: Any, db) -> str | None:
    """Build a representative request that re-exercises this playbook.

    It has to name a real, open incident of the same class: the executor works
    from an incident id, and a task phrased only as a goal ("Resolve a
    bad_deploy incident...") escalates on the first step with nothing to
    compile. Returns None when the world has no matching open incident.
    """
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except json.JSONDecodeError:
            spec = {}
    spec = spec or {}

    haystack = " ".join(
        [str(spec.get("goal", "")), *[str(p) for p in spec.get("preconditions", [])]]
    ).lower()
    kind = next((k for k in _KINDS if k in haystack), None)

    if kind:
        rows = await db.q(
            """
            SELECT incident_id FROM mock_incidents
            WHERE state = 'open' AND kind = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (kind,),
        )
    else:
        rows = await db.q(
            """
            SELECT incident_id FROM mock_incidents
            WHERE state = 'open' ORDER BY created_at DESC LIMIT 1
            """
        )

    if not rows:
        return None
    return f"Remediate {rows[0]['incident_id']}"


async def _load_trajectory_from_s3(episode_id: str, db) -> list[dict[str, Any]]:
    from app.config import settings

    rows = await db.q(
        "SELECT s3_key FROM episodes WHERE episode_id = %s", (episode_id,)
    )
    key = rows[0]["s3_key"] if rows else None
    if not key or not settings.episodes_bucket:
        return []

    try:
        import asyncio

        import boto3

        client = boto3.client("s3", region_name=settings.aws_region)
        response = await asyncio.to_thread(
            client.get_object, Bucket=settings.episodes_bucket, Key=key
        )
        return json.loads(response["Body"].read())
    except Exception as exc:
        log.warning("could not load trajectory %s from S3: %s", key, exc)
        return []


async def _audit(db, kind: str, details: dict[str, Any]) -> None:
    await db.q(
        "INSERT INTO audit_log (kind, actor, details) VALUES (%s, 'worker', %s)",
        (kind, json.dumps(details, default=str)),
    )


async def _notify_sse(topic: str, data: dict[str, Any]) -> None:
    """Push an event to connected dashboards.

    In-process when the worker runs inside the API (local dev); over the
    /internal/sse bridge when it runs as a Lambda, which has no socket to the
    browser. Never fatal — the UI refetches on its own.
    """
    from app.config import settings

    if settings.run_worker_in_process:
        try:
            from app.bus import sse

            await sse.publish(topic, data)
            return
        except Exception as exc:
            log.warning("in-process sse publish failed: %s", exc)

    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.api_base_url}/internal/sse",
                json={"topic": topic, "data": data},
                headers={"x-internal-secret": settings.internal_sse_secret},
            )
    except Exception as exc:
        log.warning("sse bridge publish failed: %s", exc)


async def job_postmortem(payload: dict[str, Any], db) -> None:
    """Write a postmortem for an episode that did not cleanly remediate (T1.3)."""
    from app.core.postmortem import generate_postmortem

    episode_id = payload.get("episode_id")
    if not episode_id:
        raise ValueError("postmortem payload needs episode_id")

    try:
        key = await generate_postmortem(UUID(episode_id), db)
    except ValueError as exc:
        log.warning("postmortem skipped for %s: %s", episode_id, exc)
        return

    await _notify_sse(
        "postmortem.created", {"episode_id": episode_id, "s3_key": key}
    )


async def job_insight_scan(payload: dict[str, Any], db) -> None:
    """Mine history for policy suggestions (T1.2).

    Scheduled, not event-driven: these are trends, and a trend derived from a
    single incident is noise.
    """
    from app.core.insights import scan_for_insights

    found = await scan_for_insights(db)
    for insight in found:
        await _notify_sse(
            "insight.created",
            {
                "kind": insight["kind"],
                "summary": insight["summary"],
                "related_rule_key": insight.get("related_rule_key"),
                "suggested_params": insight.get("suggested_params"),
            },
        )


JOB_HANDLERS = {
    "compile": job_compile,
    "rule_changed": job_rule_changed,
    "relearn": job_relearn,
    "recheck_suspect": job_recheck_suspect,
    "postmortem": job_postmortem,
    "insight_scan": job_insight_scan,
}
