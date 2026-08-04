# CASCADE - Agentic Incident Response with Persistent Memory

**Project:** CockroachDB × AWS Hackathon Submission  
**Team:** Ashfaq (Track A - Shell) + Shawki (Track B - Core Engine)  
**Status:** Integrated and verified end-to-end against a live CockroachDB — 34/34 integration assertions passing  
**Last Updated:** August 4, 2026

---

## 🎯 What is CASCADE?

CASCADE is an **agentic on-call SRE assistant** that learns, reuses, and unlearns incident response playbooks using CockroachDB as its persistent memory layer.

### The Core Concept: Learn → Reuse → Unlearn

1. **LEARN** (Cold Run)
   - Novel incident → Claude explores with tools
   - Successful trajectory → Compiled playbook
   - Stored with vector embedding in CockroachDB

2. **REUSE** (Guided Run)
   - Retrieve similar playbook via vector search
   - Execute directly (no LLM per-step)
   - **3-5× faster** than cold run

3. **UNLEARN** (Cascade)
   - Policy rule changes → **O(1) transaction**
   - Staleness derived via provenance join
   - Running tasks interrupted gracefully
   - Stale playbooks relearned automatically

---

## 🏗️ Architecture

```
┌─────────────────┐
│   Next.js UI    │ ← SSE streaming, real-time updates
└────────┬────────┘
         │
┌────────▼────────┐
│  FastAPI (ECS)  │ ← 7 routers + InterruptBus
└────────┬────────┘
         │
┌────────▼────────────────────────────────┐
│         Core Engine (Track B)           │
│  ┌──────────┬──────────┬──────────┐    │
│  │ Executor │ Compiler │ Cascade  │    │
│  │ Retrieval│ Freshness│ Confidence│    │
│  └──────────┴──────────┴──────────┘    │
└────────┬────────────────────────────────┘
         │
┌────────▼────────────────────────────────┐
│      CockroachDB (Distributed)          │
│  • Playbooks with vector embeddings     │
│  • Provenance graph (playbook_deps)     │
│  • Temporal rules (valid_from/valid_to) │
│  • Transactional outbox                 │
└─────────────────────────────────────────┘
         │
┌────────▼────────┐
│ Lambda Worker   │ ← SQS + EventBridge sweeper
│ (Compile, Learn)│
└─────────────────┘
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Docker Desktop (for CockroachDB)
- Python 3.12+
- Node.js 20+
- npm or yarn

### 1. Start CockroachDB
```bash
docker run -d \
  --name cascade-crdb \
  -p 26257:26257 \
  -p 8080:8080 \
  cockroachdb/cockroach:latest \
  start-single-node --insecure
```

### 2. Run Database Migrations
```bash
docker cp backend/migrations/001_schema.sql cascade-crdb:/tmp/
docker cp backend/migrations/002_seed.sql   cascade-crdb:/tmp/
docker exec cascade-crdb ./cockroach sql --insecure \
  -e "DROP DATABASE IF EXISTS cascade CASCADE; CREATE DATABASE cascade;"
docker exec cascade-crdb ./cockroach sql --insecure --database=cascade --file=/tmp/001_schema.sql
docker exec cascade-crdb ./cockroach sql --insecure --database=cascade --file=/tmp/002_seed.sql
```

Expect 13 tables, 4 rules, 6 services, 12 incidents, and the `pb_embed_idx`
vector index. (`infra/02_migrate.sh` does the same against a remote cluster.)

### 3. Configure Environment
```bash
cp .env.example backend/.env
# Edit backend/.env:
#   DATABASE_URL=postgresql://root@localhost:26257/cascade?sslmode=disable
#   CASCADE_STUB_MODE=false      # flipping this to false IS the integration test
#   RUN_WORKER_IN_PROCESS=true   # local dev has no SQS/Lambda to drain the outbox
```

### 4. Start Backend
```bash
cd backend
pip install -e .
python run_local.py
```

Backend runs at: http://127.0.0.1:8000

> **Why `run_local.py` and not bare `uvicorn`?** psycopg's async mode cannot
> drive the ProactorEventLoop that asyncio selects by default on Windows, and
> as of Python 3.14 `set_event_loop_policy` no longer influences the loop
> uvicorn builds for itself. The launcher constructs a selector loop explicitly.
> On Linux/macOS `uvicorn app.main:app` works directly, and that is what the
> Dockerfile runs.

### 5. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:3000

---

## 📁 Project Structure

```
cascade/
├── backend/                 # FastAPI + Core Engine
│   ├── app/
│   │   ├── main.py         # Entry point
│   │   ├── core/           # Track B engine (11 modules)
│   │   └── routers/        # Track A API (7 routers)
│   ├── worker/             # Lambda handlers
│   └── migrations/         # Database schema
├── frontend/               # Next.js UI
│   └── src/
│       ├── app/           # Main layout + SSE
│       └── components/    # 8 UI components
├── infra/                 # Deployment scripts
├── docs/                  # Documentation
└── ground_truth/          # Reference specs
```

---

## 🔧 Key Technologies

### CockroachDB Tools (3 used)
1. **Distributed Vector Indexing** - ANN playbook retrieval
2. **MCP Server** - Dev workflow via Claude Code
3. **ccloud CLI** - Cluster provisioning

### AWS Services
- **Bedrock** - Claude Sonnet (agent), Haiku (fast), Titan (embeddings)
- **Lambda** - Background workers
- **ECS Fargate** - API deployment
- **S3** - Episode storage
- **SQS** - Event queue
- **EventBridge** - Sweeper schedule

### Stack
- **Backend:** Python 3.12, FastAPI, psycopg3
- **Frontend:** Next.js 15, TypeScript, React 19
- **Database:** CockroachDB v26+ (vector index required)
- **AI:** Anthropic Claude on AWS Bedrock

---

## 📊 Demo Flow

### Step 1: Cold Run (Learn)
```bash
# Submit novel incident
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1001"}'

# Watch explore mode in UI console
# ~12s execution → playbook compiled
```

### Step 2: Warm Run (Reuse)
```bash
# Submit similar incident
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1002"}'

# Watch guided mode in UI console
# ~3s execution → 4× faster!
```

### Step 3: Policy Change (Unlearn)
```bash
# Preview the blast radius first — deterministic SQL, no LLM
curl -X POST http://127.0.0.1:8000/api/rules/incident.rollback_window/dry-run \
  -H "Content-Type: application/json" \
  -d '{"body": "Rollback allowed only within {hours} hours of deploy.", "params": {"hours": 4}}'

# Commit it (POST, and it needs the admin token)
curl -X POST http://127.0.0.1:8000/api/rules/incident.rollback_window \
  -H "Content-Type: application/json" \
  -H "x-admin-token: dev-admin-token" \
  -d '{"body": "Rollback allowed only within {hours} hours of deploy.", "params": {"hours": 4}}'

# Watch the cascade in the UI:
# • cascade transaction commits in ~16-26ms (4 writes, no fan-out)
# • runbook card flips to `suspect`, provenance dot goes red
# • running tasks interrupted before their next side-effect
# • relearn queued for playbooks at confidence ≥0.6 → v2 with supersedes
```

### Step 4: The point of the whole thing — the freshness gate
```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1009"}'
```

The playbook still *matches* by vector distance. It is **refused anyway**,
because the provenance join says it was compiled against `rollback_window` v1
and head is now v2. The task falls back to explore and correctly escalates —
INC-1009's deploy is 5 hours old, outside the new 4-hour window.

Stale knowledge is worse than no knowledge, because the agent would act on it
confidently. That refusal is the product.

---

## 🧠 Beyond the MVP

| Feature | What it does |
|---------|--------------|
| **Autonomy gating** | Irreversible actions on production-critical services stop and wait for a human. Risk is a static property of the tool — the model cannot argue past it. Approving *re-runs* the task; that's safe because every side-effecting tool is idempotent on `{task_id}:{step_index}`. |
| **Insight engine** | Mines history and proposes policy changes: *"the 4h rollback window is blocking 3 incidents; widening to 31h recovers all 3 and blocks nothing new."* Computed by replay, not extrapolation. |
| **Semantic triage** | Not every rule change breaks everything. Widening a window can't break a runbook that ran inside the old one. Provably-relaxing changes clear automatically; **uncertain always stays quarantined**. |
| **Counterfactual replay** | Before committing a policy change, re-decide every historical incident: which would newly be automated, which newly blocked. |
| **Time travel** | `AS OF SYSTEM TIME` — *"what did the agent believe when it made that call?"*, answered by CockroachDB's MVCC with no event-sourcing layer of our own. |
| **Negative memory** | Failed approaches become `anti_playbooks` and are injected into the planner prompt as warnings. Advisory only — policy still decides. |
| **Blast-radius graph** | `rules → runbooks → tasks`, with stale dependencies drawn red. |
| **Auto postmortems** | Any run that doesn't cleanly remediate gets a writeup grounded in the recorded trajectory. |
| **Savings ledger** | Tokens, dollars and engineer-hours avoided, measured from episodes. |

---

## 🎓 Key Innovations

### 1. O(1) Cascade Transaction (D1)
Traditional approach: Mass-update all dependent playbooks (N writes, contention)  
**CASCADE approach:** 4 writes total, zero fan-out
- Close old rule version
- Insert new rule version
- ONE outbox event
- ONE audit entry

Staleness detected at retrieval time via provenance join.

### 2. Two-Phase Retrieval (D2)
Never mix vector ORDER BY with scalar filters (planner risk).  
**Phase 1:** Pure ANN (20 candidates)  
**Phase 2:** PK lookup + metadata filter  
**Phase 3:** Freshness check

### 3. Interrupt Choreography (D4)
- **In-memory bus:** Microsecond latency for same-instance tasks
- **Durable flag:** Checked before side-effects
- **Scratchpad persist:** Resume with fresh rules

### 4. Confidence Lifecycle (D6)
- New playbook: `candidate` @ 0.30
- Success: +0.15 (max 0.99)
- Failure: ×0.6
- Promote: ≥3 successes + ≥0.60 → `active`
- Reject: <0.20 → terminal
- Idle decay: ×0.98 per 7 days

---

## 📈 Performance

Measured locally (CockroachDB v26.2.5, single-node Docker) via
`backend/verify_integration.py`:

| Metric | Target | Measured | |
|--------|--------|----------|---|
| Cascade transaction | <100ms | **16–26ms** | ✅ |
| Cold run (explore) | — | ~280ms | |
| Guided run | — | ~33–80ms | |
| Guided vs cold | ≥3× faster | **3.5–8.5×** | ⚠️ see below |
| Vector retrieval | <20ms | index-verified | ✅ |
| P95 task latency | <15s | well under | ✅ |

> ⚠️ **The speedup figure is not yet the real one.** These numbers were taken
> with Bedrock unavailable, so the explore path used the deterministic local
> planner and the delta reflects database round-trips only. With a live planner
> the cold path gains seconds of LLM latency and the gap widens — but the
> honest number is whatever gets measured then, not this one. `/api/metrics`
> reports `llm: "ok" | "degraded"` so you can always tell which regime a
> measurement came from.

---

## 🔒 Security & Safety

### SQL Injection Prevention
- All queries use parameterized statements
- No string interpolation

### Idempotency
- All side-effecting tools use idempotency keys
- Outbox claim with `UPDATE ... WHERE claimed_at IS NULL`

### Ops Copilot Safety
- Read-only SQL (SELECT/WITH only)
- Single statement validation
- 3s timeout + LIMIT 200 wrapper
- Executed as `cascade_readonly` role

### Budget Limits
- 15 steps per task
- 60s wall clock
- 25k tokens

---

## 📚 Documentation

### For Users
- `Claude.md` — integrated project memory, progress, and the roadmap beyond MVP
- `ground_truth/CASCADE_BUILD_SPEC.md` — complete specification

### For Judges
- `docs/query-plans.md` — vector index EXPLAIN verification, including the
  full-scan plan that a single stray predicate produced before it was fixed
- `docs/skills-review.md` — CockroachDB Agent Skills findings
- `DEVIATIONS.md` — 10 documented deviations with rationale and impact
- `backend/verify_integration.py` — the 34 assertions behind every claim above

### For Developers
- `ground_truth/DAY0_CONTRACT.md` - Frozen interface
- `ground_truth/ashfaq.md` - Track A implementation notes
- `ground_truth/Cascade_task_split.md` - Work division

---

## 🚢 Deployment

### Production Deployment (AWS)

**Prerequisites:** AWS credentials, and **Bedrock model access granted manually**
in the console for the three pinned models — that approval is not instant, so
request it first or every call returns `AccessDeniedException`.

```bash
cd infra

./01_ccloud_provision.sh     # CockroachDB Cloud cluster
./02_migrate.sh              # schema + seed + vector index

./03_aws_bootstrap.sh        # S3, SQS, Secrets Manager, IAM, ECR

# Store the real DSNs before anything tries to connect
aws secretsmanager update-secret --secret-id cascade/dsn-app      --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-worker   --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-readonly --secret-string "postgresql://..."

./04_deploy_ecs.sh           # image → ECR, ALB, Fargate service
./05_deploy_lambda.sh        # worker + SQS trigger + 60s EventBridge sweeper
./07_deploy_cloudfront.sh    # HTTPS in front of the ALB  ← must precede 06
./06_deploy_frontend.sh      # Amplify, built against the CloudFront URL
```

**Order matters.** `07` runs before `06`: `NEXT_PUBLIC_API_URL` is baked in at
build time, and Amplify serves over https — pointing the frontend at the raw
http ALB gets every request blocked as mixed content, taking the SSE stream
with it. `06` refuses to build against a non-https URL for exactly this reason.

**Verify the deployment:**
```bash
curl https://<cloudfront>/health
curl https://<cloudfront>/api/admin/verify-index -H "x-admin-token: $ADMIN_TOKEN"  # re-prove the index on Cloud
curl https://<cloudfront>/api/admin/smoke        -H "x-admin-token: $ADMIN_TOKEN"  # confirm Bedrock is live
curl -N https://<cloudfront>/api/events                                            # must stream, not buffer
```

---

## 🧪 Testing

```bash
cd backend
python verify_integration.py          # 34 assertions, resets the world first
python verify_integration.py --keep   # run against existing state
```

It refuses to run in stub mode, so a green result can never be a canned one.
It talks to the engine directly rather than over HTTP — the interrupt case
needs a task that already carries `interrupt_flag` before execution starts,
which isn't reachable through the API without a race.

What it asserts:

| Area | Assertions |
|------|-----------|
| Schema & seed | 13 tables · 4 head rules · 6 services · 12 incidents |
| Vector index | `EXPLAIN` selects `pb_embed_idx` |
| Learn | cold run succeeds · episode written · outbox queued · playbook at 0.30 · **every provenance edge resolves to a real rule version** |
| Reuse | guided mode entered · speedup reported · confidence +0.15 |
| Interrupt | halts · **no side effect applied** · scratchpad persisted · flag cleared |
| Unlearn | cascade <100ms · old version closed · staleness derived · **stale playbook refused** · status demoted |
| Copilot | answers with SQL · rejects 4 injection attempts · allows a normal `created_at` read |
| Contract | all 5 MVP + 6 extension signatures unchanged |

Frontend typecheck and build:
```bash
cd frontend && npm run build
```

---

## 📝 Status (Days 14–16)

### Day 14 — complete
- [x] Wire the two tracks together (the merge had copied files but never connected them)
- [x] Local testing with `CASCADE_STUB_MODE=false`
- [x] All API endpoints verified against a real database
- [x] Frontend SSE streaming working end to end
- [x] cold → guided → cascade → **refusal** demo runs
- [x] Vector index EXPLAIN verified (`docs/query-plans.md`)
- [x] Deployment scripts 05–07 written and syntax-checked

### Day 15 — blocked on AWS credentials
- [ ] Deploy to AWS (scripts ready)
- [ ] Re-prove the vector index on the Cloud cluster
- [ ] Re-measure cold vs guided with Bedrock live

### Day 16
- [ ] Record demo video
- [ ] Devpost submission

---

## 🤝 Team

- **Ashfaq** (Track A): FastAPI routers, Frontend UI, Infrastructure
- **Shawki** (Track B): Core memory engine, AI logic, Worker jobs

**Repository:** https://github.com/ahammadshawki8/Cascade  
**License:** MIT

---

## 🏆 Contest Goals

**Target:** 1st Place ($5,000)

**Judging Criteria:**
1. ✅ **Agentic Memory Design** - Provenance-based staleness, vector retrieval
2. ✅ **Technical Implementation** - O(1) cascade, two-phase retrieval
3. ✅ **Real-World Impact** - On-call SRE automation
4. ⏳ **Production Readiness** - Full deployment pipeline
5. ✅ **Creativity & Originality** - Learn/Reuse/Unlearn paradigm

---

## 📞 Support

**Issues:** https://github.com/ahammadshawki8/Cascade/issues  
**Demo Video:** [To be recorded]  
**Devpost:** [To be submitted]

---

**Status:** ✅ Integration Complete - Ready for Testing  
**Next Milestone:** Local verification with real database  
**Submission Deadline:** August 16, 2026
