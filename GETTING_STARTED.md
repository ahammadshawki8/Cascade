# Getting Started - Track B Development

**5-minute setup to start coding.**

---

## Prerequisites

✅ Python 3.12+  
✅ Docker Desktop  
✅ Git

---

## Quick Setup

```bash
cd Track_B

# Option 1: Automated
./setup.sh

# Option 2: Manual
make setup      # Install + config
make db-start   # Start database
make seed       # Apply schema
make test       # Verify
```

**Done!** Environment ready.

---

## Project Structure

```
core/              # Your main work (10 modules)
├── models.py      # Data types (FROZEN)
├── contracts.py   # Interface (FROZEN)
├── tools.py       # Day 1 ← Start here
├── llm.py         # Day 1
├── executor.py    # Day 2
├── retrieval.py   # Day 3 🚨 GATE
├── compiler.py    # Day 4
├── freshness.py   # Day 5
├── confidence.py  # Day 6 🚨 GATE
├── cascade.py     # Day 7
└── copilot.py     # Day 11

worker/            # Lambda jobs (Day 9-10)
migrations/        # Database schema
tests/             # Unit tests
```

---

## Daily Workflow

```bash
# Morning
make status        # Check env
make test          # Verify baseline

# During dev
code core/file.py  # Edit
pytest tests/ -v   # Test
make lint          # Check quality

# Useful commands
make dev           # Start server (port 8001)
make db-shell      # SQL shell
make help          # All commands
```

---

## Development Cycle

### Day 1 (Tomorrow): Tools + LLM
**Files:** `core/tools.py`, `core/llm.py`

Implement 5 mock tools and Bedrock clients.

### Day 3: Vector Retrieval 🚨 CRITICAL
**File:** `core/retrieval.py`

Phase 1 ANN query MUST use vector index.  
**Verify:** Document in `docs/query-plans.md`

### Day 6: Performance 🚨 CRITICAL
**File:** `core/confidence.py`

Guided MUST be ≥3× faster than explore.

### Day 11: MVP Complete 🎯
Full learn→reuse→unlearn working.

---

## Key Concepts

### Stub Mode
- `CASCADE_STUB_MODE=true` (default) - Canned data
- `CASCADE_STUB_MODE=false` - Real implementations

Track A can build UI while you build engine. No coordination needed.

### Frozen Contracts
`models.py` and `contracts.py` are FROZEN after Day 0.  
Changing signatures = breaking change requiring coordination.

### Standalone Repository
Work independently. Manual integration in Week 4.  
See `reference/INTEGRATION_PLAN.md`

---

## Common Commands

```bash
make setup         # Initial setup
make status        # Check environment
make db-start      # Start database
make db-stop       # Stop database
make seed          # Apply migrations
make test          # Run tests
make dev           # Start server
make db-shell      # SQL shell
python verify.py   # Verify setup
```

---

## Testing

```bash
# All tests
make test

# Specific module
pytest tests/test_retrieval.py -v

# With coverage
make test-cov
```

---

## Documentation

- **Claude.md** - Main development guide (read daily)
- **README.md** - Quick overview
- **DAY0_CHECKLIST.md** - Setup tasks
- **reference/** - Integration & references

---

## Troubleshooting

**Database won't start:**
```bash
make db-reset && make db-start && make seed
```

**Import errors:**
```bash
make install
```

**Tests failing:**
```bash
grep CASCADE_STUB_MODE .env  # Should be 'true'
```

---

## Next Steps

1. ✅ Setup complete (you're here)
2. [ ] Read `Claude.md` (5 min)
3. [ ] Review `core/contracts.py` (5 min)
4. [ ] Review `core/models.py` (5 min)
5. [ ] Check `migrations/001_schema.sql` (5 min)
6. [ ] Tomorrow: Start `core/tools.py`

---

**Ready!** Start building with `code core/tools.py`

## Prerequisites

✅ You have:
- Python 3.12+
- Docker Desktop
- Git
- Code editor (VS Code recommended)

## Quick Start (5 minutes)

```bash
# 1. Navigate to Track B
cd Track_B

# 2. Complete setup
make setup

# 3. Start database
make db-start

# 4. Apply migrations
make seed

# 5. Run tests
make test

# 6. Start dev server
make dev
```

Visit http://localhost:8001 to see your dev server!

## What Just Happened?

1. **Setup** - Installed Python dependencies and created `.env`
2. **Database** - Started local CockroachDB in Docker
3. **Migrations** - Created all tables and seeded initial data
4. **Tests** - Verified stub contracts work
5. **Server** - Started FastAPI server for testing

## Project Structure

```
Track_B/
├── core/              # Your main work happens here
│   ├── models.py      # Data models (FROZEN Day 0)
│   ├── contracts.py   # API contracts (FROZEN Day 0)
│   ├── tools.py       # Mock world tools (Day 1)
│   ├── llm.py         # Bedrock clients (Day 1)
│   ├── executor.py    # Task execution (Day 2)
│   ├── retrieval.py   # Vector search (Day 3) 🚨
│   ├── compiler.py    # Playbook compiler (Day 4)
│   ├── freshness.py   # Staleness checks (Day 5)
│   ├── confidence.py  # Scoring (Day 6)
│   ├── cascade.py     # Rule changes (Day 7)
│   └── copilot.py     # Analytics (Day 11)
│
├── worker/            # Lambda background jobs
│   ├── handler.py     # Entry point (Day 9)
│   └── jobs.py        # Job implementations (Day 9-10)
│
├── migrations/        # Database schema
│   ├── 001_schema.sql # All tables
│   └── 002_seed.sql   # Initial data
│
├── tests/             # Unit tests
│   └── test_contracts.py
│
├── docs/              # Documentation
│   ├── query-plans.md      # Vector index proof (Day 3 GATE)
│   └── skills-review.md    # Agent Skills findings
│
└── dev_server.py      # Test server
```

## Development Workflow

### Day 0 (Today) - Foundation
- [x] Environment setup
- [ ] Review contracts
- [ ] Understand data models
- [ ] All tests passing

### Day 1 - Tools & LLM
**Files:** `core/tools.py`, `core/llm.py`

Implement 5 mock tools and Bedrock clients.

```bash
# Work on implementation
code core/tools.py core/llm.py

# Test as you go
pytest tests/ -k tools -v
pytest tests/ -k llm -v

# Check progress
make day1
```

### Day 2 - Executor Explore Loop
**File:** `core/executor.py`

Implement cold-run exploration mode.

### Day 3 - Vector Retrieval 🚨 CRITICAL GATE
**File:** `core/retrieval.py`

Implement Phase 1 ANN query. **Must verify index usage!**

```bash
# After implementation
make day3

# CRITICAL: Verify vector index
# Open docs/query-plans.md and follow verification steps
```

### Day 4+ - Continue building
Follow the sprint breakdown in `Claude.md`

## Development Commands

```bash
make help          # Show all commands
make status        # Check environment status
make db-start      # Start database
make db-stop       # Stop database
make db-reset      # Reset database (destroys data)
make seed          # Apply migrations
make test          # Run tests
make test-cov      # Tests with coverage
make lint          # Check code quality
make format        # Auto-format code
make dev           # Start dev server
make db-shell      # Open SQL shell
```

## Working with the Database

### SQL Shell
```bash
make db-shell

# Then run SQL:
CASCADE> SELECT * FROM rules;
CASCADE> SELECT * FROM mock_incidents;
CASCADE> \q  # quit
```

### Web UI
Open http://localhost:8080 in your browser to see:
- Schema browser
- Running queries
- Performance metrics

## Stub Mode

Your code runs in two modes:

**Stub Mode (CASCADE_STUB_MODE=true)** - Default
- All contracts return canned data
- No AWS calls needed
- Perfect for UI development

**Real Mode (CASCADE_STUB_MODE=false)**
- Calls your actual implementations
- Requires AWS credentials for Bedrock
- Use after implementing each module

Toggle in `.env`:
```bash
CASCADE_STUB_MODE=false  # Use real implementations
```

## Testing Your Work

### Unit Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_retrieval.py -v

# Run specific test
pytest tests/test_retrieval.py::test_phase1_ann -v

# With coverage
make test-cov
```

### Integration Testing via Dev Server
```bash
# Start server
make dev

# In another terminal, test endpoints:
curl http://localhost:8001/
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1001"}'
```

## Common Issues

### Database won't start
```bash
# Check if port is in use
netstat -ano | findstr :26257

# Reset and restart
make db-reset
make db-start
make seed
```

### Import errors
```bash
# Reinstall dependencies
make install

# Or with pip directly:
pip install -r requirements.txt
```

### Tests failing
```bash
# Check stub mode is enabled
grep CASCADE_STUB_MODE .env

# Should show: CASCADE_STUB_MODE=true
```

### AWS credentials needed
Not needed until you implement real Bedrock calls! Keep stub mode enabled initially.

## Critical Gates

### 🔴 Day 3 - Vector Index Gate
**STOP-THE-WORLD:** Phase 1 ANN query MUST use `pb_embed_idx`.

Verify in `docs/query-plans.md` before continuing.

### 🔴 Day 6 - Performance Gate
Guided run MUST be ≥3× faster than cold run.

If not, all feature work stops.

### 🟢 Day 11 - MVP Complete
Learn → Reuse → Unlearn flow working end-to-end.

## Integration with Track A

When ready to integrate:

```bash
# Copy your modules to main backend
cp -r core/* ../backend/app/core/
cp -r worker/* ../backend/worker/
cp migrations/* ../migrations/
```

Track A imports only `core/contracts.py` - they never see your implementation details!

## Getting Help

- **Technical questions:** Check `Claude.md` for detailed specs
- **Workflow questions:** Check `WORKFLOW.md` for merge process
- **Integration points:** Check contract definitions in `core/contracts.py`

## Next Steps

1. ✅ Complete Day 0 setup (you're here!)
2. Read through `core/contracts.py` to understand the interface
3. Read through `core/models.py` to understand data structures
4. Review `migrations/001_schema.sql` to understand database
5. Start Day 1 work on `core/tools.py`

## Daily Checklist

- [ ] `git pull` main branch
- [ ] Tests passing
- [ ] Code formatted (`make format`)
- [ ] No lint errors (`make lint`)
- [ ] Document any design decisions

---

🚀 **You're ready to start building!**

Begin with Day 1 (tools.py and llm.py) and work through the sprint systematically.
