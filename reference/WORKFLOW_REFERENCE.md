# Reference - Track A/B Workflow (Original)

**NOTE:** This is a reference copy. Since you're working in a standalone repository,
most of the merge workflow doesn't apply until integration time.

## Key Points for Track B:

### What You Own (Always)
- `Track_B/core/` - All engine modules
- `Track_B/worker/` - Lambda workers
- `Track_B/migrations/` - Database schema
- `Track_B/tests/` - Your tests
- `Track_B/docs/` - Your documentation

### Frozen Contracts (Day 0)
- `core/models.py` - Data structures
- `core/contracts.py` - Function signatures

If you need to change these, it's a breaking change requiring coordination with Ashfaq.

### Integration Timeline
- **Weeks 1-3:** Work completely independently
- **Week 4:** Plan integration
- **Week 5:** Integrate and test together

### When Integration Time Comes
You'll manually copy your working code to Ashfaq's repository:
```bash
# At integration time (Week 4+)
cp -r Track_B/core/* [ashfaq-repo]/backend/app/core/
cp -r Track_B/worker/* [ashfaq-repo]/backend/worker/
cp Track_B/migrations/* [ashfaq-repo]/migrations/
```

---

**Current Strategy:** Standalone development. No merge conflicts. Clean integration later.
