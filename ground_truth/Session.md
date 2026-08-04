# Cascade — Session Record

**Project:** Cascade — a procedural memory layer for AI agents that learns skills and knows when to unlearn them
**Contest:** CockroachDB × AWS Hackathon — "Build with Agentic Memory" (Devpost)
**Deadline:** Aug 18, 2026, 5:00 PM EDT · **Submit target:** Aug 16
**Team:** Ashfaq (Shell: API + Frontend + Infra) · Shawki (Engine: Core Memory + AI)
**Repo:** `github.com/ashfaqstu/cockroach`

> This record covers the full working session. The conversation was compacted
> partway through; content below is reconstructed from the working state and
> the artifacts produced.

---

## Table of contents

1. [Phase 1 — Competitive analysis: can this win?](#phase-1)
2. [Phase 2 — Spec hardening v2 → v3 (judging fit)](#phase-2)
3. [Phase 3 — Blind-implementer audit v3 → v3.1](#phase-3)
4. [Phase 4 — Technical requirements & setup](#phase-4)
5. [Phase 5 — Work-split audit v2 → v3](#phase-5)
6. [Phase 6 — Workflow & merge runbook](#phase-6)
7. [Phase 7 — Frontend design spec](#phase-7)
8. [Phase 8 — Sprint plan & Day-0 skeleton](#phase-8)
9. [Artifact inventory](#artifacts)
10. [Binding decisions — do not regress](#decisions)
11. [Open items](#open)

---

<a name="phase-1"></a>
## Phase 1 — Competitive analysis: can this win?

**Asked:** Analyze whether CASCADE can win, based on the contest and how winners of comparable hackathons documented and presented.

### Contest facts established

| | |
|---|---|
| Prize pool | $8,750 — 1st: $5,000 + blog feature, 2nd: $2,500, 3rd: $1,250 |
| Registrants | ~1,461 |
| Required | ≥2 CockroachDB tools (Managed MCP Server · Distributed Vector Indexing · ccloud CLI · Agent Skills Repo) and ≥1 AWS service |
| Also required | Public repo (MIT/Apache) with license visible in **About**, functional demo URL, video <3 min, documentation of tools used |

**Five judging criteria:** Agentic Memory Design · Technical Implementation · Real-World Impact · Production Readiness · Creativity & Originality.

**Theme language (this mattered later):** *"production workflows like code writing, pipeline operations, and incident diagnostics."*

### Verdict

**Genuinely top-3 competitive, plausibly 1st — conditional on finishing with a rock-solid demo.**

| Criterion | Fit | Note |
|---|---|---|
| Agentic Memory Design | ⭐ Exceptional | Semantic (rules) + procedural (playbooks) + episodic (episodes) + working (tasks) memory, all load-bearing in CockroachDB. This is the win condition. |
| Technical Implementation | ⭐ Exceptional | Two-phase vector retrieval with EXPLAIN proof, transactional outbox, retry wrapper, point-of-use freshness join |
| Production Readiness | ⭐ Exceptional | Outbox+sweeper, circuit breaker, scoped SQL users, append-only audit, idempotency, DLQs. Most entries are thin here |
| Creativity & Originality | ⭐ Strong | "Stale-memory quarantine enforced at point-of-use" — sharp, memorable, defensible |
| **Real-World Impact** | 🟡 **Weakest** | A mock refund desk has no real users — the one vulnerable axis |

Four of five at ceiling on paper, which is rare.

### Winner patterns identified (from Devpost judge panels and demo-video guides)

- Elevator pitch in the first 5–10 seconds; ~60% explain / 40% demo; clear unhurried voice
- **The metric dashboard is the credibility** — judges reward pointing at real measured numbers
- One feature that shines, not five that flicker
- README must let a judge understand what it does, why it matters, and reproduce it
- Balance across all criteria; don't shoehorn
- Mock everything; remove every place the demo can stall

### Two recommendations that drove everything after

1. **Pivot the domain** from fintech refunds to incident-response runbooks — hits the judges' own vocabulary and fixes the weak axis at near-zero architectural cost.
2. **Make MCP visible in the product**, not just in the terminal — a 3-minute video skim won't show a dev-only workflow.

---

<a name="phase-2"></a>
## Phase 2 — Spec hardening v2 → v3 (judging fit)

**Produced:** `CASCADE_BUILD_SPEC.md` v3, adding decisions **D7** and **D8**.

### D7 — Domain pivot to SRE incident-response runbooks

A pure reskin; D1–D6 architecture untouched.

| Before (retired) | After |
|---|---|
| `mock_orders`, `mock_ledger` | `mock_services`, `mock_incidents`, `mock_action_log` |
| `refund.window`, `refund.max_auto_amount` | `incident.rollback_window`, `incident.auto_remediate_tier`, `incident.notify`, `incident.single_action` |
| `get_order`, `issue_refund`, `notify_customer` | `get_incident`, `apply_remediation`, `notify_oncall` |
| Demo change: refund window 30→14 days | Demo change: rollback window 24→4 hours |

Why it wins: on-theme with the contest's own framing, and "a stale runbook executed against production infrastructure" is viscerally dangerous in a way a late refund is not.

### D8 — Demo-first de-risking + winner presentation patterns

1. EXPLAIN gate moves to Week 1 — verified *through Claude Code over the Managed MCP Server* and screen-recorded, so one action yields both proof and video footage
2. Thin-slice gate at end of Week 3 — full learn→reuse→unlearn working, ugly UI acceptable
3. Fallback footage recorded weekly
4. Video follows winner patterns
5. Impact narrative is a first-class deliverable (README "Who this helps" + judging-criteria map)
6. Never-cut list extended to include **Ops Copilot panel** and **MCP dev-workflow footage**

---

<a name="phase-3"></a>
## Phase 3 — Blind-implementer audit v3 → v3.1

**Asked:** "If we blindly follow the spec, will there be any weakness?"

Audited as the implementer would experience it. **Six real spec bugs found**, all fixed in v3.1, plus a new §2.1 connection map.

### The six fixes

| # | Bug | Why it would have hurt | Fix |
|---|---|---|---|
| 1 | **HTTPS trap** | A bare ALB gets `http://…elb.amazonaws.com` and cannot carry an ACM cert without a domain. Amplify serves HTTPS → browser blocks HTTPS→HTTP API calls as mixed content. **The deployed frontend would silently fail every call, discovered in Week 4–5.** | CloudFront fronts the ALB (`CachingDisabled` + `AllViewerExceptHostHeader`, 60s origin timeout). SSE survives because 15s heartbeats sit under that timeout |
| 2 | **Vector metric mismatch** | Index created with default (L2) opclass while every query used `<=>` (cosine) → planner silently skips the index. The exact failure D3 exists to prevent | Titan V2 with `normalize: true` → unit vectors → L2 ≡ cosine ranking. **`<->` everywhere, `<=>` banned.** Thresholds re-derived: retrieval L2 ≤ 0.85, dedup < 0.40 (`d_l2 = √(2·d_cos)`) |
| 3 | **Internal contradiction** | D3 said filter `('active','candidate')`; §5.5 said `('active','candidate','suspect')`. Following D3 kills edge-case #1's recovery path | §5.5 is authoritative; both reconciled |
| 4 | **Escalation unmapped** | `final_answer {"outcome":"escalated"}` had no place in the `tasks.status` or `episodes.outcome` enums → a *policy-compliant* escalation would be recorded as failure, punishing correct playbooks via confidence decay | Added `tasks.result` (`remediated`/`escalated`). Escalation = task `succeeded`, episode `success`, **compile still enqueued** |
| 5 | **Reset doesn't restore rules** | `rules` missing from the reset TRUNCATE list → after the demo's 24→4h change, reset leaves the rule at v2 and the seed's v1 insert collides on PK | Explicit TRUNCATE list including `rules`; `audit_log` deliberately preserved |
| 6 | **Enablement gaps** | Local vector indexing may be gated behind a cluster setting; Bedrock model IDs unpinned despite "fixed versions where it matters"; model access is a manual console grant | `SET CLUSTER SETTING feature.vector_index.enabled` in migrate (guarded); model IDs pinned; **§12 step 0 Day-0 verifications** added |

### Also swept in

- `notify_oncall` gains an idempotency key — executor injects deterministic `{task_id}:{step_index}` for **all** side effects; compiler lint rejects specs supplying their own
- `cascade_readonly` gets role-level `statement_timeout = '3s'`
- Video script now **narrates the amber suspect-flip as a feature** ("quarantined until re-certified — watch them recover") with matching UI tooltip, turning a visual surprise into a selling point
- Real calendar dates in the milestone table

### New §2.1 — End-to-end connection map

Four parts: **2.1.1** ASCII topology with protocols and ports · **2.1.2** 13-edge connection table (protocol, auth credential, config source) · **2.1.3** env & secrets matrix per consumer · **2.1.4** the three core flows (Learn / Reuse / Unlearn) traced browser→services→UI, plus collapsed local-dev wiring.

---

<a name="phase-4"></a>
## Phase 4 — Technical requirements & setup

**Produced:** `SETUP.md` — the "what to have ready before building" layer, Windows 11 specific.

### The stack, decided

| Question | Answer |
|---|---|
| Cloud | **AWS**, `us-east-1` (widest Bedrock availability; must match cluster region) |
| Database | **CockroachDB Cloud** serverless, database `cascade` |
| Backend | **FastAPI** + Python **3.12** (async-native, native SSE, Pydantic v2 for the compiler gate) |
| Frontend | **Next.js 14** App Router + TypeScript + Tailwind + `shadcn/ui` |
| LLM | **Bedrock** via `AnthropicBedrockMantle`: `anthropic.claude-sonnet-5` (agent/compiler), `anthropic.claude-haiku-4-5` (cheap calls), `amazon.titan-embed-text-v2:0` (1024-d, normalized) |
| Compute | ECS Fargate + ALB + **CloudFront** |
| Worker | Lambda 3.12 + SQS + EventBridge |

### Key findings

- **Bedrock model access is the #1 blocker** — a manual console grant that can take up to 24h. Request before writing code.
- **Cost forecast:** ~$50–120 if you deploy in Week 4 only; ~$80–150 running from Week 1. ALB (~$16/mo floor) and Bedrock tokens are the real variables. Five cost levers documented.
- **App Runner** noted as a documented alternative that would eliminate ALB+CloudFront and the whole mixed-content problem — recommendation is to keep ECS (spec-aligned, names ECS on the compliance table) but switch without hesitation if CloudFront wiring eats more than half a day.
- Windows specifics: WSL2 recommended (repo inside the Linux filesystem, not `/mnt/c`); `.gitattributes` with `eol=lf` mandatory or bash scripts fail with `$'\r': command not found`; `--platform linux/amd64` required or Fargate rejects the image.
- Learning-curve honesty: the algorithmic core is the easy part; budget time for IAM, first ECS deploy, SSE through CloudFront, and async Python pitfalls (never call synchronous `boto3` in a request handler without `run_in_executor`).

---

<a name="phase-5"></a>
## Phase 5 — Work-split audit v2 → v3

**Asked:** Ensure the two-person task split doesn't deviate from the spec.

The v2 structure was sound (near-zero file overlap, frozen contract). **Nine silent conflicts with spec v3.1** found, plus **five orphaned artifacts**.

### The nine conflicts

| # | v2 said | Problem | Fix |
|---|---|---|---|
| 1 | `is_fresh() -> bool` | Spec §5.6 returns `Fresh \| Stale`. A bool discards the stale-dep list the UI needs for "why" and `recheck_suspect` needs to enqueue | Rich return type |
| 2 | `change_rule(rule_key, new_value)` | Spec takes `(rule_key, new_body, new_params, actor)` — rules have both text and JSONB params; `actor` is required for the audit row | Signature corrected |
| 3 | `find_candidate()` | Spec §5.5 names it `retrieve()` → guaranteed import break | Renamed |
| 4 | Postmortem "at the tail end of `run_task`" | **Puts a Bedrock call inside the measured path → inflates `episodes.latency_ms` → corrupts the Week-2 cold-vs-guided money metric** | Outbox event, generated in the worker |
| 5 | `notify_oncall` "gets a real webhook POST" | Breaks edge-case #15's "zero external dependencies" guarantee — a live call can hang mid-demo | Behind `ENABLE_OUTBOUND_WEBHOOK` (default false), 2s timeout, failures swallowed |
| 6 | Insights on the 60s sweeper | Wasteful; spec already has a daily-guard pattern | Reuses the daily guard |
| 7 | Approval pause via `await asyncio.Event` | **(a)** the 60s wall-clock budget would kill a task waiting on a human; **(b)** an in-memory Event dies on ECS redeploy → task hangs forever | Wait excluded from budget clock; resume reloads from DB, bus is a fast path only |
| 8 | 3 new tables "additive, no risk" | Spec §8's reset has an explicit TRUNCATE list → demo reset leaves stale rows | All three added |
| 9 | Week 5 = feature work | Spec §14 Week 5 is hardening + README + video + submit | Extensions land by Week 4; Week 5 frozen |

### Five orphaned artifacts, now assigned

`migrations/*.sql` → Shawki (frozen after Day 0) · `docs/query-plans.md` → Shawki · `docs/skills-review.md` → Shawki · test suite → split (unit=Shawki, integration=Ashfaq) · README + video + `architecture.png` → Ashfaq

### Added: D-1 → D-7 decision table

Seven decisions to agree before coding, each with a recommended default: paused-task status enum · risk-tag source · webhook auth · postmortem storage · **stub strategy** · extension cut order · AWS account ownership.

---

<a name="phase-6"></a>
## Phase 6 — Workflow & merge runbook

**Produced:** `WORKFLOW.md`.

### The discovery that mattered most

**The contract runs in both directions — v2 only modeled one.**

- Track A imports `core/contracts.py` (Shawki's surface) ✓ modeled
- **Track B imports `app/db.py` (`run_txn`, `q`) and `app/bus.py` (`InterruptBus`, `SSEBroadcaster`) — Ashfaq's surface** ✗ not modeled

If Ashfaq changed `run_txn`'s signature in Week 3, every file Shawki owns would break. Both surfaces are now frozen Day 0.

### The mechanism that removes an entire bug class

**Shawki commits real files with stub bodies on Day 0**, gated by `CASCADE_STUB_MODE`. Consequences:

- Ashfaq builds the entire UI and every router on Day 1 against realistic canned data
- When Shawki fills a body, **Ashfaq changes nothing** — no import swap, ever
- Flipping the flag to `false` *is* the integration test
- Neither track is ever blocked on the other

### Structure

- **Conflict surface:** exactly 9 files can ever collide; everything else has one owner
- **Two lanes:** fast lane (own files, self-merge on green CI) · contract lane (shared files, other person approves)
- **Merge order rule:** contract → engine → shell, so `main` is never in a state where the shell calls something that doesn't exist
- **Five integration points** (I0–I4) with per-week merge tables and Ashfaq-specific end-to-end checklists
- Conflict-resolution playbook, pre-merge checklist, and a one-page "what do I do next?" decision tree

---

<a name="phase-7"></a>
## Phase 7 — Frontend design spec

**Produced:** `FRONTEND_DESIGN.md`.

### Thesis

> **This is an operations console, not a SaaS dashboard.**

Three principles: **color is semantic, never decorative** (which is what makes the cascade flip read as *meaning*) · **identifiers are monospace, prose is sans** · **only three things animate**.

### System

- Palette: near-black cool surfaces (`#0B0E10` / `#14181B`), cyan accent `#3ECFD6` (deliberately not purple), status colors from GitHub Primer dark — battle-tested for state-on-dark and reads as engineering tool
- Type: **IBM Plex Sans + IBM Plex Mono** — technical heritage, free, and the sans/mono split *is* the identity
- 6px radius (never ≥12px), borders not shadows, 140ms ease-out
- 2×2 grid is **sacred** — all extensions go to a right rail or modals, never new grid cells

### The onboarding rail — one component, three jobs

A three-step numbered strip: **① Run an incident → ② Reuse what it learned → ③ Change a policy**, each pre-filling the console and self-completing, persisted in localStorage.

It onboards a first-time user, walks a judge through the README's 5-minute tour without them reading it, and gives a rehearsed demo path.

### The cascade choreography

Specified with explicit timings rather than improvised, because it's the 50 seconds the submission is judged on. **The 60ms stagger is the trick** — simultaneous flipping reads as a page repaint; staggered reads as a cascade propagating through a dependency graph, which is literally what's happening.

### Also covered

Per-component interaction specs with empty/loading/error states · **built-for-video constraints** (nothing under 12px, status never color-only, test a compressed clip on a phone) · accessibility floor · a 10-item anti-slop checklist (no purple gradients, no Inter/Roboto display face, no emoji iconography, no "AI-powered" copy, no glassmorphism).

---

<a name="phase-8"></a>
## Phase 8 — Sprint plan & Day-0 skeleton

**Produced:** `SPRINT.md` + 16 skeleton files.

### Timeline

Flagged that the 5-week plan assumed a Jul 15 start; work began Jul 31, leaving 16 days to the Aug 16 submit target. **Ashfaq's call: the remaining time is sufficient — prioritize completeness over cutting.** `SPRINT.md` was accordingly restaged: nothing deleted, extensions ordered by value-per-hour (dry-run → webhook → recheck_suspect → approvals → postmortems → insights → SNS fan-out), all three extension tables shipping Day 0 regardless so no feature ever needs a migration.

Three schedule changes from the original: deploy moved Day 12 → **Day 7** (SSE-through-CloudFront is the biggest unknown; discovering it late ends the project), EXPLAIN gate to **Day 3**, code freeze **Day 13** leaving three full days for README/video/submission.

### Day-0 skeleton delivered

| File | Purpose |
|---|---|
| `migrations/001_schema.sql` | All 10 spec tables + 3 extension tables, with `awaiting_approval` and `postmortem` outbox kind present from the start |
| `migrations/002_seed.sql` | Idempotent; 5 rules at v1, 6 services, 12 incidents spanning every decision path |
| `backend/app/core/models.py` | Full type vocabulary — `Fresh \| Stale` carries `stale_deps`, `TOOL_RISK` static map |
| `backend/app/core/contracts.py` | Every contract function with stub bodies returning realistic canned data |
| `backend/app/db.py` | `run_txn` with 40001 retry + jittered backoff, `q`, `one` — **frozen, Track B imports this** |
| `backend/app/bus.py` | `InterruptBus`, `SSEBroadcaster`, frozen SSE topic constants — **frozen, Track B imports this** |
| `backend/app/config.py`, `.env.example` | Mirrors spec §2.1.3 |
| `backend/pyproject.toml`, `Dockerfile` | amd64-pinned for Fargate |
| `docker-compose.yml`, `Makefile` | `make up && make reset` gives a seeded local DB |
| `.gitattributes`, `.gitignore`, `LICENSE` | LF endings, secret protection, MIT |
| `backend/app/main.py` | Lifespan + health + CORS; routers commented in |

---

<a name="artifacts"></a>
## Artifact inventory

| File | What it is | Status |
|---|---|---|
| `CASCADE_BUILD_SPEC.md` | **Ground truth.** v3.1 — architecture, schema, all decisions D1–D8, connection map | Authoritative |
| `SPRINT.md` | Day-by-day schedule; supersedes week tables elsewhere | Active |
| `Cascade_task_split.md` | v3 — ownership, D-1→D-7 decisions, interface contract | Active |
| `WORKFLOW.md` | Branching, merge order, integration points, conflict playbook | Active |
| `FRONTEND_DESIGN.md` | UI/UX spec for Track A | Active |
| `SETUP.md` | Accounts, toolchain, costs, readiness gate | Active |
| `Session.md` | This record | — |
| `Update.md`, `Changes.md` | Earlier review notes | Historical |

**Precedence:** spec → sprint → split → workflow/frontend. If any two disagree, the higher one wins and whoever spots it fixes the lower in the same PR.

---

<a name="decisions"></a>
## Binding decisions — do not regress

1. **Domain is SRE incident-response runbooks** (D7). No refund terminology anywhere.
2. **CloudFront fronts the ALB.** `NEXT_PUBLIC_API_URL` is never the raw ALB URL.
3. **L2 `<->` everywhere.** `<=>` and `<#>` are banned. Titan V2 with `normalize: true`.
4. **Escalation is a success** — task `succeeded` + `result='escalated'`, episode `success`, compile enqueued.
5. **Reset truncates `rules`**; `audit_log` is preserved.
6. **Bedrock IDs pinned:** `anthropic.claude-sonnet-5` / `anthropic.claude-haiku-4-5` / `amazon.titan-embed-text-v2:0`, via `AnthropicBedrockMantle`.
7. **Freshness returns `Fresh | Stale`,** never a bool.
8. **Postmortems run in the worker,** never inside `run_task`.
9. **Both contract directions are frozen** — `core/contracts.py` *and* `db.py`/`bus.py`.
10. **Stub bodies from Day 0**; `CASCADE_STUB_MODE` is the integration switch.
11. **Never cut:** point-of-use freshness gate · cascade txn · guided-vs-cold metrics · interrupt demo · Ops Copilot panel · MCP dev-workflow footage.

---

<a name="open"></a>
## Open items

**Immediate (Ashfaq)**
- [ ] **Bedrock model access request** — the only item with a 24h delay tail
- [ ] AWS: MFA on root, IAM user `cascade-dev`, `aws configure`, $50 billing alarm
- [ ] CockroachDB Cloud cluster on `us-east-1`; **verify `CREATE VECTOR INDEX` works**; locate the MCP config snippet
- [ ] GitHub repo public + MIT license set in the **About panel**
- [ ] Commit skeleton; `make up && make reset` green
- [ ] Send Shawki the four docs; confirm D-1 → D-7 today

**Not yet written**
- `.github/workflows/test.yml` — note CockroachDB **cannot** be a `services:` container (command can't be overridden); needs an explicit `docker run` step
- `frontend/` scaffold
- `backend/app/routers/*` — `tasks.py` + SSE endpoint is Day 1
- `backend/worker/handler.py` — needs a `--once` local mode
- `infra/scripts/01..05`, `infra/policies/`
- `docs/` contents

**Empirical unknowns the gates exist to measure**
- Whether the EXPLAIN plan uses `pb_embed_idx` with `<->` (Day 3)
- The real L2 distance threshold — 0.85 is a derived starting point, tune Day 6
- Whether the guided-vs-cold delta reaches ≥3× (Day 6 stop-the-world gate)
- Whether SSE survives CloudFront (Day 7 — the biggest deploy unknown)

*End of session record.*
