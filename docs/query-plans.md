# Query Plans - Vector Index Verification

## Day 3 Gate: Vector Index Usage

**Date:** TBD  
**Status:** Pending CRDB Cloud setup

### Critical Query (Phase 1 ANN)

```sql
EXPLAIN
SELECT playbook_id, embedding <-> $1::vector AS dist
FROM playbooks
ORDER BY embedding <-> $1::vector
LIMIT 20;
```

### Expected Plan

The plan **MUST** show `pb_embed_idx` index usage. Example:

```
Index Scan using pb_embed_idx on playbooks
  Order By: (embedding <-> $1::vector)
  Limit: 20
```

### Verification Method

Via Claude Code + Managed MCP Server:
1. Connect to CASCADE cluster via MCP config snippet
2. Run EXPLAIN query
3. Screen-record for video
4. Paste output below

### EXPLAIN Output

```
[Output will be pasted here after CRDB Cloud setup]
```

### Verification Code

```python
from core.retrieval import verify_vector_index

result = await verify_vector_index(db)
print(f"Uses index: {result['uses_index']}")
print(f"Plan:\n{result['plan']}")
```

### Notes

- Operator MUST be `<->` (L2 distance)
- NEVER use `<=>` or `<#>` (disables index)
- Titan V2 with normalize=true makes L2 ≡ cosine ranking
- If index not used: Check operator, check CRDB version, verify index exists

### Gate Status

- [ ] CRDB Cloud cluster created
- [ ] Vector index `pb_embed_idx` created
- [ ] EXPLAIN shows index usage
- [ ] Screen recording captured
- [ ] Output pasted above

**⚠️ CRITICAL:** If index NOT found in plan, ALL feature work STOPS until fixed.
