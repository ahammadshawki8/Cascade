# Query Plans - Vector Index Verification

**CRITICAL WEEK 1 GATE:** This document must prove that `pb_embed_idx` is used in Phase 1 ANN queries.

## Status
- [ ] Day 3 complete
- [ ] EXPLAIN output captured
- [ ] Index `pb_embed_idx` confirmed in plan
- [ ] MCP workflow screen-recorded

---

## Phase 1 ANN Query

**SQL:**
```sql
SELECT playbook_id, embedding <-> $1 AS dist 
FROM playbooks 
ORDER BY embedding <-> $1 
LIMIT 20;
```

**Expected Index Usage:** `pb_embed_idx` (ivfflat on `embedding` with `vector_l2_ops`)

---

## EXPLAIN Output

*Paste EXPLAIN (VERBOSE) output here from Claude Code + MCP Server*

```
-- Output goes here after Day 3
```

---

## Verification Steps

1. Connect Claude Code to CockroachDB via Managed MCP Server
2. Run query with EXPLAIN (VERBOSE)
3. **Screen record the MCP workflow** (needed for demo video)
4. Paste output above
5. Verify index appears in plan

---

## If Index Not Used

**STOP EVERYTHING.** This is a stop-the-world gate.

Possible issues:
1. Index not created (check migrations)
2. Wrong operator used (must be `<->` not `<=>` or `<#>`)
3. Vector index not enabled (check cluster setting)
4. Query planner choosing seq scan (force with hint?)

Fix before proceeding to any other work.
