"""
CASCADE - Database Connection & Transaction Wrapper
Minimal implementation for Day 2

Provides:
- Connection pool management
- run_txn() with retry on serialization failures
- q() for simple queries
"""

import asyncio
import os
import random
from typing import Any, Callable, Optional

# Will use psycopg when available
# import psycopg
# from psycopg_pool import AsyncConnectionPool


class RetryExhausted(Exception):
    """Raised when max retries exceeded"""
    pass


class DB:
    """Database connection wrapper with retry logic"""
    
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self._pool = None
    
    async def connect(self):
        """Initialize connection pool"""
        # STUB: Will implement with psycopg
        # self._pool = AsyncConnectionPool(
        #     conninfo=self.dsn,
        #     min_size=2,
        #     max_size=10
        # )
        pass
    
    async def q(self, sql: str, params: tuple = ()) -> list[dict]:
        """
        Execute single-statement query (autocommit).
        
        Args:
            sql: SQL query
            params: Query parameters
        
        Returns:
            List of row dicts
        """
        # STUB for Day 2
        # When psycopg is available:
        # async with self._pool.connection() as conn:
        #     async with conn.cursor() as cur:
        #         await cur.execute(sql, params)
        #         if cur.description:
        #             columns = [desc[0] for desc in cur.description]
        #             return [dict(zip(columns, row)) for row in await cur.fetchall()]
        #         return []
        return []
    
    async def run_txn(
        self,
        fn: Callable,
        max_retries: int = 6
    ) -> Any:
        """
        Execute function in transaction with retry on serialization failure.
        
        Args:
            fn: Async function receiving cursor
            max_retries: Max retry attempts
        
        Returns:
            Function result
        
        Raises:
            RetryExhausted: If max retries exceeded
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # STUB: Will implement with real transactions
                # async with self._pool.connection() as conn:
                #     async with conn.transaction():
                #         async with conn.cursor() as cur:
                #             return await fn(cur)
                
                # For now, just call function
                return await fn(None)
            
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check for serialization failure (SQLSTATE 40001)
                if "40001" in error_str or "serialization" in error_str.lower():
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        sleep_time = random.uniform(0, 0.05 * (2 ** attempt))
                        await asyncio.sleep(sleep_time)
                        continue
                
                # Non-retryable error
                raise
        
        raise RetryExhausted(f"Transaction failed after {max_retries} retries: {last_error}")


# Global DB instance
_db: Optional[DB] = None


def get_db() -> DB:
    """Get or create global DB instance"""
    global _db
    if _db is None:
        _db = DB()
    return _db


async def init_db():
    """Initialize database connection pool"""
    db = get_db()
    await db.connect()
