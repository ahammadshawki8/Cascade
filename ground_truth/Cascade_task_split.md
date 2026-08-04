# Cascade — Work Split v3 (Ashfaq: Shell · Shawki: Engine)

**Ground truth is `CASCADE_BUILD_SPEC.md` v3.1.** This document only says *who
builds what, when, and where the two halves meet*. If this file and the spec
ever disagree, **the spec wins** — and whoever spots the disagreement fixes
this file in the same PR.

Companion docs: `WORKFLOW.md` (branching, merge order, integration checklist)
and `FRONTEND_DESIGN.md` (UI/UX spec for Track A).

---

## What changed from v2 (read this first — 9 spec conflicts + 5 orphaned artifacts)

v2's structure was right. These are corrections, not a redesign.

| # | v2 said | Problem against spec v3.1 | v3 fix |
|---|---|---|---|
| 1 | `is_fresh(playbook_id) -> bool` | Spec §5.6 returns `Fresh \| Stale(stale_deps)`. A bool throws away the stale-dep list the UI needs for "why", and that `recheck_suspect` needs to enqueue. | Contract now returns the rich type |
| 2 | `change_rule(rule_key, new_value)` | Spec §5.8 takes `(rule_key, new_body, new_params, actor)`. Rules have **both** body text and JSONB params, and `actor` is required for the audit row. | Signature corrected |
| 3 | `find_candidate(task_text)` | Spec §5.5 names it `retrieve()` returning `PlaybookCandidate`. Two names for one function = a guaranteed import break. | Renamed to match spec |
| 4 | Postmortem generated "at the tail end of `run_task`" | Adds a Bedrock call **inside the measured task path** → inflates `episodes.latency_ms` → **corrupts the Week-2 cold-vs-guided money metric**. | Postmortem is an **outbox event**, generated in the worker |
| 5 | `notify_oncall` "gets a real webhook POST" | Spec edge-case #15 guarantees "mock world has zero external dependencies." A live outbound call can hang or fail mid-demo. | Behind `ENABLE_OUTBOUND_WEBHOOK` (default **false**), 2s timeout, failures swallowed + logged, never blocks the tool result |
| 6 | Insights job on "the existing 60s sweeper cadence" | Pattern-scan every 60s is wasteful and adds cost. Spec §7 already has a daily-guard pattern (`audit_log` marker row) for idle decay. | Insights reuses the **daily guard**, not the 60s tick |
| 7 | Approval pause via `await asyncio.Event` | Two collisions: (a) spec §5.4's **60s wall-clock budget** would kill a task waiting on a human; (b) an in-memory Event dies on ECS redeploy → task hangs forever. | Approval wait is **excluded from the budget clock**; task parks in a new durable status and resumes from DB state, not only from memory |
| 8 | 3 new tables "additive, no MVP change" | Spec §8's `/api/admin/reset` has an **explicit TRUNCATE list**. New tables not in it → demo reset leaves stale approvals/insights/postmortems. | All three added to the reset list (§8 + §4.1 of the spec must be patched in the same PR) |
| 9 | Week 5 = "postmortems + insights + notifications + full journey" | Spec §14 Week 5 is **hardening + README + video + submit ≥48h early**. v2's Week 5 leaves no room for the deliverables that are actually graded. | **All extensions land by end of Week 4.** Week 5 is frozen for polish and submission |

**Five artifacts nobody owned in v2** — now assigned below: `migrations/*.sql`,
`docs/query-plans.md`, `docs/skills-review.md` + `docs/architecture.png`,
the test suite, and the README + demo video.

---

## Day-0 decisions — agree on these before writing code

Each has a recommended default. Take the default unless one of you objects;
record the answer in the row and commit this file.

| # | Decision | Options | Recommended | Agreed? |
|---|---|---|---|---|
| D-1 | Paused-for-approval task status | (a) stays `running` (b) new `awaiting_approval` enum value | **(b)** — `running` would make the partial index `tasks_running_idx` and the cascade interrupt logic treat a parked task as live. Add `'awaiting_approval'` to the `tasks.status` CHECK in the Day-0 schema so it's never an ALTER later. | ☐ |
| D-2 | Where does an action's **risk tag** come from for `decide_autonomy`? | (a) new field on `Step` (b) static map `tool → risk` in `confidence.py` | **(b)** — a static map (`apply_remediation`=high, `notify_oncall`=low, reads=none) needs no schema/compiler change and can't be hallucinated by the LLM. | ☐ |
| D-3 | Webhook ingestion auth (`POST /api/webhooks/incident`) | (a) open (b) shared-secret header | **(b)** `X-Webhook-Secret`, same Secrets Manager pattern as `X-Internal-Secret`. An open mutating endpoint on a public demo URL is a needless risk. | ☐ |
| D-4 | Postmortem storage | (a) markdown in a CRDB column (b) S3 + pointer row | **(b)** — reuses the existing `episodes/{id}.json` S3 pattern and keeps row sizes small. | ☐ |
| D-5 | Stub strategy for parallel work | (a) Ashfaq writes his own stubs, swaps imports later (b) Shawki commits **real files with stub bodies** on Day 0 | **(b)** — see `WORKFLOW.md` §2. There is then **no import swap ever**; integration = a function body gets filled, and Track A's code never changes. This removes an entire class of merge bugs. | ☐ |
| D-6 | Extension cut line | — | If the **Week-3 MVP gate** slips by more than 2 days, cut extensions in this order: notifications → insights → postmortems → approvals → dry-run → webhook ingestion. Dry-run and webhook are cheapest to keep. | ☐ |
| D-7 | Who runs the AWS account | — | **Ashfaq** (owns infra). Shawki gets an IAM user with Bedrock + read access only; he never needs deploy rights. | ☐ |

---

## The full user journey (reference this when unsure where a feature belongs)

1. **Incident arrives** — webhook (Ext) or manual POST (MVP)
2. **Agent learns** (explore mode) if no playbook exists — MVP
3. **Compiles a playbook** with provenance to the rules it used — MVP
4. **Reuse, confidence-gated** (Ext): high-confidence + low-risk → auto-executes; otherwise pauses for human approval
5. **Incident resolves → postmortem auto-generated** (Ext) from the episode trajectory
6. **Trend detection** (Ext) notices patterns, surfaces a suggestion
7. **Human clicks the suggestion** → Policy Panel with a rule change pre-filled — MVP panel, Ext entry point
8. **Dry-run impact simulation** (Ext) — see what would break before committing
9. **Commit → cascade/unlearn fires** — MVP (D1)
10. **Quarantine + relearn v2** — MVP
11. **Notification goes out** (Ext) — closing the loop back to a human

---

## Schema — one file, one owner, one Day-0 PR

**`migrations/001_schema.sql` and `002_seed.sql` are owned by Shawki**
(the schema is the engine's contract), but they are **merged on Day 0 in the
joint contract PR** and are **frozen** afterwards. Any later change is a
"contract PR" both people approve (`WORKFLOW.md` §3).

Day-0 schema = spec §4 tables **plus** these three extension tables **plus**
the D-1 enum value, all written up front so no migration is ever needed mid-project:

```sql
CREATE TABLE approvals (
  approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     UUID NOT NULL REFERENCES tasks (task_id),
  playbook_id UUID REFERENCES playbooks (playbook_id),
  step_index  INT NOT NULL,
  action      STRING NOT NULL,
  status      STRING NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','approved','rejected','expired')),
  reason      STRING,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at  TIMESTAMPTZ, resolved_by STRING
);
CREATE INDEX approvals_pending_idx ON approvals (requested_at) WHERE status = 'pending';

CREATE TABLE insights (
  insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind    STRING NOT NULL,
  summary STRING NOT NULL,
  related_rule_key STRING,
  suggested_params JSONB,           -- pre-fills the Policy Panel form (journey step 7)
  evidence JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dismissed BOOL NOT NULL DEFAULT false
);

CREATE TABLE postmortems (
  postmortem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id UUID NOT NULL UNIQUE REFERENCES episodes (episode_id),
  s3_key     STRING NOT NULL,       -- D-4: markdown in S3
  summary    STRING NOT NULL,       -- one-line teaser for list views
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Also in the same Day-0 PR:
- `tasks.status` CHECK gains `'awaiting_approval'` (D-1)
- `outbox.kind` CHECK gains `'postmortem'` (fix #4)
- **Spec §4.1 + §8 reset TRUNCATE list gains** `approvals, insights, postmortems` (fix #8)

---

## Track A — Ashfaq: Shell (API + Frontend + Infra)

Moves data around, renders it, never owns the intelligence. Calls Track B's functions.

**Backend — `backend/app/`** (owns exclusively)
- `main.py`, `config.py`, `db.py`, `bus.py`
- `routers/`: `tasks.py`, `rules.py`, `playbooks.py`, `metrics.py`, `admin.py`, `copilot.py`
- Extensions: `routers/incidents.py` (webhook ingest), `approvals.py`, `insights.py`, `postmortems.py`; `rules.py` gains `POST /api/rules/{key}/dry-run`

**Frontend — `frontend/`** (owns exclusively) — build to `FRONTEND_DESIGN.md`
- MVP: metric bar, onboarding rail, Incident Console, Runbook Library, Policy Panel, Ops Copilot, SSE
- Extensions: approval queue, postmortem viewer, insights feed, dry-run modal, notification settings
  — all in the **right rail / modals**, never as new grid cells (see `FRONTEND_DESIGN.md` §4)

**Infra — `infra/`** (owns exclusively)
- `scripts/01..05`, `policies/`, ECS/ALB/CloudFront/Amplify, Secrets Manager, SQS/Lambda/EventBridge wiring, CI workflow
- **Also owns:** AWS account, Bedrock model-access request (spec §12 step 0), billing alarms, `.env.example`

**Newly assigned artifacts**
- `README.md` (spec §13) — Ashfaq drafts, Shawki reviews the technical sections
- `docs/architecture.png` — Ashfaq
- **Demo video** (spec §15) — Ashfaq records/edits; Shawki narrates the engine beats
- Integration tests in `backend/app/tests/integration/` — Ashfaq (they exercise routers end-to-end)

**Exit tests**
- Wk1: `POST /api/tasks` works end-to-end against stub bodies; hello-world container on ECS
- Wk2: metric bar shows the real cold-vs-guided delta
- Wk3: rule edit → dependent cards flip red live via SSE
- Wk4: webhook creates a task; approval queue blocks/unblocks a paused task; dry-run modal previews before commit; **live on HTTPS**
- Wk5: README tour walkable by a stranger; video cut and public

---

## Track B — Shawki: Core Memory & AI Engine

**`backend/app/core/`** (owns exclusively)
- `models.py`, `contracts.py`, `retrieval.py`, `freshness.py`, `executor.py`, `tools.py`, `compiler.py`, `confidence.py`, `cascade.py`, `llm.py`
- Extensions: `postmortem.py`, `insights.py`; behavior added *inside* existing files for autonomy gating, pause/resume, simulate mode

**`backend/worker/`** (owns exclusively) — `handler.py`, `jobs.py` (+ `postmortem` and daily `insights` jobs)

**`migrations/`** (owns exclusively, frozen after Day 0)

**Newly assigned artifacts**
- `docs/query-plans.md` — Shawki (it's the Week-1 EXPLAIN gate)
- `docs/skills-review.md` — Shawki (Agent Skills run against our own cluster)
- Unit tests in `backend/app/tests/unit/` — Shawki
- Bedrock fixture recordings for CI — Shawki

**Extension behavior (corrected per fixes #4–#7)**
- **`confidence.py`** gains `decide_autonomy(playbook, step) -> AUTO_EXECUTE | REQUIRES_APPROVAL`, using the static risk map (D-2)
- **`executor.py`** gains pause/resume: on `REQUIRES_APPROVAL` → insert `approvals` row, set task `awaiting_approval`, emit `approval.requested`, **stop the budget clock**, and return. Resume is triggered by `resolve_approval()` and **reloads state from the DB** (so an ECS restart mid-approval is survivable); the in-memory `InterruptBus` Event is a fast path, not the source of truth.
- **`postmortem.py`** — `generate_postmortem(episode_id) -> str`. Enqueued as an **outbox `postmortem` event** when a task resolves; runs in the worker. Never inside `run_task`.
- **`insights.py`** — daily-guarded worker job (same `audit_log` marker pattern as idle decay). Read-only scan → `insights` row with `suggested_params` that pre-fill the Policy Panel.
- **`cascade.py`** gains `simulate_rule_change(...)` — the existing `/api/impact` join without the commit.
- **`tools.py`**'s `notify_oncall` gains an optional outbound POST behind `ENABLE_OUTBOUND_WEBHOOK` (default false, 2s timeout, failure never propagates).

**Exit tests**
- Wk1: `docs/query-plans.md` proves `pb_embed_idx` used with `<->`; explore loop resolves INC-1001
- Wk2: guided run ≥3× faster — **stop-the-world gate**
- Wk3: full learn→reuse→unlearn works end to end
- Wk4: a low-confidence task pauses for approval and survives an API restart; dry-run returns correct impact without writing rows
- Wk5: postmortem coherent; synthetic repeat pattern yields an insight; **no new features**

---

## The Interface Contract (`backend/app/core/contracts.py` — frozen Day 0)

Signatures corrected to match spec v3.1 exactly (fixes #1–#3). This file is
the *only* thing Track A imports from Track B.

```python
# ---------- MVP contract ----------
async def retrieve(task_text: str) -> PlaybookCandidate | None: ...
async def check_freshness(playbook_id: str) -> Fresh | Stale: ...   # NOT bool — carries stale_deps
async def run_task(task_id: str) -> None: ...
async def change_rule(rule_key: str, new_body: str,
                      new_params: dict, actor: str) -> ImpactResult: ...
async def answer_analytics_question(question: str) -> CopilotAnswer: ...

# ---------- Extension contract (add after the Week-3 gate) ----------
def decide_autonomy(playbook: Playbook, step: Step) -> Literal["AUTO_EXECUTE", "REQUIRES_APPROVAL"]: ...
async def resolve_approval(approval_id: str,
                           decision: Literal["approved", "rejected"],
                           resolved_by: str) -> None: ...
async def generate_postmortem(episode_id: str) -> str: ...
async def list_insights(include_dismissed: bool = False) -> list[Insight]: ...
async def dismiss_insight(insight_id: str) -> None: ...
async def simulate_rule_change(rule_key: str, new_body: str,
                               new_params: dict) -> ImpactResult: ...
```

**Shared types** (`Playbook`, `PlaybookCandidate`, `Fresh`, `Stale`, `ImpactResult`,
`CopilotAnswer`, `Insight`, `Step`) live in `core/models.py`, owned by Shawki,
frozen Day 0, changed only via a contract PR.

**SSE event names** are part of the contract too (spec §5.2), because the
frontend subscribes by string. Frozen Day 0:
`task.{id}.step` · `task.{id}.status` · `rule.changed` · `playbook.changed` ·
`metrics.tick` · **`approval.requested`** · **`insight.created`**

---

## Week-by-week joint gates

| Week | Joint gate | If it fails |
|---|---|---|
| 1 | Vector index proven via EXPLAIN; a task POSTs end-to-end | Fix the index/operator before anything else |
| 2 | Guided run visibly ≥3× faster | **Stop all feature work.** Nothing else matters until this is visible |
| 3 | **MVP thin-slice**: learn → reuse → unlearn, ugly UI fine. Extensions unlock here | Slipped >2 days → apply the D-6 cut order |
| 4 | Extensions in; **deployed live on HTTPS**; a stranger follows the README | Cut remaining extensions, keep the deploy |
| 5 | **Code freeze Day 2.** Video, README, diagram, submit by Aug 16 5 PM EDT | Nothing is worth missing the deadline |

**Never cut** (spec D8): point-of-use freshness gate · cascade txn ·
guided-vs-cold metrics · interrupt demo · Ops Copilot panel · MCP dev-workflow footage.

*End of split.*
