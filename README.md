# CASCADE Track B - Standalone Development Repository

**Owner:** Shawki  
**Focus:** Core Memory & AI Engine  
**Repository Strategy:** Standalone until Week 4 integration

---

## Quick Start

```bash
# 1. Setup
make setup        # Install dependencies + create .env

# 2. Database
make db-start     # Start CockroachDB
make seed         # Apply schema + seed data

# 3. Verify
make test         # Run tests (should pass)
python verify.py  # Check environment

# 4. Develop
make dev          # Start dev server (port 8001)
```

---

## Structure

```
Track_B/
├── core/              # Engine modules (your main work)
│   ├── models.py      # Data models (FROZEN Day 0)
│   ├── contracts.py   # API contracts (FROZEN Day 0)
│   ├── tools.py       # Day 1: Mock tools
│   ├── llm.py         # Day 1: Bedrock clients
│   ├── executor.py    # Day 2: Execution
│   ├── retrieval.py   # Day 3: Vector search 🚨
│   ├── compiler.py    # Day 4: Compiler
│   ├── freshness.py   # Day 5: Staleness
│   ├── confidence.py  # Day 6: Scoring 🚨
│   ├── cascade.py     # Day 7: Rule changes
│   └── copilot.py     # Day 11: Analytics
│
├── worker/            # Lambda background jobs
├── migrations/        # Database schema
├── tests/             # Unit tests
├── docs/              # Documentation
├── reference/         # Static reference docs
│
├── dev_server.py      # Local test server
├── verify.py          # Environment checker
├── Makefile           # Commands
└── Claude.md          # Main development guide
```

---

## Essential Documentation

1. **Claude.md** - Complete technical spec (read daily)
2. **GETTING_STARTED.md** - Development workflow
3. **DAY0_CHECKLIST.md** - Today's setup tasks
4. **reference/** - Integration plan & references

---

## Development Commands

```bash
make help         # Show all commands
make status       # Check environment
make test         # Run tests
make dev          # Start server
make db-shell     # SQL shell
```

---

## Integration with Track A

**When:** Week 4 (after MVP complete)  
**How:** Manual copy to Ashfaq's repository  
**Details:** See `reference/INTEGRATION_PLAN.md`

---

## Repository Strategy

This is a **standalone repository**:
- ✅ Work independently (no merge conflicts)
- ✅ Full environment in Track_B/
- ✅ Manual integration when ready
- ✅ Clean separation until Week 4

---

## Critical Gates

- 🚨 Day 3: Vector index MUST be used
- 🚨 Day 6: Guided ≥3× faster than explore
- 🎯 Day 11: MVP complete (learn→reuse→unlearn)

---

**Next:** Read `GETTING_STARTED.md` then start with `make setup`
