# Cascade — 16-Day Sprint Plan (Jul 31 → Aug 16)

**This document supersedes the week-by-week tables in `Cascade_task_split.md`
and `WORKFLOW.md`.** Everything else in those files — ownership, contracts,
merge order, integration points — still applies exactly as written.

| | |
|---|---|
| **Today** | Fri Jul 31 |
| **Submit target** | **Sun Aug 16** (≥48h early, per spec §16) |
| **Hard deadline** | Tue Aug 18, 5:00 PM EDT |
| **Working days** | 16 |

---

## Scope staging

The original plan had 5 weeks; this one has 16 days. Nothing is deleted — the
schema, contracts, and stubs for every extension ship on Day 0. What changes is
**ordering**: the MVP thin-slice (**learn → reuse → unlearn**) plus a deployed
HTTPS demo plus a video is the committed deliverable, and extensions are built
on top of it in priority order once the Day-11 gate is green.

### Extension priority order (build in this sequence, stop wherever you run out of runway)

Per decision D-6 in the task split, most valuable first:

1. **Dry-run modal** — cheapest by far. `simulate_rule_change` is the existing impact join without the commit, and the modal is a UI state in front of a button that already exists. High demo value per hour spent.
2. **Webhook incident ingestion** — one thin router that calls the same `run_task` as the manual POST. Makes the loop feel closed.
3. **`recheck_suspect` LLM job** — the amber quarantine flag is already in the demo; this makes the recovery automatic instead of manual.
4. **Approvals / autonomy gating** — highest narrative value of the remaining set (a human in the loop), but the most moving parts: pause/resume, durable state, a new UI surface.
5. **Postmortems** — one Bedrock call in the worker plus a markdown viewer.
6. **Insights feed** — most speculative; needs enough episode history to detect a pattern at all.
7. **SNS multi-instance fan-out** — implemented but flag-off per the spec; only matters above one ECS task.

**All three extension tables ship in the Day-0 schema regardless.** They cost
nothing to create and mean adding any feature later never requires a migration.

### What is *not* cuttable (spec D8)

Point-of-use freshness gate · the O(1) cascade transaction · guided-vs-cold
metrics · the interrupt demo · **Ops Copilot panel** · **MCP dev-workflow footage**.

The Copilot stays because it's the only place a judge *sees* MCP-adjacent
LLM↔database work inside the product. It's roughly 150 lines — one Claude call,
a SQL validator, a table. Do not cut it.

---

## The 16 days

| Day | Date | Ashfaq (Shell) | Shawki (Engine) | Gate |
|---|---|---|---|---|
| **0** | **Fri Jul 31** | **Bedrock access request (first 10 min)** · AWS IAM user · CRDB cluster · GitHub public repo + MIT · toolchain install | Review Day-0 skeleton · agree D-1→D-7 | Contract PR merged |
| 1 | Sat Aug 1 | `main.py`, `config.py`, `routers/tasks.py`, SSE endpoint | `core/tools.py` (5 tools), `core/llm.py` | Bedrock smoke call works |
| 2 | Sun Aug 2 | UI shell + design tokens + MetricBar + Console (stub data) | `core/executor.py` explore loop, episode write | — |
| 3 | Mon Aug 3 | StepStream + SSE wiring · **hello-world container on ECS** | `core/retrieval.py` embed + Phase-1 ANN · `docs/query-plans.md` | **EXPLAIN proves `pb_embed_idx` + `<->`** |
| 4 | Tue Aug 4 | `routers/metrics.py` + `routers/playbooks.py` | `core/compiler.py` + PlaybookSpec validation | **INC-1001 resolves end-to-end** |
| 5 | Wed Aug 5 | RunbookLibrary + cards + provenance | `core/freshness.py` + retrieval phases 2–3 | — |
| 6 | Thu Aug 6 | MetricBar on real data · onboarding rail ①② | `core/confidence.py` + guided path | **≥3× delta visible — STOP-THE-WORLD gate** |
| 7 | Fri Aug 7 | **Real deploy: ECS + ALB + CloudFront + Amplify** | `core/cascade.py` (rule-change txn) | **HTTPS live, SSE works through CloudFront** |
| 8 | Sat Aug 8 | `routers/rules.py` + `/api/impact` + `/internal/sse` | Interrupts in `executor.py` + scratchpad + re-plan | — |
| 9 | Sun Aug 9 | PolicyPanel + impact preview + confirm dialog | `worker/handler.py` + `jobs.py` + SQS/Lambda | — |
| 10 | Mon Aug 10 | **Cascade choreography** + interrupt banner + toasts | `relearn` job → v2 compile + lineage | — |
| 11 | Tue Aug 11 | Ops Copilot panel | Copilot SQL synthesis + validator | **MVP THIN-SLICE COMPLETE** |
| 12 | Wed Aug 12 | Admin reset · empty/loading/error states · onboarding ③ | Edge-matrix audit · `docs/skills-review.md` | Reset returns clean v1 world |
| 13 | Thu Aug 13 | Deploy final · video-legibility pass · a11y pass | Bug fixes only | **CODE FREEZE 6pm** |
| 14 | Fri Aug 14 | README (spec §13) · `docs/architecture.png` · DEVIATIONS.md | Review README technical sections | Stranger completes the tour |
| 15 | Sat Aug 15 | **Record + cut video (<3:00)** · upload public · test logged-out | Narrate engine beats | Video live |
| 16 | **Sun Aug 16** | `POST /api/admin/reset` · final smoke · **SUBMIT DEVPOST** | Verify repo/license/About | ✅ Submitted |

**Buffer:** Aug 17–18 exist only as emergency overflow. Plan to never use them.

---

## Three changes from the original plan, and why

1. **Deploy moved from Day 12 → Day 7.** The single biggest unknown in this
   stack is whether SSE survives CloudFront. Discovering that on Aug 13 ends
   the project; discovering it on Aug 7 costs an afternoon. Deploy whatever
   exists at the midpoint, then redeploy continuously.

2. **The EXPLAIN gate moved to Day 3** (it was Week 1 = up to 7 days). If the
   vector index isn't used, the retrieval story collapses and you need every
   remaining day to fix it.

3. **Code freeze is Day 13, not Day 15.** Three full days for README, diagram,
   video, and submission is not padding — it's the part that's actually graded.
   Teams lose hackathons by coding until the last night and submitting a
   rushed video.

---

## Your next 3 hours (Ashfaq, right now)

Do these in this exact order. The first one has a 24-hour tail and blocks everything.

1. **[10 min] AWS → Bedrock → Model access → request Anthropic Claude (Sonnet + Haiku) + Amazon Titan Text Embeddings V2, region `us-east-1`.** Submit the use-case form if prompted. Nothing else in this project works until this is granted, and it can take a day.
2. **[15 min] Message Shawki:** timeline is 16 days, extensions are cut, here are the D-1→D-7 defaults — confirm or object today. Send him `SPRINT.md`, `Cascade_task_split.md`, `WORKFLOW.md`.
3. **[20 min] AWS account hygiene:** enable MFA on root, create IAM user `cascade-dev` with `AdministratorAccess`, generate access keys, `aws configure`, verify with `aws sts get-caller-identity`. Set a $50 billing alarm.
4. **[20 min] CockroachDB Cloud:** create serverless cluster `cascade` on AWS `us-east-1`. Create the three SQL users. Copy the connection strings. **Verify `CREATE VECTOR INDEX` works** and locate the Managed MCP Server config snippet.
5. **[15 min] GitHub:** make this repo **public**, add MIT `LICENSE`, **set the license in the About panel** (contest requirement — judges check).
6. **[45 min] Toolchain:** Python 3.12, Node 20, Docker Desktop, AWS CLI v2, ccloud, cockroach binary. Verify each. Start local CRDB in Docker.
7. **[30 min] Commit the Day-0 skeleton** (already written for you — see below), run `make seed` locally, confirm green.

By tonight you should be able to run `docker compose up`, apply migrations, and
hit a FastAPI health endpoint. That's Day 0 done.

---

## Daily discipline (non-negotiable at this pace)

- **10-minute standup every morning.** What merged, what's merging, anything touching the contract.
- **Merge every day.** Nothing sleeps unmerged. At 16 days, a two-day branch is a catastrophe.
- **Record 60 seconds of fallback footage every evening** from Day 4 onward. If the live demo dies on Aug 15, you still have a video.
- **If a gate fails, stop and fix it.** Do not build forward on a broken foundation — there is no time to unwind it later.

*End of sprint plan.*
