# CASCADE — Build Specification (v3.1, Weakness-Pass + Wiring)

**A procedural memory layer for AI agents that learns skills — and knows when to unlearn them.**

This document is a complete, self-contained build specification. An engineering agent should be able to build, test, deploy, and submit this project by following this file top-to-bottom without asking questions. Where a decision could go two ways, the decision is already made here, with rationale. Do not deviate from this spec unless a step is technically impossible; if so, implement the closest alternative and record the deviation in `DEVIATIONS.md` at repo root.

**What changed in v3 (judging-fit review):** domain pivoted from fintech refunds to **SRE incident-response runbooks** (D7); MCP usage made **visibly demo-critical** (D8); schedule restructured around **de-risk gates** (D8); README/video specs encode Devpost winner presentation patterns (D8).

**What changed in v3.1 (blind-implementer audit — six spec bugs fixed, wiring added):**
1. **HTTPS end-to-end:** CloudFront now fronts the ALB (a bare ALB has no HTTPS without a custom domain; Amplify's HTTPS frontend calling an HTTP API is blocked as mixed content). §2, §2.1, §12.
2. **One vector distance metric everywhere:** Titan V2 embeddings are normalized → L2 ≡ cosine ranking; the index and every query use `<->` (L2). Never mix operators or the planner skips the index. D3, §5.5.
3. **Phase-2 retrieval filter reconciled:** `status_cache IN ('active','candidate','suspect')` is authoritative in both D3 and §5.5 (suspect must be retrievable for edge case #1's recovery path).
4. **Escalation outcome mapped:** `final_answer {"outcome":"escalated"}` is a *policy-compliant success* — task `succeeded` + `result='escalated'`, episode `success`, compile still enqueued. Without this, correct escalations would be punished as failures. §4, §5.4.
5. **Reset restores rules:** `/api/admin/reset` truncates `rules` too (the demo's rule change must not survive a reset). §4.1, §8.
6. **Local vector-index enablement + pinned Bedrock model IDs + Day-0 access checks.** §2, §11, §12.
Plus a new **§2.1 End-to-end connection map**: every wire, port, credential, and the three core request flows.

**Contest:** CockroachDB × AWS Hackathon — "Build with Agentic Memory" (Devpost, deadline Aug 18, 2026, 5:00 PM EDT).
**Hard requirements:** (1) agentic app using CockroachDB as persistent memory, deployed on AWS; (2) use ≥2 CockroachDB tools from {Managed MCP Server, Distributed Vector Indexing, ccloud CLI, Agent Skills Repo}; (3) use ≥1 AWS service; (4) public open-source repo with license visible in the About section (MIT), README, setup instructions; (5) functional public demo URL; (6) public YouTube/Vimeo video < 3 minutes.
**Judging criteria (optimize for all five):** Agentic Memory Design · Technical Implementation · Real-World Impact · Production Readiness · Creativity & Originality.

---

## 0. What Cascade is (one paragraph)

An on-call incident-remediation agent (SRE runbook domain) that: (A) **learns** — resolves novel incidents step-by-step with Claude on Amazon Bedrock and compiles successful trajectories into reusable, parameterized *playbooks* (runbooks) with explicit provenance edges to the *policy rules* they depend on; (B) **reuses** — retrieves playbooks via CockroachDB distributed vector search and executes them 3–5× faster than cold exploration; (C) **unlearns** — when an SRE changes a policy (an approval tier, a rollback window), the system versions the rule in a small O(1) transaction, and staleness of every derived playbook is *derived from provenance*, enforced at point-of-use, surfaced in the UI within ~1 second, and repaired by an async re-learning worker that compiles playbook v2 — so a stale runbook can never execute against production. Everything — rules, playbooks, embeddings, tasks, episodes, audit — lives in one CockroachDB cluster.

---

## 1. Design decisions log (the fixes — READ FIRST)

These eight decisions respond to three rounds of review (technical, judging-fit, blind-implementer audit). They are **binding**. Every module below assumes them.

### D1. Staleness is DERIVED, not mass-UPDATEd (fixes the "giant transaction" bottleneck)

**Old design (rejected):** one SERIALIZABLE transaction that versions the rule AND mass-updates `playbooks.status` AND sets `tasks.interrupt_flag` AND inserts outbox rows. Under CockroachDB's optimistic serializable isolation this creates severe write contention with concurrent workers/executors → storms of `40001` retries.

**New design (binding):**
- The **authoritative definition of staleness is a join, not a column**: a playbook is *stale* iff any row in `playbook_deps` references a `(rule_key, rule_version)` that is no longer the head version of that rule. No rows on `playbooks` need to be touched when a rule changes.
- The synchronous "cascade" transaction is therefore tiny and O(1): close the old rule version, insert the new rule version, insert ONE outbox event, insert ONE audit row. Four writes, no fan-out, near-zero contention.
- `playbooks.status_cache` (a column) is a **UI convenience cache**, maintained asynchronously by the worker in batches of ≤100 rows per transaction. It may lag reality by a few seconds. It is NEVER trusted for correctness.
- **Correctness at point-of-use:** before executing any retrieved playbook, the executor runs a cheap indexed freshness check (`SELECT` join of that playbook's deps against rule head versions — primary-key lookups, single-digit ms). If stale → refuse to execute, fall back to explore mode, and report why. This guarantees a stale playbook is *never executed*, even in the seconds before the cache catches up.
- UI shows invalidation "instantly" anyway: the API's rule-change handler, after commit, pushes a `rule_changed` event over the in-process event bus → SSE → the dashboard optimistically flips dependent cards to red using a client-side query of `/api/impact?rule_key=...` (deterministic SQL, see D6). The async worker then persists `status_cache` truth.

### D2. `playbook_deps` primary key includes the version (fixes the composite-key flaw)

`PRIMARY KEY (playbook_id, rule_key, rule_version)`. A playbook v2 that depends on rule v2 coexists cleanly with playbook v1 → rule v1, enabling the v1→v2 lineage view. Freshness check compares each dep's `rule_version` against the rule's current head version.

### D3. Two-phase vector retrieval + ONE distance metric (fixes vector-index + scalar-filter planner risk)

**Metric decision (binding, v3.1):** Titan Text Embeddings V2 is invoked with `normalize: true` (its default), so all vectors are unit-length and **L2 distance produces the same ranking as cosine**. The vector index is created with its default (L2) opclass, and **every query uses `<->` (L2). Never use `<=>`/`<#>` anywhere** — an operator that doesn't match the index metric silently disables index usage. If the deployed CockroachDB version requires an explicit opclass on `CREATE VECTOR INDEX`, use the L2 one and record it in `docs/query-plans.md` + `DEVIATIONS.md`.

Never combine `ORDER BY embedding <-> $1` with dynamic scalar filters in one query and hope the planner uses the vector index. Instead:
1. **Phase 1 (vector-only):** `SELECT playbook_id, embedding <-> $1 AS dist FROM playbooks ORDER BY embedding <-> $1 LIMIT 20;` — pure ANN query, guaranteed index usage. Verify with `EXPLAIN` during **Week 1** (de-risk gate, D8) and record the plan in `docs/query-plans.md`.
2. **Phase 2 (relational):** `SELECT ... FROM playbooks WHERE playbook_id = ANY($ids) AND status_cache IN ('active','candidate','suspect')` — PK lookups, then re-rank by distance in app code, take top 3. (`suspect` IS retrievable — the executor forces a fresh `get_rules` + precondition pass for it; `rejected` and `invalidated` are excluded.)
3. **Phase 3 (freshness):** for the top candidate(s), run the point-of-use freshness join (D1). Only fresh playbooks proceed to precondition checking.

### D4. Interrupts via in-process event bus + low-frequency durable fallback (fixes DB-spamming interrupt polling)

- The API and the executor run in the **same FastAPI service** (single ECS service, ≥1 task). An in-memory async pub/sub (`InterruptBus`, a dict of `task_id -> asyncio.Event`) delivers rule-change interrupts to running executors in microseconds with zero DB reads.
- Multi-instance safety (ECS may run 2 tasks): the rule-change handler ALSO publishes to an SNS topic; every service instance subscribes via its own SQS queue and re-raises the event on its local bus. (For the hackathon, run desired-count=1 and keep SNS/SQS fan-out as implemented-but-optional; it is ~40 lines.)
- **Durable fallback:** executor checks `tasks.interrupt_flag` in the DB only (a) before any *side-effecting* step (`apply_remediation`, `notify_oncall`), and (b) at most once per 10 seconds otherwise. Worst case without the bus: an interrupt lands before the next side-effect, which is the only place it matters for correctness.
- The interrupt flag itself is set by the **worker** (async, batched), not inside the rule-change transaction.

### D5. Outbox = durable source of truth + immediate post-commit publish + sweeper (fixes 30s latency / missing CDC bridge)

Standard transactional-outbox-with-relay pattern:
- The rule-change txn inserts one `outbox` row (durable intent).
- **Immediately after commit**, the API best-effort publishes the event id to an SQS queue (`cascade-events`). SQS triggers the Lambda worker within ~1 second → re-learning begins with sub-second perceived latency.
- A **sweeper** (EventBridge schedule, every 60s) scans `outbox WHERE processed_at IS NULL AND created_at < now() - '30s'` and re-publishes — catches any missed post-commit publish (process crash between commit and publish). Idempotency (D5a) makes double-delivery harmless.
- **D5a Idempotency:** every worker job claims its outbox row via `UPDATE outbox SET claimed_by=$worker, claimed_at=now() WHERE event_id=$1 AND (claimed_at IS NULL OR claimed_at < now() - INTERVAL '5 minutes') RETURNING event_id;` — zero rows returned ⇒ someone else owns it ⇒ exit. All job effects are upserts keyed on natural keys (e.g., re-learn keyed on `(supersedes_playbook_id, rule_key, rule_version)`).

### D6. MCP is used honestly; impact analysis is deterministic SQL (fixes the "forced MCP" critique)

- The dashboard question "which playbooks break if I change rule X?" is answered by a **plain SQL endpoint** `/api/impact` (join on `playbook_deps`), instant and deterministic. No LLM in this path. The UI's "Impact preview" panel on the rule editor uses it.
- The **CockroachDB Managed MCP Server** is used where an LLM+DB pairing is genuinely appropriate:
  1. **Development & ops workflow (primary, demonstrated in video + README):** the team connects Claude Code to the cluster via the managed MCP config snippet and uses it for schema exploration, query-plan investigation (verifying D3), and debugging — with the read-only default and audit logging. **Screen-capture this workflow starting in Week 1** (it is how the D3 `EXPLAIN` gate is verified), so the video beat exists from day one (D8). The README contains the exact reproduction steps so judges can do the same against the demo cluster with a scoped read-only service account.
  2. **In-app "Ops Copilot" (secondary, clearly labeled *exploratory analytics*):** a chat panel for open-ended analytical questions ("why did rollback playbooks fail more this week?", "summarize the last 20 audit events") where ad-hoc SQL synthesis is the honest use case. Read-only. Every answer footer: "Exploratory — generated SQL shown below; verify before acting," with the executed SQL displayed. **Demo-required and never-cut (D8):** this panel is how a judge *sees* the LLM↔CockroachDB pairing inside the product in a 3-minute skim.
- **Agent Skills Repo** usage: run the schema-design and performance skills against our own cluster during Week 4; commit the findings to `docs/skills-review.md` and cite in the Devpost "feedback" section. **Distributed Vector Indexing** is core (D3). That is 3 of 4 CockroachDB tools, all with defensible roles. `ccloud` CLI is used in `infra/scripts/` for cluster provisioning (bonus, scripted, low effort).

### D7. Domain = incident-response runbooks, NOT fintech refunds (fixes the off-theme / impact weakness)

**Old domain (retired):** refund processing. Architecturally fine, but off-theme — the contest's own framing names "code writing, pipeline operations, and incident diagnostics" as the target production workflows, and a mock refund desk scores weakest on the Real-World-Impact criterion.

**New domain (binding):** an **on-call SRE remediation agent**. The agent resolves incidents (bad deploys, error-rate spikes, resource exhaustion) on mock services by learning remediation runbooks; versioned *policy rules* (auto-remediation approval tier, rollback window, notification duty, single-action limit) govern what it may do autonomously.

Why this wins on every axis it touches:
- **On-theme:** hits the judges' own vocabulary ("incident diagnostics", "pipeline operations") instead of adjacent fintech.
- **Impact story:** "a stale runbook executed against production infrastructure" is viscerally dangerous in a way a late refund is not — the unlearn hook lands harder. The README frames impact as on-call toil / MTTR reduction with auditable, policy-governed agent memory.
- **Zero architectural cost:** this is a pure reskin — same tables shape, same 5-tool mock world, same rules→playbooks→provenance→unlearn loop. Nothing in D1–D6 changes.

Everything below is specified in the incident domain. Do not reintroduce refund terminology anywhere in code, UI, or docs.

### D8. Demo-first de-risking + winner presentation patterns (fixes the scope/finishing risk)

The biggest opponent is not another team — it is not finishing, or finishing with a flaky demo. These are binding schedule and presentation rules:

1. **EXPLAIN gate moves to Week 1.** The vector-index query plan (D3) is verified and pasted into `docs/query-plans.md` in Week 1, before any dependent work. If the index is unused, fixing it becomes the only Week-1 priority. Verify it *through Claude Code connected via the Managed MCP Server* and screen-record it — one action, two deliverables (proof + video footage).
2. **Thin-slice gate at end of Week 3.** The full demo path — learn (cold run) → reuse (guided run, visible metric delta) → unlearn (rule change interrupts a task, invalidates playbooks, v2 compiles) — must work end-to-end, ugly UI acceptable. Weeks 4–5 are polish and presentation only. If the gate slips, cut immediately per the §14 scope-cut order; never compress Weeks 4–5.
3. **Fallback footage weekly.** At the end of every week, screen-record the current working state. Demo-day risk drops monotonically; the video can be assembled from real footage even if the live demo misbehaves.
4. **Video follows winner patterns (§15):** elevator pitch in the first 10 seconds; ~60% explain / 40% raw demo; unhurried voice; the metric bar (cold-vs-guided delta) visible on screen throughout the demo segments; MCP and Ops Copilot each get an explicit on-screen beat.
5. **Impact narrative is a first-class deliverable.** The README carries a "Who this helps" section (§13) and a judging-criteria map table; both are pasted into the Devpost description. Engineering depth must not crowd out the impact story — the writeup answers "so what?" before "how".
6. **Never-cut list is extended:** point-of-use freshness gate, cascade txn, guided-vs-cold metrics, interrupt demo, **Ops Copilot panel, MCP dev-workflow footage**.

---

## 2. Tech stack (fixed versions where it matters)

| Layer | Choice | Notes |
|---|---|---|
| Database | CockroachDB Cloud (free tier), v26.x | One database `cascade`; vector index enabled (verify Day 0, §12) |
| Backend | Python 3.12, FastAPI, uvicorn, `psycopg[binary,pool]` 3.x, Pydantic v2 | Single service: API + executor |
| LLM | Amazon Bedrock via the **`AnthropicBedrockMantle` client** (`pip install "anthropic[bedrock]"`), region `us-east-1`. Pinned model IDs: agent + compiler `anthropic.claude-sonnet-5`; precondition/param-extraction/recheck calls `anthropic.claude-haiku-4-5`. Embeddings: `amazon.titan-embed-text-v2:0` (1024-d, `normalize: true`) via `boto3` `bedrock-runtime`. | If a pinned ID is unavailable in the account/region on Day 0, substitute the closest available Claude Sonnet/Haiku ID and record it in `DEVIATIONS.md`. **Bedrock model access must be manually enabled in the AWS console (Day-0 step, §12) — a missing grant fails with `AccessDeniedException`.** |
| Worker | AWS Lambda (Python 3.12), SQS trigger + EventBridge 60s sweeper | Shares `core/` code via vendored copy |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind, `shadcn/ui`, SSE via `EventSource` | Deployed on AWS Amplify Hosting |
| Object storage | S3 — raw trajectory JSON archives | Key: `episodes/{episode_id}.json` |
| Secrets | AWS Secrets Manager | DB DSNs, admin token, internal shared secret |
| Compute | ECS Fargate (1 task, 0.5 vCPU / 1 GB) behind an ALB, **fronted by CloudFront for HTTPS** | A bare ALB has no HTTPS (`*.elb.amazonaws.com` cannot carry an ACM cert); Amplify serves the frontend over HTTPS, and browsers block HTTPS→HTTP API calls as mixed content. CloudFront (`https://<dist>.cloudfront.net`) → ALB (HTTP origin) closes the gap with zero domains to buy. §2.1 has the wiring. |
| IaC / scripts | Plain bash scripts + `ccloud` CLI in `infra/`; optional Terraform NOT required | Keep infra simple and reproducible |
| License | MIT, `LICENSE` at root, set in GitHub About | Contest requirement |

**Local dev:** `docker run cockroachdb/cockroach:latest start-single-node --insecure` + `.env` pointing at it. All migrations/seeds must run identically against local and Cloud. **If `CREATE VECTOR INDEX` errors with a feature-disabled message on the local node, `02_migrate.sh` runs `SET CLUSTER SETTING feature.vector_index.enabled = true;` first (guarded: ignore the error on Cloud, where the setting is managed).**

### 2.1 End-to-end connection map (wiring — every edge, port, and credential)

#### 2.1.1 Topology

```
                    (HTTPS 443)                (HTTPS 443)
  Browser ────────► AWS Amplify Hosting        Browser ────────► CloudFront (https://<dist>.cloudfront.net)
                    (static Next.js build)                          │  /api/* behavior: caching disabled,
                                                                    │  forward all headers/query, origin
                                                                    │  read timeout 60s (SSE heartbeats
                                                                    │  every 15s keep the pipe alive)
                                                                    ▼  (HTTP 80)
                                                                  ALB ──► ECS Fargate task :8000
                                                                          FastAPI = API + executor + InterruptBus + SSE
                                                                    │
              ┌────────────────────────────┬────────────────────────┼───────────────────────┐
              ▼ (pg wire TLS :26257)       ▼ (HTTPS, IAM role)      ▼ (HTTPS, IAM role)     ▼ (HTTPS, IAM role)
       CockroachDB Cloud             Amazon Bedrock            S3 (episodes/…)         SQS cascade-events ──► Lambda worker
       cluster `cascade`             (Claude Sonnet/Haiku      raw trajectories             ▲                    │
       rules/playbooks/deps/          via Mantle client;                                    │ re-publish         │
       tasks/episodes/outbox/         Titan V2 embeddings)                     EventBridge (rate 1 min) ─────────┤ sweeper event
       audit/mock world                                                                                          │
              ▲                                                                                                  │
              │ (pg wire TLS, worker DSN)  (HTTPS, IAM)  (HTTP to ALB DNS + X-Internal-Secret)                   │
              └───────────────────────────── Lambda ──► Bedrock / S3;  POST /internal/sse ◄──────────────────────┘

  Claude Code ──(Managed MCP config snippet)──► CockroachDB Managed MCP Server ──► cluster (readonly service account)
  ccloud CLI  ──(service account)──► CockroachDB Cloud API (provisioning, §12 step 1)
  GitHub push ──► Amplify build (frontend)  /  GitHub Actions ──► local single-node CRDB (docker run step, §11)
```

#### 2.1.2 Connection table (who talks to whom, how, authenticated by what)

| # | From → To | Protocol / port | Auth / credential | Config source |
|---|---|---|---|---|
| 1 | Browser → Amplify | HTTPS 443 | public | — |
| 2 | Browser → CloudFront → ALB → FastAPI | HTTPS 443 → HTTP 80 → 8000 | public read; mutations require `X-Admin-Token` header | Frontend `NEXT_PUBLIC_API_URL=https://<dist>.cloudfront.net`. CloudFront: default behavior → ALB origin; `/api/*` uses the managed `CachingDisabled` cache policy + `AllViewerExceptHostHeader` origin-request policy; origin response timeout 60s (SSE stays alive because heartbeats every 15s < timeout) |
| 3 | FastAPI → CockroachDB Cloud | pg wire, TLS 26257, `sslmode=verify-full` | SQL user `cascade_app` | Secret `cascade/dsn-app` → env `DATABASE_URL` (local `.env` overrides) |
| 4 | FastAPI → Bedrock runtime | HTTPS | ECS task IAM role (`bedrock:InvokeModel*`) | `AnthropicBedrockMantle(aws_region=AWS_REGION)`; model IDs from env (§2.1.3) |
| 5 | FastAPI → S3 / SQS / (opt) SNS | HTTPS | task IAM role (`s3:PutObject` on bucket, `sqs:SendMessage`, `sns:Publish`) | `EPISODES_BUCKET`, `CASCADE_QUEUE_URL`, `SNS_BUS_TOPIC_ARN` |
| 6 | SQS → Lambda | event source mapping, batch size 1 | AWS-managed | `03_aws_bootstrap.sh` |
| 7 | EventBridge → Lambda | scheduled event `rate(1 minute)`, payload `{"sweep": true}` | AWS-managed | `03_aws_bootstrap.sh` |
| 8 | Lambda → CockroachDB Cloud | pg wire, TLS 26257 | SQL user `cascade_worker` | Secret `cascade/dsn-worker` → Lambda env `DATABASE_URL` |
| 9 | Lambda → Bedrock / S3 / SQS | HTTPS | Lambda execution role (`bedrock:InvokeModel*`, `s3:GetObject/PutObject`, `sqs:SendMessage` for sweeper re-publish) | same env names as API |
| 10 | Lambda → FastAPI `/internal/sse` | HTTP 80 to ALB DNS (not via CloudFront) | header `X-Internal-Secret` (shared secret; endpoint rejects otherwise) | Lambda env `API_BASE_URL=http://<alb-dns>`, secret `cascade/internal-sse` |
| 11 | Ops Copilot SQL execution | in-process → CRDB | SQL user `cascade_readonly` (SELECT-only; role default `statement_timeout='3s'`) | Secret `cascade/dsn-readonly` |
| 12 | Claude Code → Managed MCP Server → cluster | MCP (managed config snippet from Cloud Console) | readonly service account (scoped for judges) | §12 step 1; README reproduction steps |
| 13 | `ccloud` CLI → CockroachDB Cloud API | HTTPS | ccloud service account | `01_ccloud_provision.sh` |

#### 2.1.3 Environment & secrets matrix

| Name | Used by | Value / secret | Notes |
|---|---|---|---|
| `AWS_REGION` | API, Lambda | `us-east-1` | |
| `DATABASE_URL` | API / Lambda | secrets `cascade/dsn-app` / `cascade/dsn-worker` | local dev: `.env` → `postgresql://root@localhost:26257/cascade?sslmode=disable` |
| `BEDROCK_AGENT_MODEL_ID` | API, Lambda | `anthropic.claude-sonnet-5` | agent + compiler |
| `BEDROCK_FAST_MODEL_ID` | API, Lambda | `anthropic.claude-haiku-4-5` | precondition / param extraction / recheck_suspect |
| `BEDROCK_EMBED_MODEL_ID` | API, Lambda | `amazon.titan-embed-text-v2:0` | 1024-d, `normalize: true` |
| `EPISODES_BUCKET` | API, Lambda | `cascade-episodes-<acct>` | |
| `CASCADE_QUEUE_URL` | API, Lambda | SQS `cascade-events` URL | |
| `ADMIN_TOKEN` | API | secret `cascade/admin-token` | guards `POST /api/rules/*`, reset |
| `INTERNAL_SSE_SECRET` | API, Lambda | secret `cascade/internal-sse` | Lambda→API bridge |
| `API_BASE_URL` | Lambda | `http://<alb-dns>` | for `/internal/sse` POST |
| `ENABLE_SNS_FANOUT` / `SNS_BUS_TOPIC_ARN` | API | `false` / topic ARN | multi-instance bus fan-out, off for demo (D4) |
| `NEXT_PUBLIC_API_URL` | Frontend (Amplify build env) | `https://<dist>.cloudfront.net` | never the raw ALB URL (mixed content) |
| `X-Admin-Token` | Browser → API | entered via UI "admin unlock" | stored in sessionStorage |

#### 2.1.4 The three core flows, end to end

**Flow A — Learn (cold run).** Browser submits `Remediate INC-1001` → `POST /api/tasks` (CloudFront→ALB→FastAPI) → task row `queued` → executor asyncio task starts → retrieval (§5.5) finds no candidate → **explore mode**: Bedrock converse loop (Claude Sonnet) calling `get_rules` → `get_incident` → `check_remediation_eligibility` → `apply_remediation` → `notify_oncall`, every step streamed to the browser over SSE (`task.{id}.step`) and appended to the trajectory → `final_answer {"outcome":"success"}` → task `succeeded`, episode row written (truncated copy in CRDB, raw JSON to S3) → outbox `compile` row + post-commit SQS publish → Lambda claims the event, runs the compiler pipeline (§6): Claude Sonnet emits PlaybookSpec JSON → Pydantic parse → dep verification vs the trajectory's rules snapshot → safety lint → Titan embeds `goal+preconditions` → one `run_txn` inserts `playbooks` + `playbook_deps` + audit → Lambda POSTs `/internal/sse` → `playbook.changed` → the runbook card appears in the library.

**Flow B — Reuse (guided run).** `POST /api/tasks {"input":"Remediate INC-1002"}` → embed task text (Titan) → Phase 1 ANN `<->` (vector index) → Phase 2 PK-lookup metadata filter → Phase 3 **point-of-use freshness join** (D1) → precondition check (Haiku, one capped call) → params bound via a tiny extraction call validated against `spec.params` → steps executed directly (no per-step LLM), side-effecting tools carry deterministic idempotency keys → counters + confidence updated in `run_txn` → episode `mode='guided'` → metric bar shows the cold-vs-guided delta via `/api/metrics` + `metrics.tick`.

**Flow C — Unlearn (rule change cascade).** Admin edits `incident.rollback_window` 24→4 in the Policy Panel (confirm dialog shows `/api/impact` results) → `POST /api/rules/{key}` → §5.8 txn: close v1, insert v2, ONE outbox `rule_changed` row, ONE audit row (4 writes, O(1)) → post-commit: best-effort SQS publish; impact query → `InterruptBus.interrupt_many` for running tasks on impacted playbooks; SSE `rule.changed` → cards flip red optimistically. Running executor sees the bus event (µs) or the durable flag before its next side-effect (D4) → persists scratchpad → re-plans under v2 rules (§6.3-C). Meanwhile any new retrieval is blocked at Phase 3 regardless of `status_cache` lag (edge case #19). Lambda `rule_changed` job (≤100 rows/txn): `status_cache='invalidated'` for dep-holders, `'suspect'` + `recheck_suspect` for same-domain actives without the edge, durable interrupt flags, one `relearn` per invalidated playbook, audit rows, `/internal/sse` → `playbook.changed`. `relearn` synthesizes a representative task, runs explore inside Lambda, compiles v2 with `supersedes` → lineage v1→v2 appears in the library, typically < 60s.

**Local dev wiring:** everything collapses to `docker compose` — FastAPI on :8000 talked to directly by `next dev` on :3000 (`NEXT_PUBLIC_API_URL=http://localhost:8000`), local CRDB on :26257, Bedrock still remote (AWS creds in `.env`), worker jobs runnable inline via `python -m worker.handler --once` (no SQS/Lambda needed; the sweeper is a manual invocation). `make seed` = migrations + seed.

---

## 3. Repository layout (create exactly this)

```
cascade/
├── LICENSE                      # MIT
├── README.md                    # per §13
├── DEVIATIONS.md                # any spec deviations, else "None."
├── docs/
│   ├── architecture.png         # per §13 diagram spec
│   ├── query-plans.md           # EXPLAIN output proving vector index usage (D3, Week 1)
│   └── skills-review.md         # Agent Skills repo findings (D6)
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI app factory, routers, SSE, lifespan
│   │   ├── config.py            # env parsing (pydantic-settings) per §2.1.3
│   │   ├── db.py                # pool, run_txn() retry wrapper (§5.1)
│   │   ├── bus.py               # InterruptBus + SSEBroadcaster (§5.2)
│   │   ├── routers/
│   │   │   ├── tasks.py         # POST /api/tasks, GET /api/tasks/{id}, SSE stream
│   │   │   ├── rules.py         # GET/POST rules, GET /api/impact
│   │   │   ├── playbooks.py     # list, detail, lineage, manual re-learn
│   │   │   ├── metrics.py       # GET /api/metrics
│   │   │   ├── admin.py         # POST /api/admin/reset (demo mode)
│   │   │   └── copilot.py       # Ops Copilot (read-only SQL synthesis) (§8.1)
│   │   ├── core/
│   │   │   ├── models.py        # Pydantic: PlaybookSpec, Step, Trajectory... (§6.1)
│   │   │   ├── retrieval.py     # two-phase vector retrieval (D3) (§5.5)
│   │   │   ├── freshness.py     # point-of-use dep check (D1) (§5.6)
│   │   │   ├── executor.py      # explore + guided loops, interrupts (§5.4)
│   │   │   ├── tools.py         # mock world tools (§5.3)
│   │   │   ├── compiler.py      # trajectory → playbook + deps (§6)
│   │   │   ├── confidence.py    # lifecycle math (§5.7)
│   │   │   ├── cascade.py       # small rule-change txn + post-commit publish (§5.8)
│   │   │   └── llm.py           # Bedrock clients, retries, budgets (§5.9)
│   │   └── tests/               # pytest, per §11
│   ├── worker/
│   │   ├── handler.py           # Lambda entry: SQS event / sweeper event / --once local mode
│   │   └── jobs.py              # status_cache refresh, interrupts, relearn, recheck (§7)
│   └── migrations/
│       ├── 001_schema.sql
│       └── 002_seed.sql
├── frontend/                    # Next.js app (§9)
│   └── ...
└── infra/
    ├── scripts/
    │   ├── 01_ccloud_provision.sh   # ccloud CLI: cluster + SQL users + connection strings
    │   ├── 02_migrate.sh            # psql runner for migrations (+ local vector-index setting)
    │   ├── 03_aws_bootstrap.sh      # SQS, SNS, S3, Secrets, ECR, ECS, ALB, CloudFront, Lambda, EventBridge
    │   ├── 04_deploy_backend.sh     # build+push image, update service
    │   └── 05_deploy_worker.sh      # zip+update Lambda
    └── policies/                    # least-privilege IAM JSON docs
```

---

## 4. Database schema — `migrations/001_schema.sql` (authoritative DDL)

Run against database `cascade`. All timestamps UTC. Every statement below is final.

```sql
-- ========== SEMANTIC MEMORY: versioned policy rules ==========
CREATE TABLE rules (
  rule_key    STRING NOT NULL,                  -- stable identity, e.g. 'incident.rollback_window'
  version     INT    NOT NULL,
  domain      STRING NOT NULL,                  -- 'incidents' (single domain for MVP; 'deploys' stretch)
  body        STRING NOT NULL,                  -- rule text injected into agent context
  params      JSONB  NOT NULL DEFAULT '{}',     -- machine-readable, e.g. {"hours": 24}
  valid_from  TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to    TIMESTAMPTZ,                      -- NULL = head version
  changed_by  STRING NOT NULL DEFAULT 'system',
  PRIMARY KEY (rule_key, version)
);
-- Fast head lookup (freshness checks are the hottest read path):
CREATE INDEX rules_head_idx ON rules (rule_key) STORING (version, domain, params) WHERE valid_to IS NULL;

-- ========== PROCEDURAL MEMORY: playbooks (learned runbooks) ==========
CREATE TABLE playbooks (
  playbook_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            STRING NOT NULL,
  domain          STRING NOT NULL,
  version         INT NOT NULL DEFAULT 1,
  supersedes      UUID,                          -- previous playbook version (lineage)
  -- status_cache is a UI CACHE ONLY (D1). Authoritative staleness = freshness join.
  status_cache    STRING NOT NULL DEFAULT 'candidate'
      CHECK (status_cache IN ('candidate','active','suspect','invalidated','rejected')),
  invalid_reason  STRING,
  spec            JSONB NOT NULL,                -- validated PlaybookSpec (§6.1)
  embedding       VECTOR(1024),                  -- L2 metric everywhere (D3); Titan V2 normalized
  embedding_model STRING NOT NULL DEFAULT 'amazon.titan-embed-text-v2:0',
  confidence      FLOAT NOT NULL DEFAULT 0.30,
  uses INT NOT NULL DEFAULT 0,
  successes INT NOT NULL DEFAULT 0,
  failures  INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE VECTOR INDEX pb_embed_idx ON playbooks (embedding);
CREATE INDEX pb_status_idx ON playbooks (status_cache, domain);

-- ========== PROVENANCE: playbook -> rule-version edges (D2) ==========
CREATE TABLE playbook_deps (
  playbook_id  UUID NOT NULL REFERENCES playbooks (playbook_id) ON DELETE CASCADE,
  rule_key     STRING NOT NULL,
  rule_version INT NOT NULL,
  citation     STRING,                           -- 'step 2: eligibility gate'
  extraction_confidence FLOAT NOT NULL DEFAULT 0.5,
  PRIMARY KEY (playbook_id, rule_key, rule_version),
  CONSTRAINT fk_rule FOREIGN KEY (rule_key, rule_version) REFERENCES rules (rule_key, version)
);
CREATE INDEX deps_by_rule_idx ON playbook_deps (rule_key, rule_version) STORING (playbook_id);

-- ========== WORKING MEMORY: tasks ==========
CREATE TABLE tasks (
  task_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  input       STRING NOT NULL,
  status      STRING NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued','running','interrupted','succeeded','failed')),
  -- v3.1: escalation is a policy-compliant SUCCESS; result records which kind.
  result      STRING CHECK (result IN ('remediated','escalated')),
  mode        STRING CHECK (mode IN ('explore','guided')),
  playbook_id UUID REFERENCES playbooks (playbook_id),
  interrupt_flag   BOOL NOT NULL DEFAULT false,  -- durable fallback (D4)
  interrupt_reason STRING,
  scratchpad  JSONB NOT NULL DEFAULT '{}',       -- survives restarts/interrupts
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX tasks_running_idx ON tasks (status) WHERE status = 'running';

-- ========== EPISODIC MEMORY ==========
CREATE TABLE episodes (
  episode_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     UUID NOT NULL REFERENCES tasks (task_id),
  trajectory  JSONB NOT NULL,                    -- full step log (truncated copy; raw in S3)
  outcome     STRING NOT NULL CHECK (outcome IN ('success','failure','interrupted')),
  steps INT NOT NULL, latency_ms INT NOT NULL, tokens INT NOT NULL,
  s3_key      STRING,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ========== OUTBOX (D5) ==========
CREATE TABLE outbox (
  event_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind       STRING NOT NULL CHECK (kind IN ('rule_changed','compile','relearn','recheck_suspect','compile_failed')),
  payload    JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_by STRING, claimed_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ, error STRING
);
CREATE INDEX outbox_pending_idx ON outbox (created_at) WHERE processed_at IS NULL;

-- ========== AUDIT (append-only; app role gets INSERT/SELECT only) ==========
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor  STRING NOT NULL,
  action STRING NOT NULL,       -- 'rule.change','playbook.invalidate','task.interrupt',...
  entity STRING NOT NULL,       -- 'rule:incident.rollback_window','playbook:<uuid>'
  detail JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_at_idx ON audit_log (at DESC);

-- ========== MOCK WORLD (the agent's environment lives in-DB: deterministic demos) ==========
CREATE TABLE mock_services (
  service_id     STRING PRIMARY KEY,             -- 'svc-checkout'
  name           STRING NOT NULL,
  tier           INT NOT NULL,                   -- 1 = most critical
  last_deploy_at TIMESTAMPTZ NOT NULL,
  state          STRING NOT NULL DEFAULT 'healthy'
      CHECK (state IN ('healthy','degraded','down'))
);
CREATE TABLE mock_incidents (
  incident_id STRING PRIMARY KEY,                -- 'INC-1001'
  service_id  STRING NOT NULL REFERENCES mock_services (service_id),
  kind        STRING NOT NULL
      CHECK (kind IN ('bad_deploy','high_error_rate','high_cpu','memory_leak','disk_full')),
  severity    INT NOT NULL,                      -- 1 (critical) .. 4 (low)
  opened_at   TIMESTAMPTZ NOT NULL,
  state       STRING NOT NULL DEFAULT 'open'
      CHECK (state IN ('open','remediated','escalated','resolved'))
);
CREATE TABLE mock_action_log (
  entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id STRING NOT NULL REFERENCES mock_incidents (incident_id),
  kind   STRING NOT NULL CHECK (kind IN ('remediation','notify','escalate')),
  action STRING,                                 -- 'restart' | 'rollback' | 'scale_up' for remediations
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  idempotency_key STRING UNIQUE                  -- side effects are exactly-once (remediation AND notify)
);
```

**Grants:** create SQL users `cascade_app` (full DML on all tables EXCEPT `audit_log` gets INSERT/SELECT only, no UPDATE/DELETE), `cascade_worker` (same), and `cascade_readonly` (SELECT on everything — used by the MCP server service account and the Ops Copilot; additionally `ALTER ROLE cascade_readonly SET statement_timeout = '3s';` so runaway Copilot/judge queries self-terminate).

### 4.1 Seed data — `migrations/002_seed.sql`

- **Rules (head versions, v1):**
  - `incident.auto_remediate_tier` / incidents / "Automated remediation (restart, rollback, scale_up) is permitted only for services of tier {min_tier} or a higher tier number (tier 1 = most critical). For more critical services, escalate to a human with reason 'manual_approval'." / `{"min_tier": 2}`
  - `incident.rollback_window` / incidents / "Automatic rollback is permitted only within {hours} hours of the service's last deploy; older deploys require a human decision (escalate with reason 'stale_deploy')." / `{"hours": 24}`
  - `incident.notify` / incidents / "The on-call channel must be notified after any remediation decision (action taken or escalation)." / `{}`
  - `incident.single_action` / incidents / "At most one automated remediation action may be applied to an incident." / `{}`
  - (stretch, seed but unused by MVP tools) `deploy.freeze` / deploys / "While a change freeze is active, no automated rollbacks or deploys are permitted." / `{"active": false}`
- **Services:** 6 rows spanning tiers — `svc-payments` (tier 1, deploy 2h ago), `svc-checkout` (tier 2, deploy 3h ago — exactly at the `min_tier` boundary, allowed), `svc-search` (tier 3, deploy 5h ago), `svc-catalog` (tier 3, deploy 3 days ago), `svc-emails` (tier 3, deploy 23h ago — inside window boundary), `svc-reports` (tier 3, deploy 25h ago — outside window boundary). All `last_deploy_at` computed relative to `now()` in the seed script (use `now() - INTERVAL 'X hours'`).
- **Incidents:** 12 rows spanning the decision space, fixed IDs `INC-1001..INC-1012` — ~5 happy path (`INC-1001` bad_deploy on svc-checkout → rollback eligible; `INC-1002` bad_deploy on svc-search; `INC-1003` high_error_rate on svc-search → restart; `INC-1004` high_cpu on svc-catalog → restart; `INC-1005` memory_leak on svc-emails → restart), 2 tier-blocked (`INC-1006`, `INC-1007` on svc-payments, tier 1 → must escalate), 2 outside the 24h rollback window (`INC-1008`, `INC-1009` bad_deploy on svc-catalog), 1 already `remediated` (`INC-1010` → single-action denial), 2 boundary (`INC-1011` bad_deploy on svc-emails, deploy at 23h → allowed; `INC-1012` bad_deploy on svc-reports, deploy at 25h → blocked).
- Seed is **idempotent** and **includes `rules`** (v3.1): one statement `TRUNCATE tasks, episodes, playbook_deps, playbooks, outbox, mock_action_log, mock_incidents, mock_services, rules CASCADE;` (audit_log deliberately NOT truncated — append-only history survives resets), then insert rules v1 + services + incidents. `POST /api/admin/reset` re-runs it (§8.2), so the demo's rule change (v2) is rolled back to a clean v1 world every time.

---

## 5. Backend core — module-by-module specification

### 5.1 `db.py` — connection + the ONLY way to write

- `psycopg_pool.AsyncConnectionPool`, min 2 / max 10, DSN from Secrets Manager (env override `DATABASE_URL` for local).
- `async def run_txn(fn, *, max_retries=6)`: opens txn, calls `await fn(cur)`, commits. On `SerializationFailure` (SQLSTATE `40001`): rollback, sleep `random.uniform(0, 0.05 * 2**attempt)`, retry. After max retries raise `RetryExhausted`. **Every multi-statement write in the codebase goes through `run_txn`. No exceptions.**
- `async def q(sql, params)` for single-statement reads (autocommit).

### 5.2 `bus.py` — in-process events (D4) + SSE

```python
class InterruptBus:
    def __init__(self): self._events: dict[str, asyncio.Event] = {}
    def register(self, task_id) -> asyncio.Event: ...
    def interrupt(self, task_id, reason): ...       # set event + stash reason
    def interrupt_many(self, task_ids, reason): ...
    def unregister(self, task_id): ...

class SSEBroadcaster:
    # topic-based fan-out to connected dashboards
    async def publish(self, topic: str, data: dict): ...
    def subscribe(self, topics: list[str]) -> AsyncIterator[dict]: ...
```
SSE topics: `task.{id}.step`, `task.{id}.status`, `rule.changed`, `playbook.changed`, `metrics.tick`. The frontend opens ONE `EventSource` to `GET /api/events?topics=...`.

Multi-instance note (implement, default off via `ENABLE_SNS_FANOUT=false`): on `interrupt/publish`, also publish JSON to SNS topic `cascade-bus`; a background task per instance long-polls its own SQS subscription queue and replays onto the local bus. Run ECS desired-count=1 for the demo.

### 5.3 `tools.py` — the mock world (5 tools, all DB-backed, all deterministic)

Each tool: name, JSON schema for Bedrock tool-use, and an async impl.

| Tool | Behavior |
|---|---|
| `get_incident(incident_id)` | SELECT from `mock_incidents` joined with its service (tier, `last_deploy_at`, state); not found → structured error `{"error":"incident_not_found"}` (never raise) |
| `get_rules(domain)` | SELECT head versions (`valid_to IS NULL`) for domain; returns list of `{rule_key, version, body, params}` — **the agent must cite versions from here** |
| `check_remediation_eligibility(incident_id, action)` | Pure computation against head rules: tier check, rollback-window check (when `action='rollback'`), single-action check; returns `{eligible: bool, reasons: [...], rule_versions_used: {...}}` |
| `apply_remediation(incident_id, action, idempotency_key)` | Txn: verify incident is `open`, insert `mock_action_log`, update `mock_incidents.state='remediated'` (+ service `state='healthy'`). Duplicate idempotency_key → return the prior result (exactly-once). Ineligible per current head rules → `{"error":"blocked_by_rule", "rule": ...}` — **tools re-verify rules themselves; the LLM can never bypass policy** |
| `notify_oncall(incident_id, message, idempotency_key)` | Insert `mock_action_log` kind='notify'; duplicate idempotency_key → prior result (v3.1: notifications are exactly-once too, so interrupt/resume never double-notifies); returns ok |

`apply_remediation` and `notify_oncall` are **side-effecting** (durable interrupt check applies, D4). **The executor supplies deterministic idempotency keys** — `"{task_id}:{step_index}"` — for every side-effecting call in both explore and guided modes; the LLM never invents keys. Escalation is expressed as an outcome (`final_answer` with `"outcome": "escalated"`) plus a `notify_oncall` message stating the reason — no separate tool. All tool calls append to the trajectory with args, result, latency.

### 5.4 `executor.py` — the agent loops

**Shared plumbing:** budgets — max 15 steps, 60s wall clock, 25k tokens per task (fail with reason on breach; the failed episode is still recorded). Every step: (1) check local `InterruptBus` event (non-blocking); (2) if step's tool is side-effecting OR >10s since last durable check → `SELECT interrupt_flag, interrupt_reason FROM tasks WHERE task_id=$1`; (3) on interrupt → persist scratchpad, set task `interrupted`, SSE `task.status`, then **resume**: re-fetch head rules, ask the model to re-plan from the scratchpad ("rules changed: {diff}; here is progress so far; continue or restart safely"), continue as explore mode, cap total steps at 15 including pre-interrupt steps + 5 grace.

**Outcome mapping (binding, v3.1):** `final_answer {"outcome":"success"}` → task `status='succeeded', result='remediated'`. `final_answer {"outcome":"escalated"}` → task `status='succeeded', result='escalated'` — escalating when policy demands it is *correct behavior*, episode `outcome='success'`, and the compile event IS enqueued (an "escalate tier-1 incidents" runbook is a legitimate, learnable skill). Only budget breaches, tool-level dead ends, and unhandled errors produce `status='failed'` / episode `failure`.

**Explore mode (Loop A):** system prompt (§6.3-A) + task input; injects `get_rules` output up front; Bedrock messages loop with tool-use (Mantle client, §5.9); ends when model emits `final_answer` tool or budget breach. On success/escalated: write episode (S3 raw + DB truncated), enqueue outbox `compile` event + post-commit SQS publish.

**Guided mode (Loop B):** retrieval (§5.5) picked a playbook →
1. **Freshness check** (D1/§5.6). Stale → log `retrieval_stale` metric, fall back to explore, and enqueue `recheck_suspect` for that playbook.
2. **Precondition check:** one cheap LLM call (Haiku, 200-token cap): "Task: {input}. Playbook preconditions: {list}. Incident data: {get_incident result}. Answer strictly {\"ok\": true/false, \"failed\": [..]}." Not ok → fall back to explore, log `precondition_miss`.
3. Execute `spec.steps` sequentially, binding `{params}` extracted from the task by a tiny LLM extraction call (Haiku) validated against `spec.params` types; executor injects idempotency keys per §5.3. Any tool error → mark playbook execution `failure`, apply confidence penalty, fall back to explore for the remainder.
4. On completion: update counters + confidence (§5.7) inside `run_txn`, write episode with `mode='guided'`.

### 5.5 `retrieval.py` — two-phase retrieval (D3, verbatim algorithm)

```python
async def retrieve(task_text: str) -> PlaybookCandidate | None:
    emb = await embed(task_text)                       # Titan V2, 1024-d, normalized
    rows = await q("""SELECT playbook_id, embedding <-> %s AS dist
                      FROM playbooks ORDER BY embedding <-> %s LIMIT 20""", (emb, emb))
    if not rows: return None
    ids = [r.playbook_id for r in rows]
    metas = await q("""SELECT playbook_id, spec, confidence, status_cache, domain
                       FROM playbooks WHERE playbook_id = ANY(%s)
                         AND status_cache IN ('active','candidate','suspect')""", (ids,))
    ranked = sort_by(dist asc, then confidence desc)
    best = first where dist <= THRESHOLD               # tune in Week 2; record chosen value
    return best or None
# 'suspect' playbooks ARE retrievable but executor forces a fresh get_rules + precondition pass.
# NOTE: with L2 on unit vectors, dist ranges [0, 2]; the old cosine cutoff 0.35 does NOT transfer.
# Starting point: L2 dist <= 0.85 (≈ cosine distance 0.36 on unit vectors, d_l2 = sqrt(2*d_cos));
# tune against the seed task set in Week 2 and record the final value here and in DEVIATIONS.md if changed.
```
Dedup on compile: before inserting a new playbook, vector-search own library; if top-1 L2 dist < 0.40 (≈ old cosine 0.08) and same domain → do not insert; instead record a success on the existing playbook (counts toward promotion).

### 5.6 `freshness.py` — point-of-use authority (D1)

```sql
-- Returns rows ONLY for stale deps. Empty result = fresh.
SELECT d.rule_key, d.rule_version AS depends_on, r.version AS head
FROM playbook_deps d
JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
WHERE d.playbook_id = %s AND r.version <> d.rule_version;
```
Wrapper returns `Fresh | Stale(stale_deps)`. Called: before guided execution (mandatory), by the worker when refreshing `status_cache`, and by `/api/impact` variants.

### 5.7 `confidence.py` — lifecycle math (all constants final)

- New playbook: `candidate`, confidence 0.30.
- Guided success: `confidence = min(0.99, confidence + 0.15)`; `successes+=1; uses+=1`. Promote to `active` when `successes >= 3 AND confidence >= 0.6`.
- Guided failure: `confidence *= 0.6`; `failures+=1; uses+=1`. If `< 0.20` → `status_cache='rejected'` (terminal; never retrieved: rejected excluded in phase-2 filter).
- Idle decay: worker daily job (piggyback on sweeper): `confidence *= 0.98` if `uses` unchanged in 7 days. (Demo-irrelevant; implement, don't showcase.)
- All updates inside `run_txn`; also insert `audit_log` rows for promotions/rejections.

### 5.8 `cascade.py` — the rule change (D1+D5, verbatim)

```python
async def change_rule(rule_key, new_body, new_params, actor):
    async def txn(cur):
        row = await one(cur, "SELECT version, domain FROM rules WHERE rule_key=%s AND valid_to IS NULL FOR UPDATE", (rule_key,))
        if not row: raise NotFound
        await cur.execute("UPDATE rules SET valid_to=now() WHERE rule_key=%s AND version=%s", (rule_key, row.version))
        newv = row.version + 1
        await cur.execute("INSERT INTO rules (rule_key,version,domain,body,params,changed_by) VALUES (%s,%s,%s,%s,%s,%s)",
                          (rule_key, newv, row.domain, new_body, Json(new_params), actor))
        eid = uuid4()
        await cur.execute("INSERT INTO outbox (event_id,kind,payload) VALUES (%s,'rule_changed',%s)",
                          (eid, Json({"rule_key": rule_key, "old": row.version, "new": newv, "domain": row.domain})))
        await cur.execute("INSERT INTO audit_log (actor,action,entity,detail) VALUES (%s,'rule.change',%s,%s)",
                          (actor, f"rule:{rule_key}", Json({"from": row.version, "to": newv})))
        return eid, newv, row.domain
    eid, newv, domain = await run_txn(txn)
    # post-commit, best-effort (sweeper is the safety net):
    try: sqs.send_message(QueueUrl=CASCADE_QUEUE, MessageBody=json.dumps({"event_id": str(eid)}))
    except Exception: log.warning("post-commit publish failed; sweeper will recover")
    # instant UX (D1): impacted ids via deterministic SQL, interrupt bus, SSE
    impacted = await q("SELECT DISTINCT playbook_id FROM playbook_deps WHERE rule_key=%s AND rule_version<%s", (rule_key, newv))
    running  = await q("SELECT task_id FROM tasks WHERE status='running' AND playbook_id = ANY(%s)", ([r.playbook_id for r in impacted],))
    interrupt_bus.interrupt_many([r.task_id for r in running], f"rule {rule_key} changed to v{newv}")
    await sse.publish("rule.changed", {"rule_key": rule_key, "new_version": newv, "impacted": [str(r.playbook_id) for r in impacted]})
```
Note: the sync txn touches 4 rows total regardless of fan-out size. Interrupt *flags* in the DB and `status_cache` flips are the worker's job (§7), seconds later; correctness never depends on them (D1/D4).

### 5.9 `llm.py` — Bedrock discipline

- **Two clients:** (1) `AnthropicBedrockMantle(aws_region=AWS_REGION)` for all Claude calls — Messages API with tool-use; model IDs from `BEDROCK_AGENT_MODEL_ID` / `BEDROCK_FAST_MODEL_ID` (§2.1.3). (2) `boto3` `bedrock-runtime` for Titan embeddings only (`BEDROCK_EMBED_MODEL_ID`, request body `{"inputText": ..., "dimensions": 1024, "normalize": true}`).
- Retries: 3 attempts, exponential backoff + jitter on throttling/5xx. Per-task token budget enforced here.
- Circuit breaker: 5 consecutive Bedrock failures → open for 30s → new tasks stay `queued`, SSE `metrics.tick` carries `{"llm":"degraded"}` so the UI shows a banner instead of errors.
- `embed(text)` → Titan V2 1024-d normalized; retry ×3; embedding failures on compile → job error → outbox `error` field + `compile_failed` event surfaced in UI.

---

## 6. Compiler pipeline (Loop A → playbooks) — `compiler.py`

### 6.1 PlaybookSpec (Pydantic, strict; compiler output rejected unless it parses)

```python
class Step(BaseModel):
    tool: Literal['get_incident','get_rules','check_remediation_eligibility','apply_remediation','notify_oncall']
    args: dict[str, str]                    # values may contain "{param}" placeholders;
                                            # idempotency_key args are OMITTED (executor injects them, §5.3)
class RuleCitation(BaseModel):
    rule_key: str; rule_version: int; used_in_step: int; why: str
class PlaybookSpec(BaseModel):
    goal: str
    preconditions: list[str]                # 1..6 short testable statements
    params: dict[str, Literal['string','int']]
    steps: list[Step]                       # 2..8
    rule_citations: list[RuleCitation]      # >=1 or compile is rejected
```

### 6.2 Pipeline (runs in the worker on `compile` events)

1. Load episode trajectory (DB copy; S3 if truncated). Both `remediated` and `escalated` successes compile (§5.4).
2. **Compile call** (`BEDROCK_AGENT_MODEL_ID`, temperature omitted — deterministic-enough with a strict schema and repair loop; prompt §6.3-B) → JSON only.
3. Parse via Pydantic. On failure: re-prompt with the validation error appended, max 2 retries; then mark outbox row `error`, insert `compile_failed` event (UI lists it under Playbooks → "Failed compiles"), stop. Never crashes the worker.
4. **Dependency verification (hard gate):** every `rule_citations[].rule_key` must exist; `rule_version` must equal the head version *at episode time* (the trajectory's `get_rules` output contains the versions — cross-check against it, not against current head). Citation referencing a nonexistent version → one repair retry → else reject.
5. **Safety lint:** steps only use whitelisted tools; `apply_remediation` present ⇒ a `check_remediation_eligibility` step precedes it; every placeholder appears in `params`; no step supplies its own `idempotency_key`.
6. Dedup check (§5.5). If new: single `run_txn` inserting `playbooks` + all `playbook_deps` rows + audit `playbook.compile`. Embed `goal + preconditions` text for the vector.
7. If this compile is a **re-learn** (payload has `supersedes`): set `version = old.version+1`, `supersedes = old_id`, and copy the old playbook's name.

### 6.3 Prompts (verbatim starting points; iterate only if eval fails)

**A. Explore-mode system prompt**
```
You are an on-call operations agent for a production platform. You resolve incidents by calling tools.
Non-negotiable policy:
1. Before any action, call get_rules for the relevant domain and follow the CURRENT rules exactly. Cite rule versions in your reasoning.
2. Never call apply_remediation without first calling check_remediation_eligibility for the same incident and action in this task.
3. If the rules do not permit automated action, do not force it: escalate gracefully, notify the on-call channel with the reason, and finish.
4. Be economical: fewest tool calls that correctly resolve the incident.
When done, call final_answer with {"outcome": "success"|"escalated", "summary": "..."}.
```

**B. Compiler prompt**
```
You convert one successful agent trajectory into a reusable playbook JSON.
Input: (1) the task text, (2) the full trajectory (tool calls, args, results), (3) the rules snapshot the agent read (with versions).
Output: ONLY a JSON object matching this schema: {schema_json}. No prose, no markdown fences.
Requirements:
- Generalize: replace task-specific values (incident ids, service ids, actions) with {param} placeholders declared in "params".
- Never include idempotency_key in step args; the executor supplies it.
- preconditions: the minimal testable conditions under which this playbook is safe to run.
- steps: the minimal ordered tool calls that reproduce the success. Drop exploratory/redundant calls.
- rule_citations: EVERY rule whose content influenced any step. Use the exact rule_key and version from the rules snapshot. Missing a dependency is the worst possible error; when unsure, include it with why.
```

**C. Re-plan-after-interrupt prompt** (appended to explore system prompt)
```
A rule changed while you were working. Old vs new: {rule_diff}.
Progress so far (already-executed steps and their results): {scratchpad}.
Do not repeat side effects that already happened (remediations and notifications are idempotent but do not re-issue them).
Re-read the rules, then either continue safely under the NEW rules or escalate with an explanation.
```

---

## 7. Worker — `worker/jobs.py` (Lambda; SQS-triggered + 60s EventBridge sweeper)

Handler dispatch: SQS message `{event_id}` → claim (D5a) → route by `kind`. Sweeper event → re-publish unprocessed outbox rows older than 30s, run status-cache reconciliation, run idle decay (daily guard via `audit_log` marker row). A `--once` CLI mode runs one dispatch inline for local dev (§2.1.4).

| Job | Effect (each step in batched `run_txn`, ≤100 rows/txn) |
|---|---|
| `rule_changed` | (1) Set `status_cache='invalidated', invalid_reason=...` for playbooks with a dep on any non-head version of `rule_key` (batched by id list from `deps_by_rule_idx`). (2) Set `status_cache='suspect'` for `active` playbooks in the same `domain` WITHOUT a dep edge on this rule (catches missed extractions) + enqueue one `recheck_suspect` per playbook. (3) Set `tasks.interrupt_flag=true, interrupt_reason=...` for running tasks whose `playbook_id` is impacted (durable fallback; the bus already fired). (4) Enqueue one `relearn` event per invalidated playbook. (5) Audit rows per transition. (6) SSE `playbook.changed` via a lightweight authenticated POST back to the API's `/internal/sse` endpoint (shared secret header, edge #10 in §2.1.2) — Lambda cannot publish to in-process SSE directly. |
| `relearn` | Idempotency: skip if a playbook with `supersedes=old_id` exists for the new rule version. Synthesize a representative task from the old spec's goal + a seed incident matching preconditions; run explore mode INSIDE the Lambda via shared `core/` (budget: 10 steps / 20k tokens); on success run compile pipeline with `supersedes`. On failure: mark outbox error; UI shows "Re-learn failed — run manually" button (→ `POST /api/playbooks/{id}/relearn` executes in the API service instead). |
| `recheck_suspect` | One capped LLM call (Haiku): "Does this playbook's behavior depend on rule {key} (new text: ...)? Playbook spec: {...}. Answer {\"depends\": bool, \"why\": ...}." depends=true → treat as invalidated (+ add the missing dep edge for v_old, audit `deps.repair`) and enqueue `relearn`; false → restore `status_cache='active'`, audit `playbook.recertified`. |
| `compile` | §6.2 pipeline. |
| Reconciliation (sweeper) | Recompute `status_cache` for playbooks where freshness join disagrees with cache (self-healing if any event was lost). |

**Packaging:** `backend/core` is vendored into the Lambda zip by `05_deploy_worker.sh` (no layer complexity). Lambda: 1024 MB, 120s timeout, reserved concurrency 2 (protects free-tier DB from thundering herds), env per §2.1.3.

---

## 8. HTTP API (FastAPI) — complete surface

| Method & path | Behavior |
|---|---|
| `POST /api/tasks {input}` | Create task `queued`, launch executor as background asyncio task, return `{task_id}` (202). Max 5 concurrent running tasks; beyond → stays queued, drained FIFO. |
| `GET /api/tasks/{id}` | Full task (incl. `result`) + episode summary. |
| `GET /api/tasks?limit=` | Recent tasks for console history. |
| `GET /api/events?topics=` | SSE stream (heartbeat every 15s — also keeps the CloudFront origin connection alive, §2.1.2; client auto-reconnects with `Last-Event-ID` — events are fire-and-forget, UI re-fetches on reconnect). |
| `GET /api/rules` | Head versions + last change info. |
| `GET /api/rules/{key}/history` | All versions for the lineage view. |
| `POST /api/rules/{key} {body, params}` | §5.8 `change_rule`. Validates params against a per-rule JSON schema (hardcoded map). Returns `{new_version, impacted_playbooks}`. Requires `X-Admin-Token`. |
| `GET /api/impact?rule_key=` | **Deterministic SQL (D6):** playbooks with deps on the current head of `rule_key` (i.e., would break on change), with names + confidence. Used by the rule editor's live "Impact preview". |
| `GET /api/playbooks` / `GET /api/playbooks/{id}` | List (status, confidence, counters) / detail incl. spec, deps with rule versions, lineage chain via `supersedes`. |
| `POST /api/playbooks/{id}/relearn` | Manual re-learn (also the fallback button). Requires `X-Admin-Token`. |
| `GET /api/metrics` | `{cold: {avg_ms, avg_tokens, avg_steps}, guided: {...}, retrieval: {hits, precondition_misses, stale_blocks}, counts by status}` — one SQL aggregate over `episodes` + `playbooks`. Also the ALB health-check path. |
| `POST /api/copilot {question}` | Ops Copilot (§8.1). |
| `POST /api/admin/reset` | Demo reset (v3.1): run the §4.1 idempotent seed — `TRUNCATE tasks, episodes, playbook_deps, playbooks, outbox, mock_action_log, mock_incidents, mock_services, rules CASCADE` (audit_log preserved), re-insert rules v1 + mock world. Guarded by `X-Admin-Token`. |
| `POST /internal/sse` | Worker → SSE bridge (`X-Internal-Secret` header; rejects otherwise). |

**Auth:** demo is public read; mutating endpoints (`POST /api/rules/*`, relearn, reset) require `X-Admin-Token`. Frontend stores it after a simple "admin unlock" input. No user accounts — out of scope, stated in README.

### 8.1 Ops Copilot (honest MCP-adjacent feature, D6 — demo-required, never cut per D8)

Backend implementation (NOT via MCP — MCP is the dev/ops path per D6): one Claude call with the schema DDL + question → produce a single read-only SQL statement → validate: must start with `SELECT`/`WITH`, single statement, no semicolon-chained writes; execute as `cascade_readonly` user (role-level `statement_timeout=3s`, §4 grants), `LIMIT 200` enforced by wrapping; return rows + the SQL + disclaimer. Any validation failure → refuse with message. UI renders results as a table and always shows the generated SQL in a collapsible block.

### 8.2 Demo Mode

The `reset` endpoint + a frontend "Reset demo" button (admin) + `make seed` locally. After reset, the dashboard shows scripted empty states that explain each panel.

---

## 9. Frontend spec (Next.js, single dashboard route `/`)

Layout: top metric bar + 2×2 grid (desktop) / stacked (mobile). One `EventSource`. All mutations optimistic with reconciliation on the next SSE/refetch. Skeleton loaders on first paint. Toasts for cascade events.

1. **Incident Console** (top-left): input + submit; live step stream (tool name, args summary, result badge, ms); mode badge 🔍 Exploring / ⚡ Runbook `name vX`; interrupt banner state ("⚠ Policy changed mid-flight — re-planning under new rules…") rendered from `task.status` SSE; history list of recent tasks with outcome chips (✅ remediated / 🔺 escalated / ❌ failed — escalated renders as a success variant, §5.4).
2. **Runbook Library** (top-right): cards — name+version, status pill (candidate=gray, active=green, suspect=amber, invalidated=red, rejected=strikethrough), confidence bar, `uses/successes/failures`; expand → steps, preconditions, **Provenance**: "depends on `incident.rollback_window` v1 *(step 2: eligibility gate)*" each with fresh/stale dot; **Lineage**: v1 → v2 chain with links; buttons: Re-learn (on invalidated), View episodes. "Failed compiles" collapsible section. Amber (suspect) cards show tooltip copy "Quarantined pending re-check — a related policy changed" so the domain-wide suspect flip reads as a feature, not a glitch (see §15).
3. **Policy Panel** (bottom-left): each rule: key, head version, body, editable `params` form (typed inputs from the per-rule schema); **Impact preview** (live `/api/impact` as the user focuses the editor): "3 active runbooks depend on this policy"; Save → confirm dialog listing impacted playbooks → on success toast "Policy v2 saved — cascading…" and cards flip via SSE; History drawer per rule.
4. **Ops Copilot** (bottom-right): chat box; answers render as table + collapsible SQL + fixed disclaimer footer. **This panel appears in the demo video (D8).**
- **Top metric bar:** Cold vs Guided avg time & tokens (two big numbers + delta %), retrieval hit rate, playbook counts by status, LLM health badge (from `metrics.tick`). This is the demo money-shot; make it prominent and keep it on screen in every video segment (D8).
- Empty states: Console — "No incidents worked yet. Try: *Remediate INC-1001*."; Library — "No runbooks yet — the agent learns them from successful incident resolutions."
- Error states: SSE disconnect banner with auto-retry; task failure card shows budget/tool reason; degraded-LLM banner queues submissions instead of erroring.

---

## 10. Edge-case matrix (implement every row; each maps to a test in §11)

| # | Case | Handling (binding) |
|---|---|---|
| 1 | Compiler misses a rule dependency | Domain quarantine → `suspect` → `recheck_suspect` job repairs the edge or re-certifies (§7). Suspect playbooks execute only with forced fresh `get_rules` + precondition pass. Sweeper reconciliation self-heals cache. |
| 2 | Rule changes mid-execution | Bus interrupt (µs) + durable flag before side-effects (D4); scratchpad persisted; re-plan prompt §6.3-C; remediations AND notifications idempotent so resume can't double-apply. |
| 3 | `40001` retry storms | D1 removed the hot txn; residual conflicts handled by `run_txn` backoff; worker batches ≤100 rows/txn; Lambda reserved concurrency 2. |
| 4 | Duplicate playbooks | Dedup at compile (L2 dist < 0.40 same-domain → feedback instead of insert). |
| 5 | Lucky-episode bad playbook | candidate→active gate (3 successes & conf ≥0.6); failure decay ×0.6; auto-reject <0.2; idle decay. |
| 6 | Wrong-playbook retrieval | Distance cutoff (§5.5) + mandatory precondition check + tools re-verify rules themselves (LLM cannot bypass policy, §5.3). |
| 7 | Malformed compiler JSON | 2 repair retries → `compile_failed` surfaced in UI; worker never crashes. |
| 8 | LLM parametric staleness | Memory layer never serves stale playbooks (point-of-use check); current rule text always injected; tools enforce head rules at execution. Claim in README: "stale-memory quarantine guarantee," NOT "zero hallucination." |
| 9 | Huge cascade fan-out | Sync txn O(1); UI flips via impact query + SSE; heavy work async & batched. |
| 10 | Worker crash mid-job | Claim leases expire after 5 min; idempotent upserts; sweeper re-publishes. |
| 11 | Bedrock throttle/outage | §5.9 retries + circuit breaker + queued tasks + UI banner. |
| 12 | Embedding model change | `embedding_model` column; retrieval implicitly single-model now; migration = re-embed job (documented, not built). |
| 13 | Runaway agent | 15 steps / 60s / 25k tokens hard caps; failure episode still logged. |
| 14 | Concurrent edits to same rule | `FOR UPDATE` on head row inside serializable txn; loser retries, reads new head, increments correctly. |
| 15 | Demo-day failure | `POST /api/admin/reset` (restores rules v1 too, v3.1); every demo beat pre-recorded as fallback video segments (weekly, D8); mock world has zero external dependencies. |
| 16 | Security | Scoped SQL users (§4 grants incl. readonly `statement_timeout`); audit INSERT-only; MCP endpoint read-only default with `cascade_readonly`; secrets in Secrets Manager; admin token on mutations; Copilot SQL validator + timeout; no PII in seed. Judge MCP credentials are a deliberate, scoped exposure on a throwaway demo cluster — stated in README. |
| 17 | Reproducibility | One-command local (`docker compose up` + `make seed`), scripted cloud (`infra/scripts/01..05`), `.env.example` mirroring §2.1.3, README 5-minute tour. |
| 18 | SSE client disconnects | Heartbeats (also hold the CloudFront origin connection open, §2.1.2); UI refetches state on reconnect; events are notifications, state lives in DB. |
| 19 | Task submitted during cascade | New retrievals immediately see staleness via point-of-use check even if `status_cache` lags → explore fallback; no wrong execution window exists. |
| 20 | Lambda cold start delays relearn | Acceptable (~1–2s); UI copy says "re-learning in background"; manual button as fallback. |
| 21 | Escalation misread as failure (v3.1) | Outcome mapping in §5.4: escalated = success + `result='escalated'`; confidence math and compile pipeline treat it as success; UI renders a distinct success chip. |
| 22 | Mixed-content deploy failure (v3.1) | CloudFront fronts the ALB (§2.1); frontend only ever configured with the CloudFront URL; §16 checklist verifies no mixed-content console errors on the public URL. |

---

## 11. Testing plan (pytest; run against local single-node CRDB in CI via GitHub Actions)

**CI note (v3.1):** GitHub Actions `services:` containers can't override the container command, and CRDB needs `start-single-node --insecure` — start it with an explicit `docker run -d -p 26257:26257 cockroachdb/cockroach:latest start-single-node --insecure` step (plus a health-wait loop) instead of a service container. Apply the local vector-index cluster setting in the same step (§2 local dev note).

**Unit:** PlaybookSpec validation incl. rejection paths (idempotency_key in args must fail lint); confidence math table-driven; Copilot SQL validator (accept SELECT/WITH, reject UPDATE/multi-statement/comment tricks); retrieval ranking; freshness join truth table; outcome mapping (escalated → succeeded/'escalated'/episode success).
**Integration (real local CRDB, mocked Bedrock via recorded fixtures):**
- `test_learn_reuse`: task → compile fixture → second task retrieves & runs guided → metrics delta.
- `test_cascade`: change rule → outbox row exists → worker jobs run inline → invalidated + suspect + relearn events; freshness join stale before worker runs (proves D1 point-of-use).
- `test_interrupt`: start slow fake task → change rule → bus interrupt observed before next side-effect; scratchpad persisted; resume completes under new rule.
- `test_idempotent_side_effects`: double `apply_remediation` same key → one `mock_action_log` row; double `notify_oncall` same key → one row.
- `test_escalation_success`: tier-blocked incident → `final_answer escalated` → task `succeeded` + `result='escalated'`, episode `success`, compile event enqueued.
- `test_outbox_recovery`: skip post-commit publish → sweeper picks it up.
- `test_concurrent_rule_edit`: two coroutines edit same rule → versions v2 and v3, no lost update.
- `test_40001_retry`: force serialization conflict → `run_txn` succeeds within retries.
- `test_reset_restores_rules`: change rule to v2 → reset → head is v1 again, playbooks/tasks empty, audit preserved.
**Manual EXPLAIN check (Week 1, required, D8):** paste vector query plan into `docs/query-plans.md` (verified via Claude Code over the Managed MCP Server — record the screen); confirm the plan uses `pb_embed_idx` with the `<->` operator; if index unused, fix the operator/opclass mismatch per D3 before any dependent work proceeds.
**Load sanity (Week 5):** 20 concurrent tasks + 3 rule changes; assert zero stale executions (grep audit), p95 API latency < 500ms excluding LLM time.

---

## 12. Deployment runbook (`infra/scripts/`, in order)

0. **Day-0 verifications (do these before writing more code; ~1 hour):**
   (a) AWS console → Bedrock → Model access (us-east-1): enable Anthropic Claude (Sonnet + Haiku) and Amazon Titan Text Embeddings V2; run one `AnthropicBedrockMantle` smoke call and one Titan embed call; if a pinned model ID (§2) is unavailable, pick the closest available and record it in `DEVIATIONS.md`.
   (b) Create the free-tier CockroachDB cluster; verify `CREATE VECTOR INDEX` succeeds and the cluster's Cloud Console page exposes the **Managed MCP Server** config snippet. If either is unavailable on free tier, use the smallest trial/paid cluster and note it in `DEVIATIONS.md`.
   (c) `ccloud auth login` works with the service account.
1. **`01_ccloud_provision.sh`** — create cluster `cascade` (AWS us-east-1); create SQL users `cascade_app`, `cascade_worker`, `cascade_readonly` (+ readonly `statement_timeout`, §4); emit connection strings. Also print the Cloud Console steps to copy the **Managed MCP Server config snippet** (manual: Console → cluster → MCP → copy → paste into Claude Code settings) and store the readonly service account for it (judge access: documented in README as a deliberate, scoped exposure on a throwaway demo cluster).
2. **`02_migrate.sh`** — (local only, guarded) `SET CLUSTER SETTING feature.vector_index.enabled = true;` → run `001_schema.sql`, `002_seed.sql`, apply grants.
3. **`03_aws_bootstrap.sh`** — create: S3 bucket `cascade-episodes-<acct>`; SQS `cascade-events` (+DLQ, maxReceive 3); SNS `cascade-bus` (+per-instance queue when fan-out enabled); Secrets Manager entries per §2.1.3; ECR repo; ECS cluster+service (Fargate, 1 task, ALB, health check `/api/metrics`); **CloudFront distribution** (origin = ALB over HTTP, viewer HTTPS, `/api/*` behavior: `CachingDisabled` + `AllViewerExceptHostHeader`, origin response timeout 60s); Lambda `cascade-worker` (SQS trigger + EventBridge 60s rule); IAM roles from `infra/policies/` (task role: Bedrock invoke, S3 rw on bucket, SQS send, Secrets read; Lambda role: SQS consume, Bedrock invoke, S3 rw, SQS send, Secrets read).
4. **`04_deploy_backend.sh`** — docker build/push, force new deployment, wait healthy, print ALB DNS and CloudFront URL.
5. **`05_deploy_worker.sh`** — vendor `core/`, zip, update function, set `API_BASE_URL` to the ALB DNS.
6. **Frontend** — Amplify Hosting connected to repo `frontend/`, env `NEXT_PUBLIC_API_URL=https://<dist>.cloudfront.net` (NEVER the raw ALB URL — mixed content, §2). (If Amplify friction: `next export` static to S3+CloudFront is the sanctioned fallback; note in DEVIATIONS.md.)
7. Smoke test the public URL end-to-end **over HTTPS with the browser console open (zero mixed-content errors)**; run `POST /api/admin/reset`.

---

## 13. README + architecture diagram spec

README sections (in order):
1. Hero gif (the unlearn moment: rule edit → cards flip red → v2 appears).
2. One-paragraph pitch (§0, incident domain).
3. **"Who this helps & why it matters" (D8, required):** two short paragraphs. First: on-call reality — runbook knowledge lives in wikis and heads, goes stale silently, and stale automation against production is dangerous; Cascade makes agent-learned runbooks *auditable, versioned, policy-governed, and self-quarantining*, cutting repeat-incident toil (the 3–5× guided-vs-cold delta) without ever trading away safety. Second: honest scope — the mock world is a deterministic stand-in for real infrastructure; the product is the memory layer, and every mechanism (provenance, freshness gate, cascade, re-learning) is production-shaped and domain-portable.
4. **"5-minute tour"** (exact clicks reproducing the demo).
5. Architecture diagram + a condensed §2.1 connection map.
6. **Contest compliance table** — CockroachDB tools used: Distributed Vector Indexing (runbook retrieval, §D3), Managed MCP Server (dev/ops workflow + judge reproduction steps with readonly account, §D6), Agent Skills Repo (`docs/skills-review.md`), ccloud CLI (provisioning scripts); AWS used: Bedrock, ECS Fargate, ALB, CloudFront, Lambda, SQS, SNS, EventBridge, S3, Secrets Manager, Amplify.
7. **Judging-criteria map (D8, required; also pasted into the Devpost description):** a 5-row table — Agentic Memory Design → semantic/procedural/episodic/working memory all in CRDB (§4) with the staleness lifecycle; Technical Implementation → D1–D6 + `docs/query-plans.md`; Real-World Impact → section 3 narrative + metrics; Production Readiness → §10 edge matrix, scoped users, outbox, circuit breaker, audit; Creativity & Originality → provenance-derived unlearning enforced at point-of-use.
8. **Honest guarantees** paragraph (stale-memory quarantine at point-of-use; eventual UI cache; what we do NOT claim).
9. Local quickstart; cloud deploy; design decisions D1–D8 summarized; test instructions; license.

Diagram (draw.io → `docs/architecture.png`): browser → Amplify (static) and browser → CloudFront → ALB → FastAPI(ECS) → {CockroachDB, Bedrock, S3, SQS} ; SQS → Lambda → {CockroachDB, Bedrock} → `/internal/sse` back to API; Claude Code —MCP→ CockroachDB Managed MCP Server → cluster. Label the outbox/sweeper loop and the point-of-use freshness check.

---

## 14. Milestones & exit tests (5 weeks, de-risk gates per D8; dates from today, Jul 15 2026)

| Week (dates) | Build | Exit test (must pass before next week) |
|---|---|---|
| 1 (Jul 15–21) | **Day-0 verifications (§12 step 0)**; cluster + schema + seed; FastAPI skeleton; `run_txn`; tools; explore loop; episodes to DB+S3; **embeddings + vector index + EXPLAIN gate (moved up, D8)** — verify via Claude Code over MCP and screen-record it | `POST /api/tasks {"input":"Remediate INC-1001"}` → succeeded, action-log row exists, episode logged; `docs/query-plans.md` proves `pb_embed_idx` usage with `<->`; MCP dev-workflow footage saved |
| 2 (Jul 22–28) | Compiler pipeline + prompts; two-phase retrieval; guided execution; confidence; tune the L2 distance threshold (§5.5) | Same task twice → second run guided, ≥3× faster steps/latency in `/api/metrics` — **the money metric; if the delta isn't visible, stop all feature work and fix before Week 3** |
| 3 (Jul 29–Aug 4) | `change_rule`; outbox+SQS+Lambda+sweeper; worker jobs (invalidate/suspect/interrupt/relearn/recheck); bus interrupts; freshness gate | Change `incident.rollback_window` to 4 hours while a task runs → task interrupts & re-plans; playbook invalidated (cache) but point-of-use already blocks; v2 playbook appears < 60s. **Thin-slice gate (D8): full learn→reuse→unlearn path works end-to-end (ugly UI fine); record rough fallback footage** |
| 4 (Aug 5–11) | Full dashboard + SSE + impact preview + Copilot + reset; CloudFront + Amplify deploy live; skills review doc (`docs/skills-review.md`) | A non-team member follows README 5-minute tour successfully on the public HTTPS URL |
| 5 (Aug 12–16) | Hardening (edge matrix audit), load sanity, README/diagram per §13, video per §15, **submit by Aug 16, 5:00 PM EDT (≥48h early)** | Devpost submission complete; video public; repo license visible in About |

**Scope-cut order if behind (cut from bottom, and cut at the Week-3 gate rather than compressing Weeks 4–5):** SNS multi-instance fan-out (keep code, off) → `recheck_suspect` LLM job (keep quarantine flag + manual re-certify button) → auto-relearn (keep manual button). **Never cut (D8):** point-of-use freshness gate, cascade txn, guided-vs-cold metrics, interrupt demo, Ops Copilot panel, MCP dev-workflow footage.

---

## 15. 3-minute demo video script (winner patterns per D8: pitch first, ~60% explain / 40% demo, unhurried voice, metric bar always on screen)

- **0:00–0:10 — Elevator pitch over the live dashboard:** *"Cascade is an on-call agent that learns remediation runbooks from experience — and the moment your policies change, it quarantines every stale runbook before one can touch production."* Title card: name + one-liner.
- **0:10–0:30 — Problem:** agents relearn everything from scratch; worse, they *remember wrong things* after the world changes. In incident response, a stale runbook is not an inconvenience — it's an outage multiplier.
- **0:30–0:55 — Learn (cold run):** `Remediate INC-1001` — ~11 steps / ~35s, narrated calmly; a runbook card appears with provenance: "depends on `incident.rollback_window` v1".
- **0:55–1:15 — Reuse (warm run):** `INC-1002` → ⚡ 4 steps / ~8s; camera holds on the metric bar delta; say the numbers out loud ("three to five times faster, a fraction of the tokens").
- **1:15–2:05 — The unlearn moment (the money shot):** start a slow task; edit `incident.rollback_window` 24→4 in the Policy Panel; impact preview lists dependent runbooks → save; live: the running task shows the interrupt banner and re-plans; dependent cards flip red; **narrate the amber cards explicitly** — *"every other runbook in the domain goes amber: quarantined until the system re-certifies it doesn't depend on the changed policy — watch them recover"* (turns the domain-wide suspect flip from a visual surprise into a selling point); audit toast; say the line: *"one tiny transaction — staleness is derived from provenance and enforced at point-of-use, so a stale runbook can never execute, even before the cache catches up."*
- **2:05–2:30 — Repair + the CockroachDB tools on camera:** v2 runbook auto-compiled (lineage v1→v2); Ops Copilot answers one analytics question with its generated SQL expanded on screen; 5-sec cut of Claude Code inspecting the cluster through the Managed MCP Server (Week-1 footage).
- **2:30–3:00 — Close:** architecture slide + CockroachDB/AWS tools table + repo URL; final line on impact: *"every skill the agent knows is versioned, auditable, and safe to trust — that's what a production memory layer looks like."*

Production notes: record narration separately from screen capture; no segment relies on live infrastructure (assemble from the weekly fallback footage if needed); rehearse to land under 2:55.

---

## 16. Submission checklist (Devpost)

- [ ] Public GitHub repo, MIT `LICENSE`, license visible in About section
- [ ] README complete per §13 incl. impact section + judging-criteria map; `.env.example` mirroring §2.1.3; setup + run instructions verified on a clean machine
- [ ] Public demo URL live **and HTTPS end-to-end (CloudFront) — browser console shows zero mixed-content errors**; `POST /api/admin/reset` run just before submitting (restores rules v1)
- [ ] Video < 3:00 per §15 (pitch in first 10s; MCP + Copilot beats present), uploaded YouTube/Vimeo, set to Public, link tested logged-out
- [ ] Devpost form: which CockroachDB tools + how (copy compliance table); which AWS services + how; description opens with the impact paragraph and includes the judging-criteria map
- [ ] Optional fields filled: architecture diagram; CockroachDB tools feedback (from `docs/skills-review.md`)
- [ ] Submitted ≥48 hours before Aug 18, 5:00 PM EDT (target: Aug 16, 5:00 PM EDT)

*End of specification.*
