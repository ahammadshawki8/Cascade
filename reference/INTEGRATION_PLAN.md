# Integration Plan - Track B → Track A

**When:** Week 4 (after MVP gate on Day 11)

## Pre-Integration Checklist

- [ ] All Track B tests passing
- [ ] MVP gate completed (learn→reuse→unlearn working)
- [ ] Performance gate met (3× speedup proven)
- [ ] Vector index verified (docs/query-plans.md)
- [ ] No changes to frozen contracts (models.py, contracts.py)

## Integration Steps

### 1. Prepare Ashfaq's Repository
```bash
cd [ashfaq-repo]
git checkout -b integration/track-b
git pull origin main
```

### 2. Copy Track B Code
```bash
# Core modules
cp -r [track-b-repo]/core/* backend/app/core/

# Worker modules
cp -r [track-b-repo]/worker/* backend/worker/

# Migrations (verify no conflicts)
cp [track-b-repo]/migrations/* migrations/

# Tests
cp -r [track-b-repo]/tests/* backend/app/tests/
```

### 3. Verify Integration
```bash
# In Ashfaq's repo
cd backend
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Check imports work
python -c "from app.core import contracts, executor; print('OK')"
```

### 4. Test End-to-End
```bash
# Start full stack
docker compose --profile api up

# Test endpoints
curl http://localhost:8000/api/tasks

# Verify SSE streaming works
# Verify database queries work
```

### 5. Coordinate with Ashfaq
- Compare `models.py` - should be identical (frozen)
- Compare `contracts.py` - should be identical (frozen)
- Resolve any environment variable differences
- Test UI → API → Engine → Worker flow

## Known Integration Points

### Database
- Same schema (migrations should match)
- Same connection string format
- Both use psycopg3

### Environment Variables
Merge `.env` files - Track A may have additional vars:
- API tokens
- Frontend URLs
- CloudFront distribution
- S3 bucket names

### Dependencies
Merge `requirements.txt` / `pyproject.toml`:
- Track A has FastAPI, uvicorn
- Track B has same + anthropic, boto3
- Should be mostly compatible

## Rollback Plan

If integration fails:
1. Ashfaq's code still works (we only added, didn't modify)
2. Set `CASCADE_STUB_MODE=true` to use stubs
3. Debug in isolation
4. Fix in Track B repo
5. Re-attempt integration

## Post-Integration

- [ ] All tests passing in combined repo
- [ ] Disable stub mode: `CASCADE_STUB_MODE=false`
- [ ] Full smoke test: cold run → compile → warm run
- [ ] Rule change cascade test
- [ ] Verify metrics show 3× speedup
- [ ] Check video recording scenarios work

---

**Remember:** Track B is the brain. Track A is the shell. Clean separation means clean integration.
