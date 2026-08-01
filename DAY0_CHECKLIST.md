# Day 0 Checklist - Track B Setup

**Date:** August 1, 2026  
**Owner:** Shawki  
**Goal:** Complete foundation setup before Day 1 development

---

## Prerequisites ✓

- [x] Repository cloned
- [x] Python 3.12+ installed
- [x] Docker installed and running
- [x] Track_B folder structure created
- [x] All stub files in place

---

## Environment Setup

- [ ] Virtual environment created (`python -m venv venv`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created from template
- [ ] Environment variables configured

**Quick setup:** Run `./setup.sh` or `bash setup.sh`

---

## Database Setup

- [ ] CockroachDB container running (port 26257)
- [ ] Database `cascade` created
- [ ] Schema applied (`001_schema.sql`)
- [ ] Seed data loaded (`002_seed.sql`)
- [ ] Web UI accessible at http://localhost:8080

**Quick setup:** `make db-start && make seed`

---

## Code Review

- [ ] Read `core/models.py` - understand data structures
- [ ] Read `core/contracts.py` - understand interface
- [ ] Read `migrations/001_schema.sql` - understand schema
- [ ] Review `Claude.md` - understand sprint plan
- [ ] Review `WORKFLOW.md` - understand merge process

---

## Testing

- [ ] All tests passing (`make test`)
- [ ] Stub mode working (contracts return canned data)
- [ ] Dev server starts (`make dev`)
- [ ] Health endpoint works: http://localhost:8001
- [ ] Database health check passes

---

## Documentation

- [ ] Read GETTING_STARTED.md
- [ ] Review README.md structure
- [ ] Understand Track A integration points
- [ ] Know where each module will go

---

## Development Tools

- [ ] Code editor configured (VS Code recommended)
- [ ] Python extensions installed
- [ ] Git configured
- [ ] Docker Desktop accessible
- [ ] Terminal/shell working

---

## Coordination with Track A (Ashfaq)

- [ ] Discussed Day 0 contract PR
- [ ] Agreed on `models.py` structure
- [ ] Agreed on `contracts.py` signatures
- [ ] Confirmed schema matches spec
- [ ] Scheduled joint contract PR merge

---

## Critical Understanding

### The Contract
- [x] Track A imports ONLY `core/contracts.py`
- [x] Signatures are FROZEN after Day 0
- [x] Stub mode lets Track A build UI before engine exists
- [x] No import swap ever needed

### The Gates
- [x] Day 3: Vector index MUST be used (stop-the-world)
- [x] Day 6: Guided ≥3× faster than explore (stop-the-world)
- [x] Day 11: MVP complete (learn→reuse→unlearn)

### The Workflow
- [x] Own directories: `core/`, `worker/`, `migrations/`, `docs/`
- [x] Fast lane: merge my files directly
- [x] Contract lane: shared files need approval
- [x] Never force-push to main

---

## Week 1 Preview

### Day 1 (Tomorrow): Tools + LLM
**Files:** `core/tools.py`, `core/llm.py`
- 5 mock world tools
- Bedrock client setup
- Budget tracking
- Retry logic

### Day 2: Executor Explore Loop
**Files:** `core/executor.py`
- Task execution framework
- Claude converse loop
- SSE streaming
- Episode writing

### Day 3: Vector Retrieval 🚨 CRITICAL
**Files:** `core/retrieval.py`, `docs/query-plans.md`
- Phase 1 ANN query
- EXPLAIN verification
- MCP workflow recording
- Vector index proof

---

## Pre-Flight Checks

Run these commands to verify everything:

```bash
# Environment status
make status

# Database connectivity
make db-shell
# Then type: SELECT * FROM rules;
# Should see 4 rules
# Type: \q to exit

# Python imports
python -c "from core import contracts, models; print('✓ Imports work')"

# Tests
make test

# Dev server
make dev
# Visit http://localhost:8001
# Should see {"service": "CASCADE Track B", "status": "ok"}
```

---

## Common Issues & Fixes

### Database won't start
```bash
make db-reset
make db-start
make seed
```

### Import errors
```bash
make install
```

### Port conflicts
```bash
# Check what's using port 26257
netstat -ano | findstr :26257
# Kill the process or use different port
```

---

## Success Criteria

Day 0 is complete when:

✅ All checkboxes above are ticked  
✅ `make test` passes  
✅ `make dev` starts successfully  
✅ Database has 4 rules and 4 mock incidents  
✅ You understand the contract model  
✅ You know what to build Day 1  

---

## Notes & Decisions

*Document any decisions or deviations here:*

- 
- 
- 

---

## Ready for Day 1?

If all checks pass above, you're ready to start building!

**Tomorrow (Day 1):** Start with `core/tools.py` - implement the 5 mock tools.

**Reference:** See `Claude.md` Day 1 section for detailed requirements.

---

**Date Completed:** _____________

**Signed Off:** _____________
