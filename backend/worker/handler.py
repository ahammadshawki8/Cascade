"""Worker entry points (spec §7.2, D5).

Three ways in, one code path:

    lambda_handler     AWS Lambda — SQS batch or EventBridge sweeper
    drain_outbox       poll-and-dispatch, used by the sweeper and local dev
    run_local_worker   background loop the API starts when there is no SQS

Claiming is what makes at-least-once delivery safe:

    UPDATE outbox SET claimed_at = now(), claimed_by = $2
    WHERE event_id = $1 AND claimed_at IS NULL
    RETURNING event_id

An empty result means someone else got there first, so this invocation returns
without doing the work twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any
from uuid import uuid4

from .jobs import JOB_HANDLERS

log = logging.getLogger(__name__)

# How long a claimed-but-unfinished row waits before the sweeper retries it.
STUCK_CLAIM_SECONDS = 300
SWEEP_BATCH = 100


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point for both SQS batches and the 60s sweeper."""
    if "Records" in event:
        return asyncio.run(_run_sqs_batch(event))
    if event.get("source") == "aws.events" or event.get("sweeper"):
        return asyncio.run(_run_sweeper())
    return {"statusCode": 400, "body": json.dumps({"error": "unrecognised event"})}


async def _run_sqs_batch(event: dict[str, Any]) -> dict[str, Any]:
    db = await _connect()
    failures: list[dict[str, str]] = []
    try:
        for record in event.get("Records", []):
            message_id = record.get("messageId", str(uuid4()))
            try:
                body = json.loads(record.get("body", "{}"))
                event_id = body.get("event_id")
                if not event_id:
                    raise ValueError("message has no event_id")
                await process_event(event_id, db, worker_id=f"lambda-{message_id}")
            except Exception:
                # Reporting the failure returns just this message to the queue;
                # the rest of the batch still counts as handled.
                log.exception("sqs record %s failed", message_id)
                failures.append({"itemIdentifier": message_id})
        return {"statusCode": 200, "batchItemFailures": failures}
    finally:
        await _close(db)


async def _run_sweeper() -> dict[str, Any]:
    db = await _connect()
    try:
        processed = await drain_outbox(db, worker_id="sweeper")
        return {
            "statusCode": 200,
            "body": json.dumps({"processed": processed}),
        }
    finally:
        await _close(db)


# ---------------------------------------------------------------------------
# Shared dispatch
# ---------------------------------------------------------------------------


async def claim_outbox(event_id: str, worker_id: str, db) -> bool:
    """Atomically take ownership of an outbox row. False => already claimed."""
    rows = await db.q(
        """
        UPDATE outbox
        SET claimed_at = now(), claimed_by = %s
        WHERE event_id = %s AND claimed_at IS NULL AND processed_at IS NULL
        RETURNING event_id
        """,
        (worker_id, event_id),
    )
    return bool(rows)


async def process_event(event_id: str, db, worker_id: str) -> bool:
    """Claim, dispatch, mark processed. Returns False if nothing was done."""
    if not await claim_outbox(event_id, worker_id, db):
        return False

    rows = await db.q(
        "SELECT kind, payload FROM outbox WHERE event_id = %s", (event_id,)
    )
    if not rows:
        return False

    kind = rows[0]["kind"]
    payload = rows[0]["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)

    handler = JOB_HANDLERS.get(kind)
    if handler is None:
        # Unknown kinds are marked processed rather than retried forever — the
        # CHECK constraint means this can only happen across a version skew.
        log.error("no handler for outbox kind %r, dropping %s", kind, event_id)
        await db.q(
            "UPDATE outbox SET processed_at = now() WHERE event_id = %s", (event_id,)
        )
        return False

    try:
        await handler(payload, db)
    except Exception:
        # Release the claim so the next sweep can retry a transient failure.
        await db.q(
            "UPDATE outbox SET claimed_at = NULL, claimed_by = NULL WHERE event_id = %s",
            (event_id,),
        )
        raise

    await db.q(
        "UPDATE outbox SET processed_at = now() WHERE event_id = %s", (event_id,)
    )
    log.info("processed outbox %s (%s)", event_id, kind)
    return True


async def drain_outbox(db, worker_id: str = "sweeper", limit: int = SWEEP_BATCH) -> int:
    """Process every pending outbox row. Returns how many were handled.

    Picks up both never-claimed rows and rows whose claim went stale, which is
    what recovers work from a worker that died mid-job.
    """
    rows = await db.q(
        """
        SELECT event_id
        FROM outbox
        WHERE processed_at IS NULL
          AND (claimed_at IS NULL OR claimed_at < now() - (%s * INTERVAL '1 second'))
        ORDER BY created_at
        LIMIT %s
        """,
        (STUCK_CLAIM_SECONDS, limit),
    )
    if not rows:
        return 0

    processed = 0
    for row in rows:
        event_id = str(row["event_id"])
        await db.q(
            """
            UPDATE outbox SET claimed_at = NULL, claimed_by = NULL
            WHERE event_id = %s AND processed_at IS NULL
              AND claimed_at < now() - (%s * INTERVAL '1 second')
            """,
            (event_id, STUCK_CLAIM_SECONDS),
        )
        try:
            if await process_event(event_id, db, worker_id):
                processed += 1
        except Exception:
            log.exception("outbox %s failed; will retry on the next sweep", event_id)

    return processed


# ---------------------------------------------------------------------------
# Local in-process worker
# ---------------------------------------------------------------------------


async def run_local_worker(interval_seconds: float = 2.0) -> None:
    """Poll the outbox from inside the API process.

    Local dev has no SQS and no Lambda, so without this the learn loop stops at
    "event queued" and no playbook is ever compiled. Same dispatch path as
    production — only the trigger differs.
    """
    from app import db as db_module

    worker_id = f"local-{socket.gethostname()}-{os.getpid()}"
    log.info("local outbox worker started (every %.1fs)", interval_seconds)

    while True:
        try:
            await drain_outbox(db_module, worker_id=worker_id)
        except asyncio.CancelledError:
            log.info("local outbox worker stopped")
            raise
        except Exception:
            log.exception("local outbox worker iteration failed")
        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# Lambda-side connection management
# ---------------------------------------------------------------------------


async def _connect():
    """Open a pool for a Lambda invocation and return the db module."""
    from app import db as db_module

    await db_module.init_pool()
    return db_module


async def _close(db_module) -> None:
    try:
        await db_module.close_pool()
    except Exception as exc:
        log.warning("pool close failed: %s", exc)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import sys

    logging.basicConfig(level=logging.INFO)

    async def _once() -> None:
        db = await _connect()
        try:
            count = await drain_outbox(db, worker_id="cli")
            print(f"processed {count} outbox row(s)")
        finally:
            await _close(db)

    if sys.platform == "win32":
        import selectors

        asyncio.run(
            _once(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(_once())
