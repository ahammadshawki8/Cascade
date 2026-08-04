"""Database access — the ONLY way to write (spec §5.1).

OWNER: Ashfaq (Track A). PUBLIC SURFACE FROZEN AFTER DAY 0.

⚠️ Track B imports run_txn() and q() from here. This is the reverse direction
of the contract (WORKFLOW.md §1) — changing either signature breaks every file
Shawki owns. Signature changes require a contract PR.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T")

# CockroachDB serialization failure. Retrying these is normal and expected
# under SERIALIZABLE isolation — it is not an error condition.
SERIALIZATION_FAILURE = "40001"


class RetryExhausted(RuntimeError):
    """run_txn() exceeded max_retries on 40001 conflicts."""


_pool: AsyncConnectionPool | None = None


async def init_pool() -> AsyncConnectionPool:
    """Called from the FastAPI lifespan handler on startup."""
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        await _pool.open(wait=True, timeout=30)
        log.info("db pool opened")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("db pool closed")


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("db pool not initialised — call init_pool() first")
    return _pool


async def q(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Single-statement read (autocommit). Never use this for writes."""
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            if cur.description is None:
                return []
            return await cur.fetchall()


async def one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = await q(sql, params)
    return rows[0] if rows else None


async def run_txn(
    fn: Callable[[psycopg.AsyncCursor], Awaitable[T]],
    *,
    max_retries: int = 6,
) -> T:
    """Run fn inside a SERIALIZABLE transaction, retrying on 40001.

    EVERY multi-statement write in this codebase goes through here. No
    exceptions. Backoff is exponential with full jitter, per spec §5.1.

        async def txn(cur):
            await cur.execute("UPDATE ...")
            return something
        result = await run_txn(txn)
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            async with pool().connection() as conn:
                await conn.set_autocommit(False)
                try:
                    async with conn.cursor() as cur:
                        result = await fn(cur)
                    await conn.commit()
                    return result
                except BaseException:
                    await conn.rollback()
                    raise
                finally:
                    await conn.set_autocommit(True)
        except psycopg.errors.SerializationFailure as exc:
            last_exc = exc
            delay = random.uniform(0, 0.05 * (2**attempt))
            log.warning(
                "40001 serialization conflict, retry %d/%d in %.3fs",
                attempt + 1,
                max_retries,
                delay,
            )
            await asyncio.sleep(delay)
        except psycopg.OperationalError as exc:
            # Some drivers surface 40001 as a generic OperationalError.
            if getattr(exc, "sqlstate", None) != SERIALIZATION_FAILURE:
                raise
            last_exc = exc
            await asyncio.sleep(random.uniform(0, 0.05 * (2**attempt)))

    raise RetryExhausted(
        f"transaction failed after {max_retries} serialization retries"
    ) from last_exc
