"""Reaching a real system, without giving up the guarantee that made the demo safe.

Spec edge case #15 required the mock world to have zero external dependencies
*precisely so* a live call could never hang a demo. Connectors trade that
guarantee away, so the discipline that replaces it has to be here from the
first commit rather than added after the first incident:

  1. Idempotency is enforced locally. The executor resumes an approved task by
     replaying it, which is only safe because every side-effecting step is
     idempotent on `{task_id}:{step_index}`. A remote service is not trusted to
     honour an Idempotency-Key header, so the ledger in `connector_calls` is
     what actually stops the second page going out.

  2. A hard timeout and a circuit breaker. A tripped breaker escalates the run;
     it never blocks it. Edge case #15's intent survives even though its
     mechanism does not.

  3. dry_run is the default. A connection has to be deliberately made live.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from app.core.connectors.payloads import build

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0

# Consecutive failures before a connection stops being tried. Low on purpose:
# the cost of a tripped breaker is a missing notification, and the cost of not
# tripping is every subsequent run paying the timeout.
BREAKER_THRESHOLD = 3


class DeliveryResult(dict):
    """A plain dict, named so call sites read clearly."""

async def _ledger_lookup(connection_id: str, key: str, db) -> dict | None:
    rows = await db.q(
        """
        SELECT call_id, status_code, outcome, response
        FROM connector_calls
        WHERE connection_id = %s AND idempotency_key = %s
        LIMIT 1
        """,
        (connection_id, key),
    )
    return rows[0] if rows else None


async def _record(
    connection_id: str,
    key: str,
    request: dict,
    response: Any,
    status_code: int | None,
    duration_ms: int,
    outcome: str,
    task_id: Any,
    step_index: Any,
    db,
) -> None:
    try:
        await db.q(
            """
            INSERT INTO connector_calls (
                connection_id, task_id, step_index, idempotency_key,
                request, response, status_code, duration_ms, outcome
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (connection_id, idempotency_key) DO NOTHING
            """,
            (
                connection_id,
                str(task_id) if task_id else None,
                step_index,
                key,
                json.dumps(request, default=str)[:12000],
                json.dumps(response, default=str)[:4000] if response is not None else None,
                status_code,
                duration_ms,
                outcome,
            ),
        )
    except Exception as exc:
        log.warning("could not record connector call: %s", exc)


async def _mark_health(connection_id: str, ok: bool, error: str | None, db) -> None:
    try:
        if ok:
            await db.q(
                """
                UPDATE connections
                SET last_ok_at = now(), failures = 0, last_error = NULL
                WHERE connection_id = %s
                """,
                (connection_id,),
            )
        else:
            await db.q(
                """
                UPDATE connections
                SET failures = failures + 1, last_error = %s
                WHERE connection_id = %s
                """,
                ((error or "")[:400], connection_id),
            )
    except Exception as exc:
        log.warning("could not update connection health: %s", exc)


async def send(
    connection: dict[str, Any],
    message: str,
    context: dict[str, Any],
    idempotency_key: str,
    db,
    task_id: UUID | str | None = None,
    step_index: int | None = None,
) -> DeliveryResult:
    """Deliver one message through one connection.

    Never raises. A connector failing is an operational event, not a reason for
    a remediation that already succeeded to be reported as failed.
    """
    connection_id = str(connection["connection_id"])
    kind = connection.get("kind") or "webhook"
    mode = connection.get("mode") or "dry_run"

    payload = build(kind, message, context)

    # The replay guard, and the reason this table has a unique constraint. Checked
    # before anything leaves the process.
    prior = await _ledger_lookup(connection_id, idempotency_key, db)
    if prior is not None:
        log.info(
            "connector %s: suppressed a replay of %s", connection["name"], idempotency_key
        )
        return DeliveryResult(
            delivered=False,
            replayed=True,
            outcome="replayed",
            connection=connection["name"],
            kind=kind,
            note="Idempotent replay: this exact step already went out, so nothing was sent again.",
        )

    if int(connection.get("failures") or 0) >= BREAKER_THRESHOLD:
        return DeliveryResult(
            delivered=False,
            outcome="failed",
            connection=connection["name"],
            kind=kind,
            error="circuit_open",
            note=(
                f"This connection has failed {connection.get('failures')} times in a "
                "row and is not being called. Test it under Connections to close "
                "the breaker."
            ),
        )

    if mode != "live":
        await _record(
            connection_id, idempotency_key, payload, None, None, 0, "dry_run",
            task_id, step_index, db,
        )
        return DeliveryResult(
            delivered=False,
            outcome="dry_run",
            connection=connection["name"],
            kind=kind,
            request=payload,
            note="Dry run: the request was built and recorded, but not sent.",
        )

    started = time.perf_counter()
    status_code: int | None = None
    body: Any = None
    error: str | None = None

    try:
        import httpx

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                connection["endpoint"],
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    # Sent as well as recorded. Destinations that honour it get
                    # a second layer; the ledger is what we actually rely on.
                    "Idempotency-Key": idempotency_key,
                    "User-Agent": "Cascade/1.0",
                },
            )
        status_code = response.status_code
        body = (response.text or "")[:400]
        if status_code >= 400:
            error = f"HTTP {status_code}: {body}"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:400]

    duration_ms = int((time.perf_counter() - started) * 1000)
    ok = error is None

    await _record(
        connection_id, idempotency_key, payload, body, status_code, duration_ms,
        "sent" if ok else "failed", task_id, step_index, db,
    )
    await _mark_health(connection_id, ok, error, db)

    if ok:
        log.info(
            "connector %s: delivered in %dms (HTTP %s)",
            connection["name"], duration_ms, status_code,
        )
    else:
        log.warning("connector %s failed: %s", connection["name"], error)

    return DeliveryResult(
        delivered=ok,
        outcome="sent" if ok else "failed",
        connection=connection["name"],
        kind=kind,
        status_code=status_code,
        duration_ms=duration_ms,
        request=payload,
        error=error,
    )
