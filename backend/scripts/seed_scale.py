"""Prove the cascade is O(1) by making n large.

The whole D1 claim is that changing a rule costs a fixed number of writes
however much has been learned. With a dozen runbooks in the demo world that is
indistinguishable from a fan-out UPDATE that happens to be fast because n is
small, so the claim reads as rhetoric.

This seeds a lot of runbooks against a lot of rules, changes one rule, and
reports the two numbers side by side: what the transaction wrote, and how much
it invalidated. Then it cleans up after itself.

    python scripts/seed_scale.py --runbooks 50000 --rules 2000

Everything it creates is prefixed `scale/`, and `--cleanup-only` removes it,
so this can be run against the demo cluster without leaving a mess in the
runbook library.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PREFIX = "scale/"
BATCH = 2_000


async def _connect():
    import psycopg

    from app.config import settings

    return await psycopg.AsyncConnection.connect(settings.database_url, autocommit=True)


async def cleanup(cur) -> None:
    await cur.execute(
        "DELETE FROM playbook_deps WHERE rule_key LIKE %s", (PREFIX + "%",)
    )
    await cur.execute("DELETE FROM playbooks WHERE name LIKE %s", (PREFIX + "%",))
    await cur.execute("DELETE FROM rules WHERE rule_key LIKE %s", (PREFIX + "%",))
    print("cleaned up every scale/ row")


async def seed(cur, n_rules: int, n_runbooks: int) -> None:
    print(f"seeding {n_rules:,} rules and {n_runbooks:,} runbooks…")

    rules = [(f"{PREFIX}rule_{i:05d}", 1) for i in range(n_rules)]
    for i in range(0, len(rules), BATCH):
        chunk = rules[i : i + BATCH]
        args: list = []
        for key, ver in chunk:
            args += [key, ver, "incident", f"synthetic rule {key}",
                     json.dumps({}), "scale"]
        values = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(chunk))
        await cur.execute(
            "INSERT INTO rules (rule_key, version, domain, body, params, "
            f"changed_by) VALUES {values}",
            args,
        )
    print(f"  {n_rules:,} rules")

    # Every runbook cites three rules, one of which is rule_00000 — the one the
    # cascade will later move. That makes the invalidated set large and exact.
    ids = [uuid.uuid4() for _ in range(n_runbooks)]
    for i in range(0, n_runbooks, BATCH):
        chunk = ids[i : i + BATCH]
        args = []
        for j, pid in enumerate(chunk):
            args += [
                str(pid),
                f"{PREFIX}runbook {i + j:06d}",
                "incidents",
                1,
                "active",
                json.dumps(
                    {"goal": "synthetic", "steps": [], "preconditions": [], "params": {}}
                ),
                0.5,
            ]
        values = ",".join(["(%s,%s,%s,%s,%s,%s,%s)"] * len(chunk))
        await cur.execute(
            "INSERT INTO playbooks (playbook_id, name, domain, version, "
            f"status_cache, spec, confidence) VALUES {values}",
            args,
        )

        args = []
        for j, pid in enumerate(chunk):
            # Three *distinct* rules per runbook: the primary key is
            # (playbook_id, rule_key, rule_version), so a repeat inside one
            # runbook aborts the batch.
            picks = [0]
            spread = 1
            while len(picks) < 3 and n_rules >= 3:
                cand = ((i + j) * 7 + spread * 13) % n_rules
                if cand not in picks:
                    picks.append(cand)
                spread += 1
            for k in picks:
                args += [str(pid), f"{PREFIX}rule_{k:05d}", 1, "synthetic", 1.0]
        values = ",".join(["(%s,%s,%s,%s,%s)"] * (len(chunk) * 3))
        await cur.execute(
            "INSERT INTO playbook_deps (playbook_id, rule_key, rule_version, "
            f"citation, extraction_confidence) VALUES {values}",
            args,
        )
        print(f"  {min(i + BATCH, n_runbooks):,} / {n_runbooks:,} runbooks", end="\r")
    print(f"\n  {n_runbooks:,} runbooks, {n_runbooks * 3:,} provenance edges")


async def measure(cur) -> None:
    target = f"{PREFIX}rule_00000"

    await cur.execute(
        "SELECT count(DISTINCT playbook_id)::INT FROM playbook_deps WHERE rule_key = %s",
        (target,),
    )
    depend = (await cur.fetchone())[0]

    # The freshness question, for one runbook, at this size.
    await cur.execute(
        "SELECT playbook_id FROM playbooks WHERE name LIKE %s LIMIT 1", (PREFIX + "%",)
    )
    one = (await cur.fetchone())[0]
    started = time.perf_counter()
    await cur.execute(
        """
        SELECT d.rule_key FROM playbook_deps d
        JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        WHERE d.playbook_id = %s AND d.rule_version != r.version
        """,
        (str(one),),
    )
    await cur.fetchall()
    freshness_ms = (time.perf_counter() - started) * 1000

    # The cascade itself: the same four writes the application performs.
    started = time.perf_counter()
    await cur.execute("BEGIN")
    await cur.execute(
        "UPDATE rules SET valid_to = now() WHERE rule_key = %s AND version = 1", (target,)
    )
    await cur.execute(
        "INSERT INTO rules (rule_key, version, domain, body, params, changed_by) "
        "VALUES (%s, 2, 'incident', 'synthetic, moved', '{}', 'scale')",
        (target,),
    )
    await cur.execute(
        "INSERT INTO outbox (kind, payload) VALUES ('rule_changed', %s)",
        (json.dumps({"rule_key": target, "old_version": 1, "new_version": 2}),),
    )
    await cur.execute(
        "INSERT INTO audit_log (kind, actor, details) VALUES ('rule.change', 'scale', %s)",
        (json.dumps({"rule_key": target, "from_version": 1, "to_version": 2, "writes": 4}),),
    )
    await cur.execute("COMMIT")
    cascade_ms = (time.perf_counter() - started) * 1000

    await cur.execute(
        """
        SELECT count(DISTINCT d.playbook_id)::INT
        FROM playbook_deps d
        JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        WHERE d.rule_key = %s AND d.rule_version != r.version
        """,
        (target,),
    )
    stale = (await cur.fetchone())[0]

    print()
    print("=" * 62)
    print(f"  runbooks depending on the changed rule   {depend:>10,}")
    print(f"  writes in the cascade transaction        {4:>10,}")
    print(f"  runbooks now stale                       {stale:>10,}")
    print(f"  cascade duration                         {cascade_ms:>9.0f} ms")
    print(f"  freshness check, one runbook             {freshness_ms:>9.1f} ms")
    print("=" * 62)
    print("  Not one of those runbook rows was written to. Staleness is the")
    print("  join disagreeing, computed fresh on every read.")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runbooks", type=int, default=50_000)
    ap.add_argument("--rules", type=int, default=2_000)
    ap.add_argument("--keep", action="store_true", help="leave the rows in place")
    ap.add_argument("--cleanup-only", action="store_true")
    args = ap.parse_args()

    async with await _connect() as conn:
        async with conn.cursor() as cur:
            await cleanup(cur)
            if args.cleanup_only:
                return
            await seed(cur, args.rules, args.runbooks)
            await measure(cur)
            if not args.keep:
                print()
                await cleanup(cur)


if __name__ == "__main__":
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
