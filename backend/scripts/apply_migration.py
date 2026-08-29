"""Apply a migration file to whatever DATABASE_URL points at.

    python scripts/apply_migration.py 006_platform.sql

Reads the DSN through `app.config`, so the credential stays in `.env` and never
reaches a shell history or a terminal. Windows needs the selector loop for the
same reason `run_local.py` does.

Statements are executed one at a time, with any BEGIN/COMMIT stripped.
CockroachDB refuses to run DML against a table in the same transaction as a
schema change on that table, so a migration that adds a column and then
backfills it deadlocks against itself if it is sent as one batch. Splitting is
not a convenience here, it is the only way such a migration can run at all.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def split_statements(sql: str) -> list[str]:
    """Split on semicolons that are not inside a string literal or a comment."""
    out: list[str] = []
    buf: list[str] = []
    in_string = False
    in_line_comment = False
    i = 0

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            buf.append(ch)
        elif in_string:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":       # escaped quote inside the literal
                    buf.append(nxt)
                    i += 1
                else:
                    in_string = False
        elif ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append(ch)
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == ";":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1

    if "".join(buf).strip():
        out.append("".join(buf))

    cleaned = []
    for stmt in out:
        # Drop comment-only fragments and the file's own transaction control.
        body = "\n".join(
            line for line in stmt.splitlines() if not line.strip().startswith("--")
        ).strip()
        if not body or body.upper() in {"BEGIN", "COMMIT", "START TRANSACTION"}:
            continue
        cleaned.append(stmt.strip())
    return cleaned


async def main(names: list[str]) -> None:
    import psycopg

    from app.config import settings

    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True, connect_timeout=20
    ) as conn:
        for name in names:
            path = MIGRATIONS / name
            if not path.exists():
                print(f"!! {name} not found in {MIGRATIONS}")
                sys.exit(1)

            statements = split_statements(path.read_text(encoding="utf-8"))
            print(f"{name}: {len(statements)} statement(s)")
            for n, stmt in enumerate(statements, 1):
                head = " ".join(
                    line
                    for line in stmt.splitlines()
                    if line.strip() and not line.strip().startswith("--")
                )[:72]
                try:
                    async with conn.cursor() as cur:
                        await cur.execute(stmt)
                    print(f"  [{n:>2}/{len(statements)}] ok   {head}")
                except Exception as exc:
                    # Re-runnability matters more than strictness: a migration
                    # half-applied by an earlier attempt must be finishable.
                    message = str(exc).lower()
                    benign = (
                        "already exists" in message
                        or "duplicate" in message
                        or "column already" in message
                    )
                    marker = "skip" if benign else "FAIL"
                    print(f"  [{n:>2}/{len(statements)}] {marker} {head}")
                    if not benign:
                        print(f"        {exc}")
                        sys.exit(1)
            print(f"applied {name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(args))
