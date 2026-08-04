# Schema & Query Review

**Status:** Local review complete ✅ · CockroachDB Agent Skills run against the
Cloud cluster pending (blocked on cluster provisioning)

This documents what a schema and performance review of CASCADE actually turned
up. The findings below were reproduced against CockroachDB **v26.2.5** using
`EXPLAIN`, `SHOW INDEXES`, and the constraint definitions in
`backend/migrations/001_schema.sql` — every one of them was a live defect, not
a hypothetical.

The MCP workflow (Claude Code + CockroachDB Managed MCP Server) is how the
query plans were investigated; see decision D6 in the spec for why that is the
honest half of our MCP story.

---

## Findings — schema design

### S1. Vector index silently did not exist · **critical** · fixed

```sql
-- what the schema said
CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);
```

`USING ivfflat (... vector_l2_ops)` is pgvector syntax. CockroachDB rejects it
and ships C-SPANN vector indexes instead. The statement failed, the surrounding
migration partially applied, and `pb_embed_idx` did not exist — while the
schema file continued to assert it did, and nothing checked.

**Fix.** `CREATE VECTOR INDEX pb_embed_idx ON playbooks (embedding);`, moved
after `COMMIT` because it starts a backfill job and cannot run inside an
explicit transaction.

**Follow-through.** Because "the schema says so" turned out to be worth nothing,
index usage is now asserted at runtime by `GET /api/admin/verify-index` and by
`verify_integration.py`, not trusted.

### S2. `CHECK` constraint would have rejected every remediation · **critical** · fixed

`mock_incidents` declares `CHECK (state IN ('open','mitigated','resolved'))`,
but `apply_remediation` wrote `state = 'remediated'`. Every successful
remediation would have aborted at commit. Caught by running the flow, not by
reading it.

### S3. Nullable JSONB vs. non-null model default · minor · fixed

`tasks.scratchpad` is nullable, but the `Task` model declared
`dict = Field(default_factory=dict)`. `GET /api/tasks/{id}` returned 500 for
every task that had never been interrupted. Handled with a `mode="before"`
validator mapping `NULL → {}` rather than by loosening the public type.

### S4. Status vocabularies disagreed across layers · minor · fixed

The schema allows `candidate | active | suspect | invalidated | rejected`. The
playbooks router ordered by `'stale'` and `'archived'` — values that cannot
occur — so those `CASE` arms produced `NULL` and sorted unpredictably. The
frontend's union type was missing `rejected` entirely.

### S5. Foreign keys constrain delete order · minor · fixed

`POST /api/admin/reset` replayed `002_seed.sql` without clearing first, so it
collided on primary keys the second time it ran. Rewriting it also required
respecting FK order (`postmortems → episodes → tasks → playbooks`), otherwise
the whole batch aborts.

### S6. `playbook_deps` FK is load-bearing — keep it

```sql
FOREIGN KEY (rule_key, rule_version) REFERENCES rules(rule_key, version)
```

Worth calling out as a *good* constraint. Staleness is derived by joining
`playbook_deps` against head rules; a dep pointing at a non-existent rule
version would make a playbook permanently un-stale-able. `verify_integration.py`
asserts zero orphans after every compile.

---

## Findings — query performance

### P1. One scalar predicate cost the vector index · **critical** · fixed

The phase-1 retrieval query carried `WHERE embedding IS NOT NULL`. That alone
made the optimizer abandon `pb_embed_idx` and full-scan with a top-k sort:

```
• top-k → • filter (embedding IS NOT NULL) → • scan playbooks@playbooks_pkey  FULL SCAN
```

Removing it restores the index:

```
• top-k → • lookup join playbooks@playbooks_pkey → • vector search playbooks@pb_embed_idx
```

This is precisely the planner risk decision D3 exists to prevent, and it shows
that D3 has to be read strictly: *no* predicate belongs in the ANN statement,
not merely "no interesting predicate". Full plans in `docs/query-plans.md`.

### P2. `dedup_check()` had the same defect · fixed

It filtered on `domain` and `status_cache` alongside the vector `ORDER BY`.
Restructured into the same pure-ANN-then-filter shape.

### P3. Read-modify-write on confidence was a lost-update race · fixed

`update_confidence()` read `confidence`/`uses`/`successes`, computed, then
wrote — across two autocommit statements. Two concurrent guided runs on the
same playbook would silently drop an increment. Moved inside `run_txn`, so
CockroachDB's `SERIALIZABLE` isolation converts the race into a 40001 retry.

### P4. Transactions that weren't · **critical** · fixed

`cascade.py` and `compiler.py` opened `run_txn(...)` and then issued their
writes through `db.q()` — which runs autocommit on a *different* pooled
connection. The "O(1) atomic cascade" was four independent statements, and a
playbook could be committed without its provenance edges. Both rewritten to use
the transaction's cursor.

### P5. Unsupported interval syntax · minor · fixed

`make_interval(secs => $1)` is not accepted by CockroachDB. Replaced with
`now() - ($1 * INTERVAL '1 second')`.

### P6. Metric derived from the wrong signal · fixed

Retrieval hit-rate inferred misses from `tasks.playbook_id`, but the compile
job stamped that column onto the *cold run that authored* the playbook — so
every successful learn counted as a retrieval miss and hit-rate sat at 50% when
it should have been 100%. Retrieval outcomes are now recorded as explicit
`audit_log` events at the moment the decision is made, scoped to the current
world by a `world.reset` marker.

---

## Index inventory

| Index | Backs | Verified |
|-------|-------|----------|
| `pb_embed_idx` | phase-1 ANN retrieval | ✅ EXPLAIN |
| `playbooks_pkey` | phase-2 PK lookup | ✅ EXPLAIN |
| `deps_playbook_idx` | freshness join by playbook | ✅ used |
| `deps_rule_idx` | impact query by rule | ✅ used |
| `rules_current_idx` | head lookup (`valid_to IS NULL`) | ✅ used |
| `tasks_running_idx` | interrupt sweep | partial index on `status='running'` |
| `outbox_unprocessed_idx` | worker claim scan | partial, matches the claim predicate |
| `playbooks_active_idx` | active-by-confidence listing | present |
| `playbooks_lineage_idx` | v1→v2 lineage | present |

Partial indexes on `tasks_running_idx` and `outbox_unprocessed_idx` are the
right call — both are scanned constantly but match a small, shrinking subset.

---

## Recommendations not yet actioned

| # | Recommendation | Why it was deferred |
|---|----------------|---------------------|
| R1 | Add `episodes(mode, outcome, created_at)` covering index | `/api/metrics` aggregates the whole table; fine at demo scale, wanted before real volume |
| R2 | Retention/TTL on `audit_log` and `episodes` | Both are append-only and unbounded |
| R3 | Range-partition `episodes` by `created_at` | Only matters once the table is large |
| R4 | Tune `RETRIEVAL_L2_THRESHOLD` against Titan | Currently 0.85 from the spec; the local fallback embedder has different geometry, so this must be re-tuned once Bedrock is live |
| R5 | Multi-region survival goals | Single-region for the hackathon |

---

## Pending: Agent Skills against CockroachDB Cloud

Blocked on cluster provisioning. Once `01_ccloud_provision.sh` and
`02_migrate.sh` have run:

1. Re-run the schema design and performance skills against the Cloud cluster
2. Confirm the plan still shows `vector search · playbooks@pb_embed_idx`
   (`distribution: full` rather than `local` on a multi-node cluster)
3. Append findings and any diff from the local review here

---

*Last updated: August 4, 2026*
