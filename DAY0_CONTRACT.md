# Day 0 Contract - CASCADE Project

**Date:** August 1, 2026  
**Parties:** Ashfaq (Track A - Shell: API + Frontend + Infra) & Shawki (Track B - Engine: Core + Worker)  
**Project:** CockroachDB × AWS Hackathon - CASCADE  
**Deadline:** August 16, 2026, 5:00 PM EDT (48h before hard deadline)  
**Status:** BINDING after both parties sign off

---

## PURPOSE

This contract defines the **FROZEN INTERFACE** and **GROUND TRUTH** that both teammates MUST agree on before ANY code is written. After Day 0:
- Changing ANY signature, type, table, column, SSE event name, or decision requires a **CONTRACT PR** with approval from BOTH teammates
- This is NOT a design doc - this is an **executable contract**
- If this file and any other doc disagree, **THIS FILE WINS**

**Contract Scope:**
- Data models with EXACT type signatures
- Function signatures in `contracts.py` (Track A imports ONLY this file from Track B)
- Complete database schema with ALL tables, columns, indices, constraints
- SSE event names (frontend subscribes by string)
- Environment variables matrix
- All 7 Day-0 decisions (D1-D7)
- Integration boundaries and workflows

---

## CONTEST REQUIREMENTS (Context)

**Hackathon:** CockroachDB × AWS - "Build with Agentic Memory"  
**Must use ≥2 CockroachDB tools:** We use 3:
1. **Distributed Vector Indexing** (core to retrieval)
2. **Managed MCP Server** (dev workflow + Ops Copilot)
3. **ccloud CLI** (cluster provisioning)

**Must use ≥1 AWS service:** We use 6:
- Amazon Bedrock (Claude Sonnet/Haiku, Titan embeddings)
- AWS Lambda (worker)
- S3 (trajectory archives)
- SQS (event queue)
- ECS Fargate (API + executor)
- EventBridge (sweeper schedule)

**Judging Criteria (optimize ALL 5):**
1. Agentic Memory Design
2. Technical Implementation
3. Real-World Impact
4. Production Readiness
5. Creativity & Originality


---

## 1. FROZEN DATA MODELS (`core/models.py`)

These types are FROZEN after Day 0. Track A and Track B both import from this file.

### 1.1 Enums

```python
class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"  # Extension (Week 4+)

class ExecutionMode(str, Enum):
    EXPLORE = "explore"
    GUIDED = "guided"

class PlaybookStatus(str, Enum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    SUSPECT = "suspect"
    STALE = "stale"
    ARCHIVED = "archived"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class InsightKind(str, Enum):
    THRESHOLD_TREND = "threshold_trend"
    FAILURE_PATTERN = "failure_pattern"
    COVERAGE_GAP = "coverage_gap"
```

### 1.2 Core Response Types

```python
class PlaybookCandidate(BaseModel):
    """Result from two-phase vector retrieval"""
    playbook_id: UUID
    name: str
    version: int
    confidence: float
    distance: float
    status_cache: str

class StaleRule(BaseModel):
    """A single stale rule dependency"""
    rule_key: str
    expected_version: int
    actual_version: int

class FreshnessResult(BaseModel):
    """Point-of-use freshness check result - NEVER a bool"""
    is_fresh: bool
    stale_rules: list[StaleRule] = Field(default_factory=list)

class ImpactResult(BaseModel):
    """Rule change impact analysis"""
    affected_playbooks: list[UUID]
    affected_count: int
    will_trigger_cascade: bool

class CopilotAnswer(BaseModel):
    """Ops Copilot SQL synthesis response"""
    sql: str
    results: list[dict[str, Any]]
    row_count: int

class Insight(BaseModel):
    """Trend detection insight (Extension)"""
    insight_id: UUID
    kind: InsightKind
    summary: str
    related_rule_key: Optional[str] = None
    suggested_params: Optional[dict[str, Any]] = None
    evidence: dict[str, Any]
    created_at: datetime
    dismissed: bool = False
```

### 1.3 Compiler Types

```python
class Step(BaseModel):
    """Single playbook step"""
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Optional[str] = None
    timestamp: datetime

class PlaybookSpec(BaseModel):
    """Compiled playbook specification - validated by Pydantic"""
    name: str
    domain: str
    description: str
    preconditions: list[str]  # 1-6 testable statements
    parameters: list[dict[str, Any]]
    steps: list[dict[str, Any]]  # 2-8 steps
    rule_citations: list[dict[str, Any]]  # ≥1 or compile rejected
```


---

## 2. FROZEN FUNCTION SIGNATURES (`core/contracts.py`)

**CRITICAL:** Track A imports ONLY `core/contracts.py`. Track A NEVER imports from other `core/*` files.

### 2.1 MVP Functions (Week 1-3)

```python
async def retrieve(task_text: str) -> Optional[PlaybookCandidate]:
    """
    Two-phase vector retrieval for playbook candidates.
    Returns best match or None if no good candidates found.
    
    Phase 1: Pure ANN query (L2 distance, <-> operator)
    Phase 2: PK lookup + status filter
    Phase 3: Freshness check (point-of-use)
    """
    
async def check_freshness(playbook_id: UUID) -> FreshnessResult:
    """
    Point-of-use freshness check via provenance join.
    CRITICAL: NEVER returns bool - always returns FreshnessResult.
    
    Returns:
        FreshnessResult with is_fresh=True/False and stale_rules list
    """
    
async def run_task(task_id: UUID) -> None:
    """
    Main executor entry point.
    - Runs explore mode (cold) or guided mode (warm)
    - Updates task status
    - Streams SSE events (task.{id}.step, task.{id}.status)
    - Writes episodes to CRDB + S3
    - Budget: 15 steps max, 60s wall clock, 25k tokens
    """
    
async def change_rule(
    rule_key: str,
    new_body: str,
    new_params: dict,
    actor: str
) -> ImpactResult:
    """
    O(1) cascade transaction - versions the rule.
    
    Transaction (4 writes total):
        1. Close old rule version (UPDATE valid_to)
        2. Insert new rule version
        3. Insert ONE outbox event
        4. Insert ONE audit row
    
    Post-commit (best-effort):
        - SQS publish for worker
        - InterruptBus notifications
        - SSE broadcast (rule.changed)
        - Impact query for UI
    
    Returns: ImpactResult with affected playbook count
    """
    
async def answer_analytics_question(question: str) -> CopilotAnswer:
    """
    Ops Copilot: synthesize read-only SQL from natural language.
    - Uses cascade_readonly role (SELECT-only, 3s timeout)
    - Validates SQL (must start with SELECT/WITH)
    - Wraps with LIMIT 200
    - Returns SQL + results for display
    """
```


### 2.2 Extension Functions (Week 4+, after MVP gate)

```python
def decide_autonomy(playbook: Playbook, step: Step) -> Literal["AUTO_EXECUTE", "REQUIRES_APPROVAL"]:
    """
    Autonomy gating using static risk map (D2).
    Risk map (inside confidence.py):
        - apply_remediation: high risk
        - notify_oncall: low risk
        - reads (get_*): no risk
    
    Logic:
        high risk + (low confidence OR high-tier service) → REQUIRES_APPROVAL
        else → AUTO_EXECUTE
    """
    
async def resolve_approval(
    approval_id: UUID,
    decision: Literal["approved", "rejected"],
    resolved_by: str
) -> None:
    """
    Handle approval decision and resume/fail task.
    - Updates approval row (status, resolved_at, resolved_by)
    - If approved: resumes task from scratchpad (reloads from DB, not just memory)
    - If rejected: fails task with reason
    - Budget clock EXCLUDES approval wait time (D1)
    """
    
async def generate_postmortem(episode_id: UUID) -> str:
    """
    Generate postmortem markdown from episode trajectory.
    - Runs in worker (NOT in run_task - keeps metrics clean)
    - Stores markdown in S3 (D4)
    - Returns S3 key: postmortems/{episode_id}.md
    - Enqueued as outbox event when task completes
    """
    
async def list_insights(include_dismissed: bool = False) -> list[Insight]:
    """
    List trend detection insights.
    - Daily worker job scans patterns
    - Returns insights with suggested rule changes
    - suggested_params pre-fill Policy Panel form
    """
    
async def dismiss_insight(insight_id: UUID) -> None:
    """
    Dismiss an insight (sets dismissed=true).
    """
    
async def simulate_rule_change(
    rule_key: str,
    new_body: str,
    new_params: dict
) -> ImpactResult:
    """
    Dry-run impact analysis without committing.
    - Runs same impact query as change_rule
    - NEVER writes to DB
    - Used by UI "Impact Preview" modal
    """
```


---

## 3. COMPLETE DATABASE SCHEMA

**Owner:** Shawki (Track B)  
**File:** `migrations/001_schema.sql`  
**Status:** FROZEN after Day 0 - changes need contract PR

### 3.1 Core Tables

#### rules (Policy Rules - Versioned)
```sql
CREATE TABLE rules (
    rule_key VARCHAR(100) NOT NULL,
    version INT NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    body TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,  -- NULL = current version
    changed_by VARCHAR(100) NOT NULL,
    PRIMARY KEY (rule_key, version)
);
CREATE INDEX rules_current_idx ON rules (rule_key, valid_to) WHERE valid_to IS NULL;
```

**Seed rules (v1, in 002_seed.sql):**
- `incident.auto_remediate_tier`: min_tier=2 (tier 1 services require manual approval)
- `incident.rollback_window`: hours=24 (rollback allowed within 24h of deploy)
- `incident.notify`: {} (on-call must be notified after any remediation)
- `incident.single_action`: {} (max 1 automated action per incident)

#### playbooks (Compiled Runbooks)
```sql
CREATE TABLE playbooks (
    playbook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    version INT NOT NULL DEFAULT 1,
    supersedes UUID REFERENCES playbooks(playbook_id),  -- Lineage v1→v2
    status_cache VARCHAR(20) NOT NULL DEFAULT 'candidate',
        -- Values: active|candidate|suspect|stale|archived
        -- CRITICAL: This is UI CACHE ONLY (D1)
        -- Authoritative staleness = freshness join
    spec JSONB NOT NULL,  -- Full PlaybookSpec
    confidence FLOAT NOT NULL DEFAULT 0.5,
    uses INT NOT NULL DEFAULT 0,
    successes INT NOT NULL DEFAULT 0,
    failures INT NOT NULL DEFAULT 0,
    embedding VECTOR(1024),  -- Titan V2 embeddings (normalized, L2 metric)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CRITICAL: Vector index for Phase 1 ANN query (D3)
CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops);
CREATE INDEX playbooks_active_idx ON playbooks (domain, confidence DESC) 
    WHERE status_cache = 'active';
```

**Vector Index Notes (D3):**
- Titan V2 with `normalize: true` → L2 distance ≡ cosine ranking
- Index uses L2 opclass (`vector_l2_ops`)
- ALL queries MUST use `<->` (L2 operator) - never `<=>` or `<#>`
- Week 1 gate: EXPLAIN must show pb_embed_idx usage

#### playbook_deps (Provenance Edges)
```sql
CREATE TABLE playbook_deps (
    playbook_id UUID NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    rule_key VARCHAR(100) NOT NULL,
    rule_version INT NOT NULL,
    citation TEXT,  -- "step 2: eligibility check"
    extraction_confidence FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (playbook_id, rule_key, rule_version),  -- D2: version in PK
    FOREIGN KEY (rule_key, rule_version) REFERENCES rules(rule_key, version)
);
CREATE INDEX deps_rule_idx ON playbook_deps (rule_key, rule_version);
```

**Freshness Check (D1 - THE authoritative staleness definition):**
```sql
-- Returns rows ONLY for stale deps. Empty result = fresh.
SELECT d.rule_key, d.rule_version AS depends_on, r.version AS head
FROM playbook_deps d
JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
WHERE d.playbook_id = $1 AND r.version <> d.rule_version;
```


#### tasks (Working Memory)
```sql
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
        -- Values: queued|running|succeeded|failed|awaiting_approval
        -- D1: awaiting_approval added for extension
    result JSONB,
    mode VARCHAR(10),  -- explore|guided
    playbook_id UUID REFERENCES playbooks(playbook_id),
    interrupt_flag BOOLEAN NOT NULL DEFAULT FALSE,  -- D4: durable fallback
    interrupt_reason TEXT,
    scratchpad JSONB,  -- For interrupt resume
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX tasks_running_idx ON tasks (created_at) WHERE status = 'running';
CREATE INDEX tasks_status_idx ON tasks (status, created_at DESC);
```

**Outcome Mapping (v3.1):**
- `final_answer {"outcome":"success"}` → status='succeeded', result='remediated'
- `final_answer {"outcome":"escalated"}` → status='succeeded', result='escalated' (policy-compliant success)
- Budget breach / tool error → status='failed'

#### episodes (Performance History)
```sql
CREATE TABLE episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    outcome VARCHAR(20) NOT NULL,  -- success|failed|interrupted
    mode VARCHAR(10) NOT NULL,  -- explore|guided
    steps INT NOT NULL,
    latency_ms INT NOT NULL,  -- CRITICAL: excludes approval wait time (D1)
    tokens INT NOT NULL,
    s3_key TEXT,  -- Full trajectory JSON in S3: episodes/{episode_id}.json
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX episodes_task_idx ON episodes (task_id);
CREATE INDEX episodes_mode_idx ON episodes (mode, created_at DESC);
```

**Metrics Calculation:**
```sql
-- Cold vs guided delta (Week 2 gate: guided ≥3× faster)
SELECT mode, AVG(latency_ms), AVG(steps), AVG(tokens)
FROM episodes
WHERE outcome = 'success'
GROUP BY mode;
```

#### outbox (Transactional Outbox - D5)
```sql
CREATE TABLE outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
        -- Values: compile|rule_changed|relearn|recheck_suspect|postmortem
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMPTZ
);
CREATE INDEX outbox_unprocessed_idx ON outbox (created_at) 
    WHERE processed_at IS NULL AND claimed_at IS NULL;
```

**Idempotency (D5a):**
```sql
-- Worker claims event
UPDATE outbox 
SET claimed_by = $worker, claimed_at = NOW() 
WHERE event_id = $1 
  AND (claimed_at IS NULL OR claimed_at < NOW() - INTERVAL '5 minutes')
RETURNING event_id;
-- Zero rows returned = already claimed = skip
```

#### audit_log (Append-Only)
```sql
CREATE TABLE audit_log (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
        -- rule_changed|playbook_compiled|task_executed|etc
    actor VARCHAR(100) NOT NULL,
    details JSONB NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX audit_kind_idx ON audit_log (kind, at DESC);
```


### 3.2 Extension Tables (Wire up Week 4+)

#### approvals (Autonomy Gating)
```sql
CREATE TABLE approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    playbook_id UUID REFERENCES playbooks(playbook_id),
    step_index INT NOT NULL,
    action TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- Values: pending|approved|rejected|expired
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)
);
CREATE INDEX approvals_pending_idx ON approvals (requested_at) 
    WHERE status = 'pending';
```

#### insights (Trend Detection)
```sql
CREATE TABLE insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
        -- threshold_trend|failure_pattern|coverage_gap
    summary TEXT NOT NULL,
    related_rule_key VARCHAR(100),
    suggested_params JSONB,  -- Pre-fills Policy Panel form
    evidence JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX insights_active_idx ON insights (created_at DESC) 
    WHERE NOT dismissed;
```

#### postmortems
```sql
CREATE TABLE postmortems (
    postmortem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL UNIQUE REFERENCES episodes(episode_id),
    s3_key TEXT NOT NULL,  -- D4: markdown in S3
    summary TEXT NOT NULL,  -- One-line teaser
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX postmortems_episode_idx ON postmortems (episode_id);
```

### 3.3 Mock World (Demo Environment)

```sql
CREATE TABLE mock_incidents (
    incident_id VARCHAR(20) PRIMARY KEY,  -- INC-1001, INC-1002, etc
    kind VARCHAR(50) NOT NULL,
        -- bad_deploy|error_spike|resource_exhaustion
    severity VARCHAR(10) NOT NULL,  -- P1|P2|P3
    service_name VARCHAR(100) NOT NULL,
    service_tier VARCHAR(20) NOT NULL,  -- production|staging|dev
    deploy_timestamp TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL DEFAULT 'open',
        -- open|mitigated|resolved
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE mock_action_log (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(20) NOT NULL REFERENCES mock_incidents(incident_id),
    action VARCHAR(50) NOT NULL,  -- rollback|restart|scale_up|notify
    outcome VARCHAR(20) NOT NULL,  -- success|failed
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX action_log_incident_idx ON mock_action_log (incident_id, at DESC);
```

**Seed Incidents (002_seed.sql):**
- INC-1001 to INC-1012 (12 scenarios covering happy path, tier blocks, window blocks, boundaries)
- Services: svc-payments (tier 1), svc-checkout (tier 2), svc-search (tier 3), etc.

### 3.4 Reset Behavior (v3.1)

**POST /api/admin/reset truncates:**
```sql
TRUNCATE tasks, episodes, playbook_deps, playbooks, outbox,
         mock_action_log, mock_incidents, mock_services, rules,
         approvals, insights, postmortems CASCADE;
-- audit_log deliberately NOT truncated (append-only history)
```
Then re-runs 002_seed.sql to restore clean v1 world.


---

## 4. FROZEN SSE EVENT NAMES

**CRITICAL:** Frontend subscribes by string. NEVER change these after Day 0.

| Event Name | Payload Shape | When Published |
|---|---|---|
| `task.{id}.step` | `{task_id, step_index, tool_name, tool_input, tool_output, timestamp}` | Every tool call during explore/guided execution |
| `task.{id}.status` | `{task_id, status, finished_at}` | Task status changes (queued→running→succeeded/failed) |
| `rule.changed` | `{rule_key, new_version, impacted: [playbook_ids]}` | Rule change committed (post-txn) |
| `playbook.changed` | `{playbook_id, action: "compiled"\|"invalidated"\|"relearned"}` | Playbook compiled, invalidated, or v2 compiled |
| `metrics.tick` | `{cold: {...}, guided: {...}, retrieval: {...}}` | Metrics updated (after episode write) |
| `approval.requested` | `{approval_id, task_id, step_index, action}` | Extension: autonomy gate triggered |
| `insight.created` | `{insight_id, kind, summary, related_rule_key}` | Extension: new trend detected |

**SSE Endpoint:** `GET /api/events?topics=task.123,rule.changed,metrics.tick`
- Heartbeat every 15s (keeps CloudFront connection alive)
- Client auto-reconnects with Last-Event-ID

---

## 5. ENVIRONMENT VARIABLES & SECRETS

**Owner:** Ashfaq (Track A - manages AWS infra)  
**Contract:** Both API and Lambda use same names

| Variable | Used By | Value / Secret | Notes |
|---|---|---|---|
| `AWS_REGION` | API, Lambda | `us-east-1` | Fixed |
| `DATABASE_URL` | API, Lambda | Secrets Manager `cascade/dsn-app` / `cascade/dsn-worker` | API uses cascade_app role, Lambda uses cascade_worker role |
| `BEDROCK_AGENT_MODEL_ID` | API, Lambda | `anthropic.claude-sonnet-5` | Agent + compiler (if unavailable, use closest Sonnet and record in DEVIATIONS.md) |
| `BEDROCK_FAST_MODEL_ID` | API, Lambda | `anthropic.claude-haiku-4-5` | Precondition / param extraction |
| `BEDROCK_EMBED_MODEL_ID` | API, Lambda | `amazon.titan-embed-text-v2:0` | 1024-d, normalize:true |
| `EPISODES_BUCKET` | API, Lambda | `cascade-episodes-{acct}` | S3 bucket for raw trajectories |
| `CASCADE_QUEUE_URL` | API, Lambda | SQS queue URL | Event queue |
| `ADMIN_TOKEN` | API | Secret `cascade/admin-token` | Guards POST /api/rules/*, reset |
| `INTERNAL_SSE_SECRET` | API, Lambda | Secret `cascade/internal-sse` | Lambda→API bridge auth |
| `API_BASE_URL` | Lambda | `http://{alb-dns}` | For POST /internal/sse |
| `CASCADE_STUB_MODE` | API, Lambda | `true` (default) / `false` | Enables stub responses in contracts.py |

**Local Dev Overrides (.env):**
```
DATABASE_URL=postgresql://root@localhost:26257/cascade?sslmode=disable
CASCADE_STUB_MODE=true
EPISODES_BUCKET=cascade-episodes-local
```


---

## 6. DAY-0 DESIGN DECISIONS (D1-D7)

These decisions are **BINDING**. All code assumes them.

### D1. Staleness is DERIVED, not mass-UPDATEd

**Problem:** Mass-updating playbooks.status on rule changes causes write contention.

**Solution:**
- **Authoritative staleness = a JOIN** (freshness check query)
- `status_cache` is **UI convenience ONLY**, updated async by worker
- Point-of-use freshness check BEFORE every execution (mandatory)
- O(1) cascade transaction: 4 writes (close rule, insert rule, outbox, audit)
- UI shows invalidation "instantly" via SSE + client-side /api/impact query

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D2. playbook_deps PK Includes Version

**Primary Key:** `(playbook_id, rule_key, rule_version)`

**Why:** Playbook v2 depending on rule v2 coexists with playbook v1→rule v1 lineage.

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D3. Two-Phase Vector Retrieval + ONE Distance Metric (L2)

**Metric Decision (BINDING):**
- Titan V2 with `normalize: true` → L2 distance ≡ cosine ranking
- Vector index: L2 opclass (`vector_l2_ops`)
- **ALL queries use `<->` (L2 operator)** - NEVER `<=>` or `<#>`

**Retrieval Phases:**
1. **Phase 1 (vector-only):** `SELECT playbook_id, embedding <-> $1 AS dist FROM playbooks ORDER BY embedding <-> $1 LIMIT 20` - pure ANN
2. **Phase 2 (relational):** `WHERE playbook_id = ANY($ids) AND status_cache IN ('active','candidate','suspect')` - PK lookup + filter
3. **Phase 3 (freshness):** Run point-of-use freshness check on top candidates

**Week 1 Gate:** EXPLAIN must show pb_embed_idx usage. Screen-record via Claude Code + MCP Server.

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D4. Interrupts via In-Process Event Bus + Durable Fallback

**Design:**
- API + executor run in **same FastAPI service** (ECS)
- In-memory `InterruptBus` (dict of task_id→asyncio.Event) - microsecond delivery
- Durable fallback: check `tasks.interrupt_flag` before side-effects + every 10s
- Multi-instance safety: optional SNS→SQS fan-out (implemented, default OFF for demo)

**When Checked:**
- Before `apply_remediation` or `notify_oncall` (side-effecting tools)
- Every 10s otherwise
- Immediately on bus event (if not crashed)

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D5. Outbox Pattern with Immediate Post-Commit Publish

**Pattern:**
1. Rule-change txn inserts ONE outbox row (durable intent)
2. **Post-commit:** best-effort SQS publish (~1s latency)
3. **Sweeper:** EventBridge every 60s re-publishes unprocessed >30s old
4. **Idempotency (D5a):** Worker claims with `UPDATE ... WHERE claimed_at IS NULL OR claimed_at < now() - '5 minutes' RETURNING event_id`

**Job Effects:** All upserts on natural keys (re-learn keyed by `(supersedes, rule_key, rule_version)`)

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D6. MCP Usage is Honest

**Primary Use (MUST DEMO):**
- Dev workflow via Claude Code + Managed MCP Server
- Schema exploration, query plans (EXPLAIN gate), debugging
- Screen-recorded for video
- README has reproduction steps for judges

**Secondary Use (In-App):**
- Ops Copilot panel: read-only SQL synthesis for analytics
- Clearly labeled "Exploratory — verify SQL before acting"
- Shows executed SQL in response

**Impact Analysis:**
- `/api/impact` endpoint: **deterministic SQL**, NOT LLM
- Used by Policy Panel "Impact Preview"

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D7. Domain = SRE Incident Response Runbooks

**Domain:** On-call incident remediation (NOT fintech refunds)

**Incidents:**
- Bad deploys → rollback
- Error spikes → restart
- Resource exhaustion → scale_up

**Policy Rules:**
- `incident.auto_remediate_tier`: min_tier=2 (tier 1 needs manual)
- `incident.rollback_window`: hours=24
- `incident.notify`: on-call notification required
- `incident.single_action`: max 1 automated action

**Mock World:** All in-DB (deterministic demos, no external calls)

**Agreed:** ☐ Ashfaq ☐ Shawki


---

## 7. ADDITIONAL WORK-SPLIT DECISIONS

### D-WS1. Paused Task Status for Approvals

**Options:**
- (a) stays `running`
- (b) new `awaiting_approval` enum value

**Decision:** **(b)** - `awaiting_approval`

**Rationale:** 
- `running` would make partial index `tasks_running_idx` treat paused task as active
- Cascade interrupt logic would target it incorrectly
- Add to `tasks.status` CHECK constraint in Day-0 schema

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS2. Action Risk Tag Source for Autonomy

**Options:**
- (a) new field on Step model
- (b) static map `tool → risk` in confidence.py

**Decision:** **(b)** - static map in confidence.py

**Static Risk Map:**
```python
TOOL_RISK = {
    "apply_remediation": "high",
    "notify_oncall": "low",
    "get_incident": "none",
    "get_rules": "none",
    "check_remediation_eligibility": "none",
}
```

**Rationale:** No schema/compiler change, can't be hallucinated by LLM

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS3. Webhook Ingestion Auth

**Options:**
- (a) open endpoint
- (b) shared-secret header

**Decision:** **(b)** - `X-Webhook-Secret` header

**Rationale:** 
- Uses same Secrets Manager pattern as `X-Internal-Secret`
- Open mutating endpoint on public demo URL is unnecessary risk

**Extension Only:** Not MVP, wire up Week 4+

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS4. Postmortem Storage

**Options:**
- (a) markdown in CRDB column
- (b) S3 + pointer row

**Decision:** **(b)** - S3 + pointer

**Pattern:** Reuses existing `episodes/{id}.json` S3 pattern
- Keeps row sizes small
- Postmortems at `postmortems/{episode_id}.md`
- DB row has `s3_key` + `summary` (one-line teaser)

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS5. Stub Strategy for Parallel Work

**Options:**
- (a) Ashfaq writes own stubs, swaps imports later
- (b) Shawki commits **real files with stub bodies** on Day 0

**Decision:** **(b)** - Shawki commits stub bodies

**Files on Day 0:**
- `core/contracts.py` with `STUB = os.getenv("CASCADE_STUB_MODE", "true").lower() == "true"`
- All functions return realistic data when STUB=true
- Ashfaq builds UI against stubs, Shawki fills bodies
- **NO IMPORT SWAP EVER** - integration = function body gets filled

**Benefit:** Eliminates entire class of merge bugs

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS6. Extension Cut Order (If MVP Slips)

**If Week-3 MVP gate slips >2 days, cut in this order:**

1. ~~Notifications~~ (cut first)
2. ~~Insights~~
3. ~~Postmortems~~
4. ~~Approvals~~
5. ~~Dry-run~~
6. Webhook ingestion (keep - cheapest)

**NEVER CUT (per D8):**
- Point-of-use freshness gate
- Cascade transaction
- Guided vs cold metrics
- Interrupt demo
- Ops Copilot panel
- MCP dev-workflow footage

**Agreed:** ☐ Ashfaq ☐ Shawki

---

### D-WS7. AWS Account Ownership

**Owner:** **Ashfaq** (Track A - owns infra)

**Shawki Access:**
- IAM user with Bedrock access
- S3 read access
- NO deploy rights needed

**Ashfaq Manages:**
- CockroachDB Cloud cluster provisioning
- Bedrock model access request (Day 0 manual step)
- ECS, Lambda, S3, SQS, Secrets Manager
- Billing alarms

**Agreed:** ☐ Ashfaq ☐ Shawki


---

## 8. THE THREE CORE WORKFLOWS (End-to-End)

### Workflow A: LEARN (Cold Run - Explore Mode)

**Input:** Browser submits "Remediate INC-1001"

**Flow:**
1. `POST /api/tasks {"input": "Remediate INC-1001"}` → CloudFront → ALB → FastAPI
2. Task row inserted with `status='queued'`
3. Executor asyncio task starts
4. **Retrieval (§5.5):** Two-phase vector search finds NO candidate
5. **Explore mode:** Claude Sonnet converse loop on Bedrock
   - Injects `get_rules('incident')` output upfront
   - Agent calls: `get_incident` → `check_remediation_eligibility` → `apply_remediation` → `notify_oncall`
   - Every step streamed over SSE (`task.{id}.step`)
   - Deterministic idempotency keys: `{task_id}:{step_index}`
6. `final_answer {"outcome":"success"}` → task `status='succeeded', result='remediated'`
7. Episode written (truncated in CRDB, full JSON to S3: `episodes/{episode_id}.json`)
8. Outbox `compile` event inserted + post-commit SQS publish
9. Lambda worker claims event within ~1s
10. **Compiler (§6):**
    - Load trajectory
    - Claude Sonnet → PlaybookSpec JSON
    - Pydantic validation
    - Dep verification vs trajectory's rules snapshot
    - Safety lint
    - Dedup check (vector search own library)
    - Embed `goal + preconditions` (Titan V2)
    - Single `run_txn`: insert playbooks + playbook_deps + audit
11. Lambda POST `/internal/sse` → `playbook.changed`
12. Runbook card appears in UI Runbook Library

**Metrics:** Episode recorded with `mode='explore'`, latency, steps, tokens

---

### Workflow B: REUSE (Warm Run - Guided Mode)

**Input:** Browser submits "Remediate INC-1002"

**Flow:**
1. `POST /api/tasks {"input": "Remediate INC-1002"}` → task `queued`
2. Executor starts
3. **Retrieval:**
   - Phase 1: Embed task text (Titan V2) → pure ANN query `<->` → 20 candidates
   - Phase 2: PK lookup + filter `status_cache IN ('active','candidate','suspect')`
   - Re-rank by distance, take top 3
4. **Phase 3 - Freshness Check (D1 MANDATORY):**
   ```sql
   SELECT d.rule_key, d.rule_version, r.version AS head
   FROM playbook_deps d JOIN rules r ...
   WHERE d.playbook_id = $1 AND r.version <> d.rule_version
   ```
   - Empty result = fresh → proceed
   - Non-empty = stale → fall back to explore + enqueue `recheck_suspect`
5. **Precondition Check:** Haiku call (200 tokens max)
   - "Task: {...}. Playbook preconditions: {...}. Incident data: {...}. Answer {ok: true/false, failed: [...]}"
   - Not ok → fall back to explore
6. **Param Extraction:** Tiny Haiku call extracts params from task, validates against `spec.params` types
7. **Execute steps directly** (NO per-step LLM):
   - Bind `{params}` to step args
   - Executor injects idempotency keys
   - Side-effecting tools checked for interrupt before execution
8. **Update confidence (§5.7):**
   - Success: `confidence += 0.15` (max 0.99), `successes++`, `uses++`
   - Promote to `active` when `successes >= 3 AND confidence >= 0.6`
9. Episode written with `mode='guided'`
10. SSE `metrics.tick` → metric bar shows cold vs guided delta

**Week 2 Gate:** Guided ≥3× faster than cold. IF NOT, STOP ALL FEATURES.

---

### Workflow C: UNLEARN (Rule Change Cascade)

**Input:** Admin edits `incident.rollback_window` 24→4 hours in Policy Panel

**Flow:**
1. Confirm dialog shows `/api/impact?rule_key=incident.rollback_window` results (deterministic SQL)
2. `POST /api/rules/incident.rollback_window {"body": "...", "params": {"hours": 4}}` with `X-Admin-Token`
3. **Cascade Transaction (§5.8 - 4 writes, O(1)):**
   ```python
   # In run_txn:
   UPDATE rules SET valid_to=now() WHERE rule_key=... AND version=1;
   INSERT INTO rules (rule_key, version=2, body, params, changed_by);
   INSERT INTO outbox (kind='rule_changed', payload={...});
   INSERT INTO audit_log (action='rule.change', entity='rule:incident.rollback_window');
   # Total: 4 writes regardless of fan-out
   ```
4. **Post-commit (microseconds):**
   - Best-effort SQS publish
   - Impact query: `SELECT DISTINCT playbook_id FROM playbook_deps WHERE rule_key=... AND rule_version<2`
   - Running tasks query: `SELECT task_id FROM tasks WHERE status='running' AND playbook_id IN (...)`
   - `InterruptBus.interrupt_many(task_ids, reason="rule ... v1→v2")`
   - SSE broadcast `rule.changed` → UI cards flip red optimistically
5. **Running Executor (D4):**
   - Sees bus event (µs) OR checks `interrupt_flag` before next side-effect
   - Persists scratchpad to `tasks.scratchpad`
   - Re-fetches head rules
   - Re-plan prompt with rule diff
   - Continues as explore with remaining budget
6. **Lambda worker (`rule_changed` job, ~1-5s latency):**
   - Batch 1: Set `status_cache='invalidated'` for playbooks with deps on old version (≤100/txn)
   - Batch 2: Set `status_cache='suspect'` for same-domain actives WITHOUT this rule dep
   - Batch 3: Set `tasks.interrupt_flag=true` for impacted running tasks (durable fallback)
   - Enqueue `relearn` per invalidated playbook
   - Enqueue `recheck_suspect` per suspect playbook
   - Audit rows
   - POST `/internal/sse` → `playbook.changed`
7. **Relearn jobs (async, < 60s total):**
   - Synthesize representative task from old spec
   - Run explore INSIDE Lambda (10 steps / 20k tokens budget)
   - Compile v2 with `supersedes=v1_id`
   - Lineage v1→v2 appears in UI

**Any new task retrieval during this window:**
- Phase 3 freshness check BLOCKS stale playbooks (even if `status_cache` not updated yet)
- Falls back to explore automatically

**Result:** Stale playbook NEVER executes against production (D1 guarantee)


---

## 9. TRACK BOUNDARIES & OWNERSHIP

### Track A: Ashfaq (Shell - API + Frontend + Infra)

**Owns Exclusively:**
- `backend/app/main.py`, `config.py`, `db.py`, `bus.py`
- `backend/app/routers/` (all routers: tasks, rules, playbooks, metrics, admin, copilot)
- `frontend/` (entire Next.js app)
- `infra/` (all scripts, policies, ECS, ALB, CloudFront, Lambda, Amplify)
- `README.md` (Ashfaq drafts, Shawki reviews technical sections)
- `docs/architecture.png`
- Demo video recording/editing (Shawki narrates engine beats)
- Integration tests in `backend/app/tests/integration/`

**NEVER Touches:**
- `core/*` (imports ONLY `core/contracts.py`)
- `worker/*` (calls Lambda, doesn't edit)
- `migrations/*`

**Calls Track B Via:**
```python
from app.core.contracts import (
    retrieve, check_freshness, run_task, change_rule,
    answer_analytics_question,  # Extensions below
    decide_autonomy, resolve_approval, generate_postmortem,
    list_insights, dismiss_insight, simulate_rule_change
)
```

---

### Track B: Shawki (Engine - Core + Worker)

**Owns Exclusively:**
- `core/` (all 11 files: models, contracts, retrieval, freshness, executor, tools, compiler, confidence, cascade, llm, copilot)
- `worker/` (handler.py, jobs.py)
- `migrations/` (001_schema.sql, 002_seed.sql) - FROZEN after Day 0
- `docs/query-plans.md` (Week 1 EXPLAIN gate)
- `docs/skills-review.md` (Agent Skills findings)
- Unit tests in `backend/app/tests/unit/`
- Bedrock fixture recordings for CI

**NEVER Touches:**
- `routers/*`
- `frontend/*`
- `infra/*` (except reviews scripts that use core/)

**Provides Interface:**
- `core/contracts.py` - Track A imports this ONLY
- All functions work in stub mode (`CASCADE_STUB_MODE=true`)
- Stub bodies return realistic data for UI development

---

## 10. CRITICAL GATES & NEVER-CUT LIST

### Week-by-Week Gates

| Week | Joint Gate | If Fails |
|---|---|---|
| **Week 1** | Vector index proven via EXPLAIN; task POSTs end-to-end | Fix index/operator before ANYTHING else |
| **Week 2** | Guided run ≥3× faster (visible metric bar) | **STOP ALL FEATURES** until this works |
| **Week 3** | MVP thin-slice: learn→reuse→unlearn working ugly UI OK | Slipped >2 days → apply D-WS6 cut order |
| **Week 4** | Extensions in; HTTPS live; stranger follows README | Cut remaining extensions, keep deploy |
| **Week 5** | Code freeze Day 2; video, README, submit Aug 16 5pm | Nothing worth missing deadline |

### NEVER-CUT List (D8)

**These features CANNOT be cut under ANY circumstances:**

1. **Point-of-use freshness gate** (D1) - THE staleness guarantee
2. **Cascade transaction** (O(1), 4 writes) - core unlearn demo
3. **Guided vs cold metrics** (visible metric bar) - judges MUST see 3× speedup
4. **Interrupt demo** (rule change mid-task) - shows live cascade
5. **Ops Copilot panel** (SQL synthesis) - shows LLM↔CRDB pairing
6. **MCP dev-workflow footage** (Claude Code + EXPLAIN) - contest requirement

**Rationale:** These 6 features directly map to all 5 judging criteria. Cutting any = disqualification risk.


---

## 11. INTEGRATION CHECKLIST (Week 4)

**Both teammates verify BEFORE submission:**

### Schema & Data
- [ ] All tables from §3 exist in CRDB Cloud cluster
- [ ] Vector index pb_embed_idx exists and is used (EXPLAIN proof in docs/query-plans.md)
- [ ] Seed data (002_seed.sql) runs successfully
- [ ] Reset endpoint restores clean v1 world
- [ ] All 3 SQL roles exist: cascade_app, cascade_worker, cascade_readonly

### Core Flows
- [ ] Learn flow: INC-1001 resolves, playbook compiles, card appears (<90s end-to-end)
- [ ] Reuse flow: INC-1002 uses existing playbook, ≥3× faster
- [ ] Unlearn flow: Rule change invalidates playbook, running task interrupted, v2 compiles
- [ ] Metric bar shows cold vs guided delta in real-time

### Integration Points
- [ ] All `core/contracts.py` functions work with `STUB=false`
- [ ] SSE events flow from executor → frontend (all 7 event types)
- [ ] Lambda worker processes all outbox kinds (compile, rule_changed, relearn, recheck_suspect)
- [ ] Ops Copilot synthesizes + executes read-only SQL
- [ ] Impact preview shows correct affected playbooks

### Infra
- [ ] Frontend on Amplify HTTPS: `https://{app-id}.amplifyapp.com`
- [ ] API via CloudFront HTTPS: `https://{dist}.cloudfront.net`
- [ ] ECS service running with 1 task
- [ ] Lambda triggered by SQS + EventBridge sweeper
- [ ] S3 episodes bucket has trajectory JSON files
- [ ] All secrets in Secrets Manager

### Demo & Presentation
- [ ] README walkable by stranger (setup, run, demo path)
- [ ] Architecture diagram shows all components
- [ ] Video <3min with: pitch (10s), 60% explain, 40% demo, MCP footage, metric bar visible
- [ ] Public repo with MIT license visible in About section
- [ ] Devpost submission ready (description = README "Who this helps" + judging table)

### Extensions (if built)
- [ ] Approval queue blocks/unblocks tasks
- [ ] Postmortem generated and viewable
- [ ] Insights surface with suggested rule changes
- [ ] Dry-run modal previews impact without commit
- [ ] Webhook ingestion creates tasks

---

## 12. EMERGENCY CONTACTS & ESCALATION

**If Day-0 contract dispute:**
1. Document disagreement in comments below
2. Schedule 15min call within 24h
3. Decide or revert to spec default
4. Update contract, both re-sign

**If critical blocker (Bedrock access, CRDB bug, etc):**
- Ashfaq: AWS/CRDB support channels
- Shawki: Implementation workarounds
- Both: Update DEVIATIONS.md with what changed

**If MVP gate slips:**
- Apply D-WS6 cut order IMMEDIATELY
- Never compress Week 5 (hardening + submission)

---

## 13. JUDGING CRITERIA MAPPING

**How this contract addresses each criterion:**

| Criterion | Contract Elements | Success Metrics |
|---|---|---|
| **Agentic Memory Design** | - Provenance-based staleness (D1)<br>- Vector retrieval (D3)<br>- Confidence lifecycle (§5.7)<br>- All memory in CRDB | - Freshness check <5ms<br>- Zero stale executions<br>- Lineage v1→v2 visible |
| **Technical Implementation** | - O(1) cascade txn (D1)<br>- Vector index usage (D3)<br>- Bedrock integration (§5.9)<br>- Outbox pattern (D5) | - EXPLAIN shows index<br>- 4-write cascade<br>- <1s perceived latency |
| **Real-World Impact** | - SRE domain (D7)<br>- Policy governance<br>- Audit trail<br>- README "Who this helps" | - Interrupts prevent stale actions<br>- MTTR reduction story |
| **Production Readiness** | - Retry logic (§5.1)<br>- Circuit breaker (§5.9)<br>- Idempotency (D5a)<br>- Reset endpoint | - Survives ECS restart<br>- Sweeper recovers missed events<br>- Clean demo resets |
| **Creativity & Originality** | - DERIVED staleness (not mass-update)<br>- Honest MCP usage (D6)<br>- Compiler from trajectories (§6) | - Novel provenance approach<br>- Unlearn demo unique |


---

## 14. CONTRACT SIGN-OFF

**By signing, both parties agree:**
1. This contract is BINDING after Day 0
2. Changes require mutual approval via contract PR
3. All decisions (D1-D7, D-WS1-D-WS7) are accepted as-is
4. Schema, signatures, SSE events, and types are FROZEN
5. Track boundaries are respected
6. Gates and never-cut list are mandatory

---

### Ashfaq (Track A - Shell)

**I have read and agree to this Day 0 contract.**

- [ ] Signature: ___________________
- [ ] Date: ___________________

**Notes / Concerns (if any):**

```
[Write any concerns or questions here before signing]
```

---

### Shawki (Track B - Engine)

**I have read and agree to this Day 0 contract.**

- [ ] Signature: ___________________
- [ ] Date: ___________________

**Notes / Concerns (if any):**

```
[Write any concerns or questions here before signing]
```

---

## 15. CONTRACT HISTORY

| Version | Date | Changes | Approved By |
|---|---|---|---|
| 1.0 | 2026-08-01 | Initial Day 0 contract based on CASCADE_BUILD_SPEC v3.1, Cascade_task_split.md v3, and team discussion | Pending |

---

## APPENDIX A: QUICK REFERENCE

### Key File Locations
- **Contract:** `core/contracts.py` (Track A imports this ONLY)
- **Schema:** `migrations/001_schema.sql` (FROZEN)
- **Seed:** `migrations/002_seed.sql` (FROZEN)
- **Models:** `core/models.py` (FROZEN)
- **Decisions:** This file, §6 and §7

### Critical Constants
- **Vector:** 1024-d, L2 metric (`<->`), Titan V2 normalized
- **Budgets:** 15 steps, 60s wall clock, 25k tokens per task
- **Confidence:** New=0.30, promote at ≥0.60 + ≥3 successes, reject at <0.20
- **Thresholds:** L2 dist ≤0.85 for retrieval, <0.40 for dedup
- **Outbox:** 30s delay before sweeper, 5min claim timeout

### Essential Queries
```sql
-- Freshness check (D1)
SELECT d.rule_key, d.rule_version, r.version AS head
FROM playbook_deps d JOIN rules r ON r.rule_key=d.rule_key AND r.valid_to IS NULL
WHERE d.playbook_id=$1 AND r.version<>d.rule_version;

-- Impact analysis
SELECT DISTINCT playbook_id FROM playbook_deps
WHERE rule_key=$1 AND rule_version < $new_version;

-- Metrics
SELECT mode, AVG(latency_ms), AVG(steps) FROM episodes
WHERE outcome='success' GROUP BY mode;
```

### Stub Mode Toggle
```python
# In core/contracts.py
STUB = os.getenv("CASCADE_STUB_MODE", "true").lower() == "true"

# Return realistic stub data when STUB=true
# Ashfaq develops UI against stubs, Shawki fills real implementations
```

---

## APPENDIX B: FAILURE MODES & RECOVERY

| Failure | Detection | Recovery | Owner |
|---|---|---|---|
| Vector index not used | EXPLAIN missing pb_embed_idx | Fix operator/query, re-verify | Shawki |
| Guided not 3× faster | Metric bar Week 2 | Profile, optimize retrieval/precondition | Shawki |
| Cascade txn too slow | Latency >100ms on rule change | Reduce writes, check contention | Shawki |
| SSE events not reaching UI | Network tab empty | Check bus wiring, CloudFront timeout | Ashfaq |
| Lambda not claiming events | Outbox rows unprocessed >60s | Check SQS trigger, sweeper, claim logic | Both |
| Task survives ECS restart? | Manual kill pod test | Verify scratchpad persistence | Shawki |
| Bedrock throttling | Circuit breaker opens | Retry logic, rate limits, backoff | Shawki |
| Demo reset not clean | Stale data after reset | Fix TRUNCATE list in §3.4 | Both |

---

## APPENDIX C: TOOLS & MOCK WORLD

### 5 Tools (All DB-Backed, Deterministic)

| Tool | Inputs | Returns | Side-Effects |
|---|---|---|---|
| `get_incident(incident_id)` | incident_id | Incident + service details | None |
| `get_rules(domain)` | domain | List of head rule versions | None |
| `check_remediation_eligibility(incident_id, action)` | incident_id, action | `{eligible: bool, reasons: [...]}` | None |
| `apply_remediation(incident_id, action, idem_key)` | incident_id, action, idempotency_key | Result or error | INSERT mock_action_log, UPDATE incident state |
| `notify_oncall(incident_id, message, idem_key)` | incident_id, message, idempotency_key | ok | INSERT mock_action_log kind='notify' |

**Idempotency Keys:** Executor supplies `{task_id}:{step_index}` - NEVER invented by LLM

**Escalation:** No separate tool - expressed as `final_answer {"outcome":"escalated"}` + notify_oncall with reason

### Seed Data Scenarios (INC-1001 to INC-1012)

| Incident | Service | Tier | Deploy Age | Kind | Expected Outcome |
|---|---|---|---|---|---|
| INC-1001 | svc-checkout | 2 | 3h | bad_deploy | Rollback (happy path) |
| INC-1002 | svc-search | 3 | 5h | bad_deploy | Rollback |
| INC-1003 | svc-search | 3 | 5h | error_spike | Restart |
| INC-1006 | svc-payments | 1 | 2h | bad_deploy | Escalate (tier blocked) |
| INC-1008 | svc-catalog | 3 | 3 days | bad_deploy | Escalate (window blocked) |
| INC-1011 | svc-emails | 3 | 23h | bad_deploy | Rollback (boundary - allowed) |
| INC-1012 | svc-reports | 3 | 25h | bad_deploy | Escalate (boundary - blocked) |

---

**END OF DAY 0 CONTRACT**

*This contract is complete and ready for sign-off. Both teammates should review all sections, discuss any concerns, sign above, and commit this file to the repository before any implementation work begins.*
