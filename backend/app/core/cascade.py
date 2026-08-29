"""Rule change cascade — the O(1) unlearn transaction (spec §7, D1 + D5).

OWNER: Shawki (Track B).

Changing a rule must not fan out. Marking every dependent playbook stale would
mean an unbounded write set and heavy contention on exactly the table the
retrieval path reads. Instead the transaction is a fixed four writes:

    1. close the current rule version   (valid_to = now())
    2. insert the new version
    3. insert ONE outbox row            (kind='rule_changed')
    4. insert ONE audit row

Staleness then *derives* from the version bump via the freshness join (D1), so
every dependent playbook is already stale the instant this commits — no rows
were touched to make that true.

Everything after the commit is best-effort UX: SQS publish, in-process
interrupt fan-out, SSE broadcast. If any of it fails the sweeper still picks
the outbox row up within 60s, so correctness never depends on it (D5).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from .models import ImpactedPlaybook, ImpactedTask, ImpactResult

log = logging.getLogger(__name__)

# Close the old version, insert the new one, one outbox row, one audit row.
# Named rather than hardcoded at the call sites, because the number *is* the
# claim: it does not grow with how many playbooks depend on the rule.
_WRITES_PER_CASCADE = 4

# "Leave this as it is." Distinct from None, which is a legitimate value for a
# predicate and means "this rule gates nothing".
KEEP: Any = object()


async def change_rule(
    rule_key: str,
    new_body: str,
    new_params: dict[str, Any],
    actor: str,
    db,
    interrupt_bus=None,
    sse_bus=None,
    sqs_client=None,
    new_predicate: Any = KEEP,
    new_enforcement: Any = KEEP,
) -> ImpactResult:
    """Version a rule forward and report what it invalidated.

    How a rule decides is versioned exactly like what it says. Changing a
    predicate is a policy change in the fullest sense — a procedure compiled
    while the old one was in force may now be acting on a rule that no longer
    means what it did — so it moves through this same transaction and
    invalidates the same dependents. Anything else would leave a class of policy
    change that silently kept stale procedures looking fresh.
    """

    async def txn(cur):
        await cur.execute(
            """
            SELECT version, domain, predicate, enforcement
            FROM rules
            WHERE rule_key = %s AND valid_to IS NULL
            """,
            (rule_key,),
        )
        current = await cur.fetchone()
        if current is None:
            raise ValueError(f"rule {rule_key!r} has no current version")

        old_version = current["version"]
        domain = current["domain"]
        new_version = old_version + 1
        event_id = uuid4()

        # Carried forward unless explicitly replaced. A caller that only knows
        # about body and params — every caller that predates migration 006 —
        # must not silently drop a rule's ability to decide anything.
        predicate = current.get("predicate") if new_predicate is KEEP else new_predicate
        enforcement = (
            (current.get("enforcement") or "advisory")
            if new_enforcement is KEEP
            else new_enforcement
        )

        await cur.execute(
            "UPDATE rules SET valid_to = now() WHERE rule_key = %s AND version = %s",
            (rule_key, old_version),
        )
        await cur.execute(
            """
            INSERT INTO rules (rule_key, version, domain, body, params, changed_by,
                               predicate, enforcement)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                rule_key,
                new_version,
                domain,
                new_body,
                json.dumps(new_params),
                actor,
                json.dumps(predicate) if predicate is not None else None,
                enforcement,
            ),
        )
        await cur.execute(
            "INSERT INTO outbox (event_id, kind, payload) VALUES (%s, %s, %s)",
            (
                str(event_id),
                "rule_changed",
                json.dumps(
                    {
                        "rule_key": rule_key,
                        "old_version": old_version,
                        "new_version": new_version,
                        "domain": domain,
                    }
                ),
            ),
        )
        await cur.execute(
            "INSERT INTO audit_log (kind, actor, details) VALUES (%s, %s, %s)",
            (
                "rule.change",
                actor,
                json.dumps(
                    {
                        "rule_key": rule_key,
                        "from_version": old_version,
                        "to_version": new_version,
                        "params": new_params,
                        # The bounded write set is the claim this whole design
                        # exists to make, and it was only ever visible by
                        # reading the source. Recorded here so the UI can
                        # report it as a fact rather than assert it.
                        "writes": _WRITES_PER_CASCADE,
                    }
                ),
            ),
        )
        return event_id, old_version, new_version, domain

    started = time.perf_counter()
    event_id, old_version, new_version, domain = await db.run_txn(txn)
    duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "rule %s: v%d -> v%d by %s in %dms",
        rule_key,
        old_version,
        new_version,
        actor,
        duration_ms,
    )

    impact = await analyze_impact(rule_key, db, committed=True)
    impact.old_version = old_version
    impact.new_version = new_version
    impact.writes = _WRITES_PER_CASCADE
    impact.duration_ms = duration_ms

    await _publish_sqs(event_id, sqs_client)
    await _interrupt_running_tasks(
        impact, rule_key, old_version, new_version, interrupt_bus
    )
    await _broadcast(impact, rule_key, new_version, sse_bus)

    return impact


async def analyze_impact(rule_key: str, db, committed: bool = False) -> ImpactResult:
    """Which playbooks and in-flight tasks does this rule govern?

    Deterministic SQL, no LLM (D6) — the operator confirming a policy change is
    entitled to an exact answer, not a plausible one.
    """
    result = ImpactResult(rule_key=rule_key, committed=committed)

    try:
        current = await db.q(
            "SELECT version FROM rules WHERE rule_key = %s AND valid_to IS NULL",
            (rule_key,),
        )
        if current:
            head = current[0]["version"]
            result.old_version = head if not committed else None
            result.new_version = head + 1 if not committed else None

        playbook_rows = await db.q(
            """
            SELECT DISTINCT p.playbook_id, p.name, p.version, p.confidence, p.status_cache
            FROM playbook_deps d
            JOIN playbooks p ON p.playbook_id = d.playbook_id
            WHERE d.rule_key = %s
              AND p.status_cache IN ('active', 'candidate', 'suspect')
            ORDER BY p.confidence DESC
            """,
            (rule_key,),
        )
        result.impacted_playbooks = [
            ImpactedPlaybook(
                playbook_id=_as_uuid(r["playbook_id"]),
                name=r["name"],
                version=r["version"],
                confidence=float(r["confidence"]),
                status_cache=r["status_cache"],
            )
            for r in playbook_rows
        ]

        if result.impacted_playbooks:
            task_rows = await db.q(
                """
                SELECT task_id, input,
                       (EXTRACT(EPOCH FROM (now() - created_at)) * 1000)::INT AS elapsed_ms
                FROM tasks
                WHERE status = 'running'
                  AND playbook_id = ANY(%s)
                """,
                ([str(p.playbook_id) for p in result.impacted_playbooks],),
            )
            result.impacted_tasks = [
                ImpactedTask(
                    task_id=_as_uuid(r["task_id"]),
                    input=r["input"],
                    elapsed_ms=int(r["elapsed_ms"] or 0),
                )
                for r in task_rows
            ]
    except Exception as exc:
        log.warning("impact analysis for %s failed: %s", rule_key, exc)

    return result


async def simulate_rule_change(
    rule_key: str, new_body: str, new_params: dict[str, Any], db
) -> ImpactResult:
    """Dry run for the Policy Panel's confirm dialog. Writes nothing."""
    return await analyze_impact(rule_key, db, committed=False)


# ---------------------------------------------------------------------------
# Post-commit side effects (all best-effort — the sweeper is the safety net)
# ---------------------------------------------------------------------------


async def _publish_sqs(event_id: UUID, sqs_client) -> None:
    from app.config import settings

    if not settings.cascade_queue_url:
        return  # local dev: the 60s sweeper claims the outbox row instead

    try:
        import asyncio

        if sqs_client is None:
            import boto3

            sqs_client = boto3.client("sqs", region_name=settings.aws_region)
        await asyncio.to_thread(
            sqs_client.send_message,
            QueueUrl=settings.cascade_queue_url,
            MessageBody=json.dumps({"event_id": str(event_id)}),
        )
    except Exception as exc:
        log.warning("post-commit SQS publish failed (sweeper will recover): %s", exc)


async def _interrupt_running_tasks(
    impact: ImpactResult,
    rule_key: str,
    old_version: int,
    new_version: int,
    interrupt_bus,
) -> None:
    """Microsecond in-process delivery (D4), then cross-instance (T3.7).

    The durable `tasks.interrupt_flag` set by the worker is the correctness
    guarantee; both of these just get there first, before the executor reaches
    its next side-effecting step.
    """
    if not impact.impacted_tasks:
        return

    task_ids = [str(t.task_id) for t in impact.impacted_tasks]
    reason = f"{rule_key} changed v{old_version} -> v{new_version}"

    if interrupt_bus is not None:
        interrupt_bus.interrupt_many(task_ids, reason)

    # Other instances have their own in-process bus and cannot see the call
    # above. Best-effort — a failure just means they fall back to the flag.
    from .fanout import publish_interrupt

    await publish_interrupt(task_ids, reason)


async def _broadcast(
    impact: ImpactResult, rule_key: str, new_version: int, sse_bus
) -> None:
    if sse_bus is None:
        return
    try:
        from app.bus import TOPIC_RULE_CHANGED

        await sse_bus.publish(
            TOPIC_RULE_CHANGED,
            {
                "rule_key": rule_key,
                "new_version": new_version,
                "impacted_playbooks": [
                    str(p.playbook_id) for p in impact.impacted_playbooks
                ],
                "impacted_count": len(impact.impacted_playbooks),
            },
        )
    except Exception as exc:
        log.warning("SSE broadcast failed: %s", exc)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
