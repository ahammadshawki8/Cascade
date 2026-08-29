# Reproduction guide

Written for someone starting from a clean machine with nothing installed and no
accounts.

There are three paths, and they cost different amounts of your time. Pick the
first one that answers your question.

| | What it proves | Setup | Runtime |
|---|---|---|---|
| **A. Stub mode** | The API works, every endpoint answers | ~3 min, no database, no keys | seconds |
| **B. Full local** | The whole loop: learn, reuse, unlearn, refuse | ~15 min, Docker + a model key | ~10 min |
| **C. The evaluation** | The measured claim against two baselines | B, plus Bedrock access | ~25 min |

Path C is the one that produces the numbers in
[`IMPROVEMENT_CHANGELOG.md`](IMPROVEMENT_CHANGELOG.md). If you only have time
for one thing and you are checking whether the claims hold, do C.

---

## Versions

Pinned to what this was built and verified against.

| | Version |
|---|---|
| Python | 3.12 or newer (`requires-python = ">=3.12"`) |
| Node | 20 or newer |
| Next.js | 16.2.12 |
| React | 19.2.4 |
| CockroachDB | `cockroachdb/cockroach:latest`, single node, insecure |
| Docker | any recent version, for CockroachDB only |

Python 3.14 works and is what the latest runs used, with one caveat noted under
[Windows](#a-note-for-windows).

---

## Path A — Stub mode, no database, no keys

The fastest way to confirm the API is real. Every endpoint responds against
in-memory fixtures.

```bash
git clone https://github.com/ahammadshawki8/Cascade.git
cd Cascade/backend
pip install -e .
CASCADE_STUB_MODE=true python run_local.py
```

In another shell:

```bash
curl localhost:8000/health
curl localhost:8000/api/metrics
curl -X POST localhost:8000/api/tasks \
  -H 'content-type: application/json' \
  -d '{"input":"Remediate INC-1001"}'
```

**Expect:** `{"status":"ok"}`, a metrics object, and a `201` with a task id.

**What this does not prove:** anything about the actual engine. Stub mode
returns fixtures. That is why `verify_integration.py` refuses to run in it — a
green result that could have been canned is not evidence.

---

## Path B — Full local

### 1. Database

```bash
docker compose up -d crdb
make reset
```

`make reset` creates the database, applies the migrations **in dependency
order**, and seeds it.

Order matters and is not the numeric order. `006_platform.sql` adds the
`predicate` and `enforcement` columns, and `002_seed.sql` inserts into them, so
the seed runs last:

```
001 → 003 → 004 → 005 → 006 → 002
```

Applying them 001, 002, 003 ... fails on 002 with an undefined column. If you
are applying them by hand, use the order above.

**Expect:** `seed applied — rules at v1, 6 services, 12 incidents`.

### 2. A model provider

The engine runs on a provider chain: `bedrock → groq → openrouter → local` for
chat, `bedrock → huggingface → local` for embeddings. Any one of them is
enough to see the loop work.

```bash
cd backend
cp ../.env.example .env
```

Then set **one** of these in `backend/.env`:

```bash
# Easiest, free tier, no AWS account
GROQ_API_KEY=gsk_...
HF_API_KEY=hf_...

# Or, what the published numbers were measured on
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

Also set, for local runs:

```bash
DATABASE_URL=postgresql://root@localhost:26257/cascade?sslmode=disable
CASCADE_STUB_MODE=false
RUN_WORKER_IN_PROCESS=true
```

`RUN_WORKER_IN_PROCESS=true` matters. There is no SQS or Lambda on your
machine, so without it the compile event is queued and **no runbook ever
appears**, which looks like the system failing to learn. It must be `false` in a
real deployment or two consumers race.

### 3. Run it

```bash
cd backend && python run_local.py      # see the Windows note below
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000`.

### 4. Prove it

```bash
cd backend && python verify_integration.py
```

**Expect:** `109 passed, 0 failed, 1 skipped`. It refuses to run in stub mode
and talks to the engine directly rather than over HTTP, because the interrupt
case needs a task already carrying `interrupt_flag` before execution starts,
which is not reachable through the API without a race.

### 5. See the thing the project exists for

In the browser, in this order:

1. **Fix it** on `INC-1001` — explores, remediates, compiles a runbook
2. **Fix it** on `INC-1002` — reuses it, no model call on that path
3. **Policy** → `incident.rollback_window` → hours `24` → `4` → Commit
4. The runbook in **Procedures** turns `suspect`, its provenance dot greys out
5. **Fix it** on `INC-1009` — still the closest vector match, **refused anyway**

Step 5 is the claim. Everything else is setup for it.

---

## Path C — The evaluation

This is what produces the head-to-head numbers.

### What it does

Twelve seeded incidents, decided twice:

- **Phase 1** — `rollback_window = 24h`, the policy the runbooks were learned under
- **Phase 2** — the same world, `rollback_window = 4h`

24 decision points per arm, three arms, identical cases:

| Arm | What it is |
|---|---|
| `single_prompt` | One direct prompt. Incident plus current policy, decide. No memory |
| `naive_cache` | Store what worked, match it, replay it. No provenance |
| `cascade` | The system under test |

**Fairness.** Both baselines call `app.core.llm._chat` — the same function,
provider chain and model (`bedrock_agent_model_id`) as Cascade's own planner —
and both are handed the current policy with live parameter values on every
call. No arm gets a weaker model, and `naive_cache` in phase 2 is not guessing
at a rule it was never shown.

**Ground truth** is the seeded rule predicates applied by the shipped evaluator,
mirroring `check_remediation_eligibility`. It is data a human wrote in
`002_seed.sql`, not an opinion and not Cascade's answer.

**Primary metric:** policy-correct decision rate. For someone on call, success
is not speed, it is not running the wrong procedure. Secondary: unsafe-action
rate, latency, tokens.

**The challenging case** is `INC-1010`, deployed at exactly 24.0 hours. At the
boundary a `lte` comparison passes and a `lt` fails, which separates an arm that
evaluates the rule from one that has absorbed the general idea that 24 hours is
the limit.

### Run it

```bash
cd backend
python -m eval.run_eval --api http://127.0.0.1:8000 --admin-token dev-admin-token
```

Against a deployed stack instead:

```bash
python -m eval.run_eval --api https://<your-host> --admin-token <token>
```

Useful flags:

```bash
--arm baseline     # baselines only, no task execution
--arm cascade      # Cascade only, no Bedrock needed locally
--dry-run          # print the plan, call nothing
--keep             # do not restore the sample world afterwards
```

### Output

```
eval/out/results.json     every decision, scored
eval/out/RESULTS.md       the tables
```

The JSON is also what the **Evidence** view in the app renders, from
`frontend/src/data/eval-results.json`.

### What to expect

Phase 1 should be close for all three arms — everyone can read a rule. Phase 2
is the experiment. An arm holding a remembered procedure has to work out that
yesterday's correct answer is today's wrong one.

The result is reported as measured. If a baseline holds up in phase 2, the
report says so.

### Runtime and cost

| | |
|---|---|
| Wall clock | ~25 min, mostly the 24 live task executions |
| Model calls | 48 baseline calls, plus whatever the cold runs need |
| Cost on Bedrock | roughly $1–3 depending on how many runs go cold |
| Cost on Groq free tier | nothing, but expect 429s under back-to-back load |

### Trajectories

```bash
python -m eval.export_trajectories --api <host> --admin-token <token>
```

Writes `eval/out/AGENT_TRAJECTORIES.md` from `episodes.trajectory` — the calls
that actually happened, including the refused ones, rather than a write-up of
what an agent would have done.

---

## A note for Windows

Use `python run_local.py`, never bare `uvicorn`.

psycopg's async mode cannot drive Windows' default `ProactorEventLoop`, and as
of Python 3.14 `set_event_loop_policy` no longer influences the loop uvicorn
builds for itself. `run_local.py` constructs a selector loop explicitly. Linux
and macOS are unaffected, and the Dockerfile runs uvicorn directly.

The `make dev` target uses bare uvicorn and is therefore Linux/macOS only.

---

## Data

Everything is synthetic and ships with the repository, in
`backend/migrations/002_seed.sql`: 6 fictional services, 12 incidents, 4 policy
rules. No PII, no real service names, nothing fetched at runtime. The mock world
has no external dependencies on purpose, so a live call can never hang a
demonstration.

---

## If something goes wrong

**No runbook ever appears after a cold run.** `RUN_WORKER_IN_PROCESS=true` is
missing. The compile event is sitting in the outbox with nothing draining it.

**Every incident refuses, and the deploy ages look enormous.** The sample world
has aged: `002_seed.sql` writes `NOW() - INTERVAL '2 hours'`, which was true
when it ran. Re-seed, or press **Restore the sample** in the app.

**`undefined column "predicate"` while migrating.** The migrations were applied
in numeric order. See the ordering under Path B.

**`llm` reads `degraded`.** That means "not Bedrock", not "broken". Check which
provider is actually serving:

```bash
curl localhost:8000/api/admin/smoke -H "x-admin-token: dev-admin-token"
```

A real fallback provider makes genuine model calls, so timings remain
comparable. The deterministic local planner does not, so they are not.
