# Cascade — Working Agreement, Merge Order & Integration Runbook

Two people, five weeks, one hard deadline (**Aug 18, 5:00 PM EDT** — we submit
**Aug 16**). This document exists to answer one question at any moment:
*"I finished a thing. What do I merge, in what order, and what do I do next
so nothing breaks?"*

- **Ashfaq** — Track A (Shell): `backend/app/` routers + `main.py`/`db.py`/`bus.py`/`config.py`, `frontend/`, `infra/`, AWS account, README, video
- **Shawki** — Track B (Engine): `backend/app/core/`, `backend/worker/`, `migrations/`, `docs/query-plans.md`, `docs/skills-review.md`

---

## 1. The conflict surface (the only files that can ever collide)

With strict directory ownership, **95% of this project cannot produce a merge
conflict**. These are the exceptions — the entire list:

| File | Owner | Rule |
|---|---|---|
| `migrations/001_schema.sql`, `002_seed.sql` | Shawki | **Frozen after Day 0.** Any change = contract PR |
| `backend/app/core/contracts.py` | Shawki | Signatures Track A imports. Frozen Day 0 |
| `backend/app/core/models.py` | Shawki | Shared types. Frozen Day 0 |
| `backend/app/db.py` — `run_txn()`, `q()` | Ashfaq | ⚠️ **Track B imports these.** Public surface frozen Day 0 |
| `backend/app/bus.py` — `InterruptBus`, `SSEBroadcaster` | Ashfaq | ⚠️ **Track B imports these.** Public surface frozen Day 0 |
| `backend/pyproject.toml` | Ashfaq | Adding a dep = ping the other person in chat, then push |
| `.env.example`, `docker-compose.yml` | Ashfaq | Adding a var = ping, then push |
| `CASCADE_BUILD_SPEC.md`, `Cascade_task_split.md`, this file | Joint | Contract PR |
| `README.md` | Ashfaq | Shawki reviews technical sections only |

> **The bidirectional dependency v2 missed:** Track A imports `core/contracts.py`,
> and Track B imports `app/db.py` + `app/bus.py`. The contract runs **both
> directions**. If Ashfaq changes `run_txn`'s signature in Week 3, every file
> Shawki owns breaks. Freeze both surfaces on Day 0.

Everything else — every router, every core module, every component — has
exactly one owner and will never conflict.

---

## 2. The Day-0 skeleton: why there is never an "import swap"

**The single most important mechanic in this plan.** (Decision D-5 in the split.)

On Day 0, Shawki commits **every file Track A will ever import, with real
signatures and stub bodies that return realistic canned data**:

```python
# backend/app/core/contracts.py  — Day 0, stub body
import os
STUB = os.getenv("CASCADE_STUB_MODE") == "true"

async def retrieve(task_text: str) -> PlaybookCandidate | None:
    if STUB:
        return PlaybookCandidate(
            playbook_id="00000000-0000-0000-0000-000000000001",
            name="Rollback bad deploy", version=1, confidence=0.72,
            distance=0.41, status_cache="active",
        )
    raise NotImplementedError
```

Consequences, all good:

- Ashfaq builds the **entire UI and every router on Day 1** against data that
  looks real — cards render, the metric bar has numbers, the library has rows.
- When Shawki fills a body, **Ashfaq changes nothing.** No import swap, no
  find-and-replace, no "integration day."
- `CASCADE_STUB_MODE=true` in `.env` is the toggle. Flip it to `false` and
  you're running the real engine. That flip *is* the integration test.
- Frontend work is never blocked on engine work, and vice versa.

**Rule:** Shawki never changes a signature after Day 0 without a contract PR.
Filling a body is a normal PR. Changing the shape is a joint decision.

---

## 3. Branching & PR rules

```bash
# Always branch. Branches are free and give you a revert point.
git checkout main && git pull
git checkout -b feat/engine/compiler        # Shawki
git checkout -b feat/shell/policy-panel     # Ashfaq
git checkout -b contract/add-approvals      # either, for shared files
```

Naming: `feat/engine/*` · `feat/shell/*` · `fix/*` · `contract/*` · `docs/*`

| Lane | What | Review | Merge |
|---|---|---|---|
| **Fast lane** | Only files you own | None needed | Self-merge once CI is green |
| **Contract lane** | Anything in §1's table | **Other person must approve** | After approval + CI |

**PR size:** one logical unit, ideally under ~400 lines. A PR that sits open
more than 24 hours is a problem — split it. Long-lived branches are how
two-person projects generate week-five merge hell.

**Never:** force-push to `main`; merge with red CI; rebase a branch the other
person has pulled.

**Windows note (Ashfaq):** `.gitattributes` with `*.sh text eol=lf` must land in
the Day-0 PR, or Shawki's bash scripts arrive with CRLF and fail with
`$'\r': command not found`.

---

## 4. Contract PR process (the only ceremony we keep)

Triggered by: a schema change, a signature change, a new SSE event name, a new
shared type, a new env var that both sides read, or a change to `/internal/sse`'s payload.

1. **Propose in chat first** — one message, what and why. No surprise PRs on shared files.
2. Branch `contract/<thing>`. Change **only** contract files — no feature code mixed in.
3. PR description states: what changed, who is affected, what they must update.
4. Other person approves (or objects) **same day**.
5. Merge. **Both people immediately `git pull` on all active branches.**
6. If it's a schema change: both run `make seed` locally to rebuild.

A contract PR should be mergeable in under an hour. If it's contentious, it's
probably two changes — split it.

---

## 5. Merge order & integration points, week by week

The rule that prevents every ordering bug: **contract → engine → shell.**
Shawki's body-fill merges before Ashfaq's consuming code, so `main` is never
in a state where the shell calls something that doesn't exist.

### I0 — Day 0: the joint contract PR (do this together, one sitting, ~3 hours)

One PR, both present. Nothing else happens until it's merged.

**Contents:**
- Repo skeleton (spec §3 directory tree, empty files where needed)
- `migrations/001_schema.sql` — spec §4 tables **+** `approvals`/`insights`/`postmortems` **+** `tasks.status` gains `'awaiting_approval'` **+** `outbox.kind` gains `'postmortem'`
- `migrations/002_seed.sql` — spec §4.1, TRUNCATE list including the three new tables
- `core/models.py` + `core/contracts.py` with **stub bodies** (§2)
- `app/db.py` + `app/bus.py` with **real implementations** (Track B depends on these from Week 1)
- `pyproject.toml`, `package.json`, `Dockerfile`, `docker-compose.yml`
- `.env.example` (mirrors spec §2.1.3), `.gitattributes`, `LICENSE` (MIT), CI workflow
- The frozen SSE event-name list as a constant module both sides import

**Exit condition:** both people can run `docker compose up && make seed` and get
a green `pytest` on an empty test suite. **Ownership is frozen from this moment.**

---

### Week 1 — "a task runs"

| Order | Who | Merges | Contains |
|---|---|---|---|
| 1 | Shawki | `feat/engine/tools-llm` | `core/tools.py` (5 mock-world tools), `core/llm.py` (Bedrock clients, retries, budgets) |
| 2 | Shawki | `feat/engine/explore-loop` | `core/executor.py` explore path, episode write (DB + S3) |
| 3 | Shawki | `feat/engine/embed-phase1` | `core/retrieval.py` embed + Phase-1 ANN query; `docs/query-plans.md` |
| 4 | Ashfaq | `feat/shell/api-skeleton` | `main.py`, `config.py`, `routers/tasks.py`, `routers/metrics.py`, SSE endpoint |
| 5 | Ashfaq | `feat/shell/ui-shell` | Next.js app, metric bar, Incident Console, onboarding rail (stub data) |
| 6 | Ashfaq | `feat/shell/infra-spike` | hello-world container on ECS Fargate (proves the deploy path early) |

**🔗 Integration point I1 — `run_task`.** `routers/tasks.py` creates the task
row and launches `core.contracts.run_task(task_id)` as a background asyncio
task. Track B fills the body; Track A's code is unchanged.

**Ashfaq's end-to-end checklist:**
- [ ] `CASCADE_STUB_MODE=false` in local `.env`
- [ ] `POST /api/tasks {"input":"Remediate INC-1001"}` → 202 with a task_id
- [ ] SSE stream emits `task.{id}.step` rows as the executor runs
- [ ] `mock_action_log` has a remediation row; `episodes` has one row with `latency_ms > 0`
- [ ] Task ends `succeeded`, `result='remediated'`

**Joint gate:** the above passes **and** `docs/query-plans.md` shows `pb_embed_idx`
used with `<->`. If the index isn't used, everything stops until it is.

---

### Week 2 — "it learns and reuses"

| Order | Who | Merges | Contains |
|---|---|---|---|
| 1 | Shawki | `feat/engine/compiler` | `core/compiler.py`, PlaybookSpec validation, dedup, dep verification |
| 2 | Shawki | `feat/engine/freshness` | `core/freshness.py` (returns `Fresh \| Stale`) |
| 3 | Shawki | `feat/engine/guided-mode` | retrieval phases 2–3, `core/confidence.py`, guided path in `executor.py` |
| 4 | Ashfaq | `feat/shell/playbooks-api` | `routers/playbooks.py` (list/detail/lineage) |
| 5 | Ashfaq | `feat/shell/library-ui` | Runbook Library, provenance list, confidence bars |
| 6 | Ashfaq | `feat/shell/metrics` | `/api/metrics` aggregate + live metric bar |

**🔗 Integration point I2 — the metrics data contract.** `/api/metrics` is
Ashfaq's SQL over `episodes`, but the *columns* are written by Shawki's
executor. Agree the exact semantics before Ashfaq writes the aggregate:
`mode` ∈ `explore|guided`, `latency_ms` **excludes** compile time,
`steps` counts tool calls only.

**Ashfaq's end-to-end checklist:**
- [ ] Run INC-1001 (cold) → a runbook card appears with provenance
- [ ] Run INC-1002 → badge shows ⚡ Runbook, step count visibly lower
- [ ] Metric bar shows both columns and a delta percentage
- [ ] Delta is **≥3×** on steps and latency

**Joint gate:** ≥3× visible. **If not, all feature work stops** — this is the
demo's central claim and the spec's stop-the-world condition.

---

### Week 3 — "it unlearns" (tightest coupling of the project)

| Order | Who | Merges | Contains |
|---|---|---|---|
| 1 | **Joint** | `contract/sse-payloads` | Freeze the `/internal/sse` POST body shape (Lambda → API) **before** either side codes against it |
| 2 | Shawki | `feat/engine/cascade` | `core/cascade.py` — the O(1) rule-change txn + post-commit publish |
| 3 | Shawki | `feat/engine/interrupts` | Bus interrupt + durable flag checks in `executor.py`, scratchpad persist, re-plan |
| 4 | Shawki | `feat/engine/worker-jobs` | `worker/handler.py`, `jobs.py` (rule_changed, relearn, recheck, compile, sweeper) |
| 5 | Ashfaq | `feat/shell/rules-api` | `routers/rules.py`, `/api/impact`, `/internal/sse` receiver |
| 6 | Ashfaq | `feat/shell/policy-panel` | Policy Panel, impact preview, confirm dialog |
| 7 | Ashfaq | `feat/shell/cascade-ui` | SSE-driven card flips, interrupt banner, toasts |

**🔗 Integration point I3 — three contracts at once.** This week has the most
surface area: (a) `change_rule()` signature, (b) SSE event names/payloads,
(c) the Lambda→API `/internal/sse` HTTP shape. Item 1 in the table exists
precisely so (c) is settled before anyone codes.

**Ashfaq's end-to-end checklist:**
- [ ] Start a task; while it runs, change `incident.rollback_window` 24 → 4
- [ ] Running task shows the interrupt banner and re-plans under v2
- [ ] Dependent cards flip red within ~1s (SSE), others go amber (suspect)
- [ ] A **new** task submitted during the cascade falls back to explore (never executes stale)
- [ ] v2 runbook appears with lineage v1→v2 in under 60s
- [ ] `POST /api/admin/reset` returns the world to rules v1 and empty playbooks

**Joint gate — the MVP thin-slice.** Ugly UI is fine. **Extensions unlock only
after this passes.** If it slips more than 2 days, apply the D-6 cut order.

---

### Week 4 — extensions + go live

| Order | Who | Merges | Contains |
|---|---|---|---|
| 1 | **Joint** | `contract/extension-signatures` | Add the six extension functions to `contracts.py` **as stubs** |
| 2 | Ashfaq | `feat/shell/deploy` | `03_aws_bootstrap.sh` (ECS+ALB+**CloudFront**), `04`/`05` deploy scripts, Amplify |
| 3 | Shawki | `feat/engine/autonomy` | `decide_autonomy`, pause/resume, `resolve_approval` |
| 4 | Ashfaq | `feat/shell/approvals` | `routers/approvals.py` + approval queue UI |
| 5 | Shawki | `feat/engine/simulate` | `simulate_rule_change` |
| 6 | Ashfaq | `feat/shell/dryrun` | `/api/rules/{key}/dry-run` + dry-run modal |
| 7 | Shawki | `feat/engine/postmortem-insights` | `core/postmortem.py`, `core/insights.py`, worker jobs |
| 8 | Ashfaq | `feat/shell/rail` | Insights feed + postmortem viewer in the right rail |
| 9 | Ashfaq | `feat/shell/webhook` | `routers/incidents.py` with `X-Webhook-Secret` |

**Ashfaq's end-to-end checklist:**
- [ ] Public **HTTPS** URL live; browser console shows **zero mixed-content errors**
- [ ] SSE works *through CloudFront* (this is the #1 deploy surprise — test it the hour CloudFront goes up)
- [ ] Lambda → `/internal/sse` reaches the deployed API and cards flip in a browser you didn't start the task from
- [ ] A low-confidence task pauses; approving it from the UI resumes it
- [ ] Restart the ECS task while an approval is pending → approving still resumes it (durable resume, fix #7)
- [ ] A stranger follows the README 5-minute tour without asking you anything

---

### Week 5 — freeze and ship

| Day | What |
|---|---|
| Mon–Tue | Edge-matrix audit, load sanity, bug fixes only. **Code freeze end of Tuesday.** |
| Wed | README final, `docs/architecture.png`, `docs/skills-review.md`, DEVIATIONS.md |
| Thu | Record and cut the video (<3:00), upload public, test logged-out |
| **Fri Aug 16** | Run `POST /api/admin/reset`, final smoke test, **submit Devpost** |

After code freeze: **only** fixes for a broken demo path. No new features, no
refactors, no "quick improvements." The most common way hackathon teams lose
is a Thursday-night refactor that breaks Friday's demo.

---

## 6. Daily rhythm

- **Morning (10 min, both):** what I merged yesterday · what I'm merging today · anything that touches the contract. That third item is the whole point.
- **Before you start coding:** `git checkout main && git pull` — always.
- **Before you push:** `pytest` locally, then rebase onto latest `main`.
- **End of day:** merge what's green. Nothing sits unmerged overnight.
- **End of week:** both merge everything, run the joint gate together, record fallback footage (spec D8 #3).

---

## 7. When something conflicts anyway

Because ownership is strict, a conflict means one of three things:

| Symptom | Cause | Fix |
|---|---|---|
| Conflict in a file you don't own | Someone crossed a boundary | Revert their hunk, ping them. Don't "merge both" |
| Conflict in `migrations/*.sql` | Schema changed without a contract PR | Stop. Contract PR. Both re-run `make seed` |
| `ImportError` / `TypeError` on a core function | Signature drifted post-freeze | Shawki reverts to the frozen signature, then proposes the change properly |
| CI red on `main` | Someone merged without a green run | Whoever merged reverts immediately, fixes on a branch |

```bash
# Standard rebase flow
git checkout main && git pull
git checkout feat/shell/thing && git rebase main
# resolve, then
git push --force-with-lease   # only ever on YOUR OWN branch, never main
```

---

## 8. Pre-merge checklist (paste into the PR description)

```
- [ ] Only touches files I own (or it's a contract PR with approval)
- [ ] `pytest` green locally
- [ ] CI green
- [ ] No signature in contracts.py changed (or: contract PR, approved by @other)
- [ ] No new env var (or: added to .env.example AND spec §2.1.3 AND pinged)
- [ ] Rebased onto latest main
- [ ] Spec section this implements: §___
```

---

## 9. The one-page answer to "what do I do next?"

1. `git pull main`.
2. Is the thing I'm about to build in **my** directory? → branch, build, PR, self-merge.
3. Does it need a **new function from the other track**? → is the stub in `contracts.py`? If yes, build against it now. If no, it's a contract PR first.
4. Does it touch **schema, a signature, an SSE name, or `/internal/sse`**? → contract PR, other person approves, both pull.
5. Did I just finish a **week's worth**? → run that week's integration checklist in §5, then the joint gate, then record fallback footage.
6. Is it **Week 5, past Tuesday**? → the answer is no. Ship what works.

*End of workflow.*
