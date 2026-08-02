# CASCADE — Track B Development Memory
## Shawki's Core Memory & AI Engine Implementation Guide

**Project:** CockroachDB × AWS Hackathon - CASCADE  
**Role:** Track B (Core Memory & AI Engine)  
**Partner:** Ashfaq (Track A - Shell: API + Frontend + Infra)  
**Timeline:** 16 days (Jul 31 → Aug 16, 2026)  
**Submission Deadline:** Aug 16, 2026 (48h before hard deadline)

---

## 🚨 STRICT DEVELOPMENT RULES

### DO NOT Create These Files
- ❌ **NO** markdown summaries after task completion
- ❌ **NO** "CHANGES.md", "UPDATES.md", "SUMMARY.md" files
- ❌ **NO** status reports in markdown format
- ❌ **NO** additional documentation unless explicitly requested
- ❌ **NO** duplicate guides or redundant explanations

### Communication Style
- ✅ Provide concise status updates in chat ONLY
- ✅ Update code and tests directly
- ✅ Use inline code comments for decisions
- ✅ Keep responses brief and actionable
- ✅ Focus on implementation, not documentation

### Repository Strategy
This is a **STANDALONE repository** for Track B development:
- Work independently until integration time
- No merge conflicts with Ashfaq's repo
- Manual integration when ready
- Keep only essential reference docs

**When you complete a task:** Just say "Done" or give a 1-2 sentence summary. NO markdown files.  

---

## 🎯 CONTEST OBJECTIVE

**Win 1st Place ($5,000)** - Build an agentic incident-response application using:
- CockroachDB as persistent memory layer
- ≥2 CockroachDB tools (we use 3: MCP Server, Distributed Vector Indexing, ccloud CLI)
- ≥1 AWS service (we use: Bedrock, Lambda, S3, SQS, ECS, EventBridge)

**Judging Criteria (optimize for all 5):**
1. Agentic Memory Design
2. Technical Implementation  
3. Real-World Impact
4. Production Readiness
5. Creativity & Originality

---

## 🧠 WHAT CASCADE IS

An on-call SRE remediation agent that:
- **LEARNS** - Resolves novel incidents with Claude on Bedrock, compiles successful trajectories into reusable playbooks
- **REUSES** - Retrieves playbooks via CockroachDB distributed vector search, executes 3-5× faster
- **UNLEARNS** - When policy rules change, staleness is derived from provenance, stale playbooks never execute

**Domain:** Incident response runbooks (rollbacks, restarts, scale-ups for bad deploys, error spikes, resource exhaustion)

---

## 📋 YOUR EXCLUSIVE OWNERSHIP (Track B)

### Core Files (backend/app/core/)
- ✅ `models.py` - Shared types (FROZEN after Day 0)
- ✅ `contracts.py` - Interface signatures (FROZEN after Day 0)  
- 🔨 `retrieval.py` - Two-phase vector retrieval
- 🔨 `freshness.py` - Point-of-use dep check
- 🔨 `executor.py` - Explore + guided loops, interrupts
- 🔨 `tools.py` - Mock world (5 tools)
- 🔨 `compiler.py` - Trajectory → playbook + deps
- 🔨 `confidence.py` - Lifecycle math
- 🔨 `cascade.py` - O(1) rule-change txn
- 🔨 `llm.py` - Bedrock clients, retries, budgets

### Worker (backend/worker/)
- 🔨 `handler.py` - Lambda entry point
- 🔨 `jobs.py` - Status cache, interrupts, relearn, recheck

### Schema (migrations/)
- ✅ `001_schema.sql` - All tables (FROZEN after Day 0)
- ✅ `002_seed.sql` - Initial data (FROZEN after Day 0)

### Documentation (docs/)
- 🔨 `query-plans.md` - EXPLAIN output proving vector index (Week 1 gate)
- 🔨 `skills-review.md` - Agent Skills findings (Week 4)

### Tests
- 🔨 `backend/app/tests/unit/` - Unit tests

✅ = Already exists  
🔨 = You need to build

---

## 🔗 THE CONTRACT (How Tracks Connect)

**Track A imports ONLY:** `backend/app/core/contracts.py`

**Signatures are FROZEN after Day 0.** Changing a signature = contract PR requiring Ashfaq's approval.

### MVP Functions (Week 1-3)
```python
async def retrieve(task_text: str) -> PlaybookCandidate | None
async def check_freshness(playbook_id: str | UUID) -> FreshnessResult
async def run_task(task_id: str | UUID) -> None
async def change_rule(rule_key, new_body, new_params, actor) -> ImpactResult
async def answer_analytics_question(question: str) -> CopilotAnswer
```

### Extension Functions (Week 4+, after MVP gate)
```python
def decide_autonomy(playbook, step) -> "AUTO_EXECUTE" | "REQUIRES_APPROVAL"
async def resolve_approval(approval_id, decision, resolved_by) -> None
async def generate_postmortem(episode_id) -> str
async def list_insights(include_dismissed=False) -> list[Insight]
async def dismiss_insight(insight_id) -> None
async def simulate_rule_change(rule_key, new_body, new_params) -> ImpactResult
```

**Stub Mode:** All functions have stub bodies returning realistic data when `CASCADE_STUB_MODE=true`. Ashfaq builds UI against stubs, you fill bodies. No import swap ever needed.

---

## 🗓️ 16-DAY SPRINT BREAKDOWN

**Today:** Day 0 (Fri Aug 1) - Contract PR must merge today  
**Final submission:** Sun Aug 16 (48h early buffer)

### Day 0 (COMPLETE) - Foundation
- [x] Review Day-0 skeleton
- [x] Agree on D-1→D-7 decisions (see Decisions section below)
- [x] Ensure `migrations/001_schema.sql` includes all extension tables (approvals, insights, postmortems)
- [x] Verify `tasks.status` has `'awaiting_approval'` (line 72 comment includes it)
- [x] Contract PR merged (pushed to GitHub as ahammadshawki8)

### Day 1 (COMPLETE) - Tools & LLM
**Files:** `core/tools.py`, `core/llm.py`
- [x] 5 mock tools: `get_incident`, `get_rules`, `check_remediation_eligibility`, `apply_remediation`, `notify_oncall` (all DB-backed with idempotency)
- [x] Bedrock clients: AgentClient, FastClient, EmbedClient with retry logic and circuit breaker
- [x] Model IDs: `anthropic.claude-sonnet-5` (agent), `anthropic.claude-haiku-4-5` (fast), `amazon.titan-embed-text-v2:0` (embeddings)
- [x] Retry logic (3 attempts, exponential backoff), budget tracking (15 steps, 60s, 25k tokens)
- [x] Circuit breaker (5 failures → 30s open)
- **Gate:** Bedrock environment configured (full calls deferred to Day 2 with executor)
- [ ] Retry logic, budget tracking (15 steps, 60s, 25k tokens)
- **Gate:** Bedrock smoke call works

### Day 2 (COMPLETE) - Executor Explore Loop
**Files:** `core/executor.py`, `db.py` (new)
- [x] `run_task()` skeleton: retrieve → freshness → explore vs guided decision
- [x] Explore mode: Simulated tool-calling loop (full Claude integration deferred until Bedrock access)
- [x] Stream steps over SSE (infrastructure ready)
- [x] Episode write (truncated to CRDB, S3 stub for full JSON)
- [x] Task status transitions: `queued` → `running` → `succeeded`/`failed`
- [x] Budget tracking integrated (15 steps, 60s, 25k tokens)
- [x] DB connection wrapper with retry logic (run_txn, q methods)
- **Note:** Full Bedrock Claude integration pending AWS credentials setup

### Day 3 (Mon Aug 3) - Vector Retrieval Phase 1 🚨 CRITICAL GATE
**Files:** `core/retrieval.py`, `docs/query-plans.md`
- [ ] Titan V2 embedding (1024-d, `normalize: true`)
- [ ] Phase 1: Pure ANN query with `<->` (L2) operator
  ```sql
  SELECT playbook_id, embedding <-> $1 AS dist 
  FROM playbooks 
  ORDER BY embedding <-> $1 LIMIT 20;
  ```
- [ ] Run `EXPLAIN` via Claude Code connected to MCP Server
- [ ] **SCREEN-RECORD the MCP workflow** (needed for video)
- [ ] Paste EXPLAIN output to `docs/query-plans.md`
- **🔴 GATE:** Index `pb_embed_idx` MUST appear in plan. If not, STOP EVERYTHING and fix.

### Day 4 (Tue Aug 4) - Compiler
**Files:** `core/compiler.py`
- [ ] Trajectory → PlaybookSpec JSON (Claude Sonnet call)
- [ ] Pydantic validation against `PlaybookSpec` schema
- [ ] Dep extraction from rule citations
- [ ] Safety lint (no unbounded loops, external calls)
- [ ] Insert `playbooks` + `playbook_deps` + audit in one txn
- [ ] Enqueue `compile` outbox event
- **Gate:** INC-1001 resolves end-to-end

### Day 5 (Wed Aug 5) - Freshness & Retrieval Phase 2-3
**Files:** `core/freshness.py`, update `retrieval.py`
- [ ] Phase 2: PK lookup filter `status_cache IN ('active','candidate','suspect')`
- [ ] Phase 3: Freshness join
  ```sql
  SELECT d.rule_key, d.rule_version, r.version AS head
  FROM playbook_deps d
  JOIN rules r ON d.rule_key = r.rule_key AND r.valid_to IS NULL
  WHERE d.playbook_id = $1 AND d.rule_version != r.version
  ```
- [ ] Return `Fresh` or `Stale(stale_deps)` - NEVER a bool

### Day 6 (Thu Aug 6) - Guided Path & Confidence 🚨 STOP-THE-WORLD GATE
**Files:** `core/confidence.py`, update `executor.py`
- [ ] Precondition check (Haiku, one call)
- [ ] Param extraction from task text
- [ ] Guided execution: steps run directly, no per-step LLM
- [ ] Confidence update: `uses++`, `successes++` or `failures++`
- [ ] Episode `mode='guided'`
- **🔴 GATE:** Guided run ≥3× faster than cold. IF NOT, ALL FEATURE WORK STOPS.

### Day 7 (Fri Aug 7) - Cascade Transaction
**Files:** `core/cascade.py`
- [ ] O(1) txn: close old rule, insert new rule, ONE outbox, ONE audit (4 writes total)
- [ ] Post-commit: SQS publish, InterruptBus fan-out, SSE `rule.changed`
- [ ] **Gate:** HTTPS live (Ashfaq handles deploy)

### Day 8 (Sat Aug 8) - Interrupts
**Files:** Update `executor.py`
- [ ] Listen to `InterruptBus` events (from `app/bus.py`)
- [ ] Check `tasks.interrupt_flag` before side-effects
- [ ] Scratchpad persist on interrupt
- [ ] Re-plan with fresh `get_rules` call
- [ ] Resume with new rule versions

### Day 9 (Sun Aug 9) - Worker Infrastructure
**Files:** `worker/handler.py`, `worker/jobs.py`
- [ ] Lambda entry: handle SQS events vs sweeper events
- [ ] Outbox claim with idempotency
- [ ] `rule_changed` job: status_cache updates (≤100 rows/txn), interrupt flags, relearns

### Day 10 (Mon Aug 10) - Relearn Job
**Files:** Update `worker/jobs.py`
- [ ] `relearn` job: synthesize task, run explore, compile v2
- [ ] Set `supersedes` → lineage v1→v2
- [ ] POST `/internal/sse` → `playbook.changed`

### Day 11 (Tue Aug 11) - Ops Copilot 🚨 MVP COMPLETE
**Files:** `core/copilot.py` (NEW)
- [ ] SQL synthesis from question (Claude Haiku)
- [ ] Validate: starts with SELECT/WITH, single statement
- [ ] Execute as `cascade_readonly` with 3s timeout + LIMIT 200 wrapper
- [ ] Return SQL + results for display
- **🟢 GATE:** MVP thin-slice complete (learn → reuse → unlearn)

### Day 12 (Wed Aug 12) - Edge Cases & Skills
**Files:** `docs/skills-review.md`
- [ ] Edge-matrix audit (19 cases in spec §10)
- [ ] Run Agent Skills against cluster
- [ ] Document findings in `skills-review.md`
- **Gate:** Reset returns clean v1 world

### Day 13 (Thu Aug 13) - 🔒 CODE FREEZE 6pm
- [ ] Bug fixes only
- [ ] No new features

### Day 14 (Fri Aug 14) - Documentation
- [ ] Review Ashfaq's README technical sections
- [ ] Verify `DEVIATIONS.md` (or write "None.")

### Day 15 (Sat Aug 15) - Video
- [ ] Narrate engine beats for video

### Day 16 (Sun Aug 16) - SUBMIT
- [ ] Verify repo/license/About settings
- [ ] Final smoke test
- [ ] ✅ SUBMIT DEVPOST

---

## 🔑 CRITICAL DESIGN DECISIONS (READ FIRST)

These 8 decisions are BINDING. Every module assumes them.

### D1. Staleness is DERIVED (not mass-updated)
**Problem:** Mass-updating `playbooks.status` causes write contention.
**Solution:** 
- Staleness = a JOIN, not a column
- `status_cache` is async UI convenience only
- Point-of-use freshness check before EVERY execution
- O(1) cascade transaction (4 writes, no fan-out)

### D2. Vector Index Uses ONE Metric (L2)
**CRITICAL:** Titan V2 with `normalize: true` → L2 ≡ cosine ranking
- Index: default (L2) opclass
- **Every query MUST use `<->`** (L2 operator)
- NEVER use `<=>` or `<#>` (disables index)

### D3. Two-Phase Retrieval (prevents planner risk)
Never mix vector ORDER BY with scalar filters in one query.
**Phase 1:** Pure ANN (20 results)
**Phase 2:** PK lookup + filter `status_cache IN ('active','candidate','suspect')`
**Phase 3:** Freshness check top candidates

### D4. Interrupts via In-Process Event Bus
- `InterruptBus` in same FastAPI service (microseconds)
- Durable fallback: check `tasks.interrupt_flag` before side-effects
- Multi-instance: optional SNS/SQS (flag-off for demo)

### D5. Outbox Pattern + Immediate Post-Commit Publish
- Cascade txn inserts ONE outbox row
- Post-commit: best-effort SQS publish (~1s latency)
- Sweeper: every 60s scans unprocessed >30s old
- Idempotency: `UPDATE ... WHERE claimed_at IS NULL RETURNING`

### D6. MCP Usage is Honest
**Primary (MUST DEMO):** Dev workflow via Claude Code + Managed MCP
- Schema exploration
- Query plan investigation (Day 3 EXPLAIN gate)
- Screen-record for video

**Secondary:** Ops Copilot panel (read-only SQL synthesis)
- Ad-hoc analytics
- Shows executed SQL
- Clearly labeled "exploratory"

### D7. Domain = SRE Incident Response
NOT fintech refunds. Runbooks for:
- Bad deploys → rollback
- Error spikes → restart
- Resource exhaustion → scale_up

Policy rules govern: approval tiers, rollback windows, notification, single-action limits

### D8. Demo-First De-Risking
- EXPLAIN gate moved to Week 1 (not Week 5)
- Thin-slice gate end of Week 3
- Weekly fallback footage
- Never-cut list: freshness gate, cascade txn, metrics, interrupts, Ops Copilot, MCP footage

---

## 🔧 TECH STACK

### Database
- CockroachDB Cloud (free tier), v26.x
- Database: `cascade`
- Vector index enabled (verify Day 0)

### Backend
- Python 3.12
- FastAPI + uvicorn
- `psycopg[binary,pool]` 3.x
- Pydantic v2

### LLM (Amazon Bedrock, us-east-1)
```python
# AnthropicBedrockMantle client: pip install "anthropic[bedrock]"
# Agent + Compiler
BEDROCK_AGENT_MODEL_ID = "anthropic.claude-sonnet-5"

# Fast calls (precondition, param extraction, recheck)  
BEDROCK_FAST_MODEL_ID = "anthropic.claude-haiku-4-5"

# Embeddings (1024-d, normalize: true)
BEDROCK_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
```

**⚠️ Day-0 Action:** Bedrock model access MUST be manually enabled in AWS console. `AccessDeniedException` if missing.

### Worker
- AWS Lambda (Python 3.12)
- SQS trigger (`cascade-events`)
- EventBridge 60s sweeper

### Storage
- S3: `cascade-episodes-<acct>` for raw trajectory JSON
- Secrets Manager: DB DSNs, tokens

---

## 📊 DATABASE SCHEMA (Day 0 - FROZEN)

### Core Tables
```sql
-- Policy rules (versioned)
rules (rule_key, version, domain, body, params JSONB, valid_from, valid_to, changed_by)

-- Compiled playbooks
playbooks (playbook_id UUID, name, domain, version, supersedes UUID, 
           status_cache, spec JSONB, confidence, uses, successes, failures,
           embedding VECTOR(1024), created_at, updated_at)

-- Provenance edges
playbook_deps (playbook_id, rule_key, rule_version, citation, extraction_confidence)
  PRIMARY KEY (playbook_id, rule_key, rule_version)

-- Tasks
tasks (task_id, input, status, result, mode, playbook_id, 
       interrupt_flag, interrupt_reason, scratchpad JSONB, 
       created_at, finished_at)

-- Episodes (performance history)
episodes (episode_id, task_id, outcome, mode, steps, latency_ms, 
          tokens, s3_key, created_at)

-- Transactional outbox
outbox (event_id, kind, payload JSONB, created_at, processed_at, 
        claimed_by, claimed_at)

-- Audit log
audit_log (entry_id, kind, actor, details JSONB, at)
```

### Extension Tables (Day 0, wire up Week 4+)
```sql
-- Autonomy gating
approvals (approval_id, task_id, playbook_id, step_index, action,
           status, reason, requested_at, resolved_at, resolved_by)

-- Trend detection
insights (insight_id, kind, summary, related_rule_key,
          suggested_params JSONB, evidence JSONB, created_at, dismissed)

-- Postmortems
postmortems (postmortem_id, episode_id, s3_key, summary, generated_at)
```

### Mock World
```sql
mock_incidents (incident_id, kind, severity, service_name, service_tier, 
                deploy_timestamp, state, created_at)
mock_action_log (action_id, incident_id, action, outcome, at)
```

### Critical Indices
```sql
CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops);
CREATE INDEX tasks_running_idx ON tasks (created_at) WHERE status = 'running';
CREATE INDEX playbooks_active_idx ON playbooks (domain, confidence DESC) 
  WHERE status_cache = 'active';
```

---

## 🎬 SSE EVENT NAMES (Frozen Day 0)

Track A subscribes by string. NEVER change these:
- `task.{id}.step` - Streaming step execution
- `task.{id}.status` - Task status change
- `rule.changed` - Rule version updated
- `playbook.changed` - Playbook compiled/invalidated
- `metrics.tick` - Metrics updated
- `approval.requested` - Autonomy gate triggered (extension)
- `insight.created` - New trend detected (extension)

---

## 🔄 THE THREE CORE FLOWS

### Flow A: Learn (Cold Run)
1. Browser → `POST /api/tasks` → task `queued`
2. Executor starts → retrieval finds nothing → **explore mode**
3. Claude Sonnet converse loop: `get_rules` → `get_incident` → `check_eligibility` → `apply_remediation` → `notify_oncall`
4. Every step streamed over SSE
5. `final_answer {"outcome":"success"}` → task `succeeded`
6. Episode written (CRDB + S3)
7. Outbox `compile` + SQS publish
8. Lambda claims event → compiler runs → PlaybookSpec JSON → Pydantic parse → deps → embed → insert `playbooks` + `playbook_deps`
9. Lambda POST `/internal/sse` → `playbook.changed` → card appears in UI

### Flow B: Reuse (Guided Run)
1. `POST /api/tasks` → embed task text (Titan)
2. Phase 1: ANN query `<->` (vector index)
3. Phase 2: PK lookup + metadata filter
4. **Phase 3: Point-of-use freshness join** (NEVER execute if stale)
5. Precondition check (Haiku)
6. Params bound
7. Steps executed directly (no LLM)
8. Counters updated
9. Episode `mode='guided'`
10. Metric bar shows cold vs guided delta

### Flow C: Unlearn (Rule Change Cascade)
1. Admin edits rule in Policy Panel
2. Confirm dialog shows `/api/impact` results
3. `POST /api/rules/{key}` → cascade txn (4 writes, O(1))
4. Post-commit: SQS publish, InterruptBus, SSE `rule.changed`
5. Cards flip red optimistically (UI query `/api/impact`)
6. Running executor sees bus event (μs) or flag before next side-effect → scratchpad → re-plan
7. Lambda `rule_changed` job: `status_cache` updates (batched), interrupt flags, relearn queue
8. `relearn` synthesizes task → explore → compile v2 with `supersedes`
9. Lineage v1→v2 appears in UI (~60s)

---

## 🛠️ DEVELOPMENT WORKFLOW

### Local Setup
```bash
# Start local CRDB
docker run -d -p 26257:26257 cockroachdb/cockroach:latest start-single-node --insecure

# Apply migrations
cd backend
make seed

# Run API
uvicorn app.main:app --reload

# Test worker locally
python -m worker.handler --once
```
