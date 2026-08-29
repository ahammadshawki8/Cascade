# CASCADE

**Agent memory that knows when it has expired.**

Every procedure this system learns is pinned to the exact version of every
policy rule it was derived from. Change one rule and all of them stop being
trusted, in a transaction of four writes, whether one procedure depends on
that rule or a hundred thousand. Nothing is marked stale, because staleness
is a join, not a column.

An agent produces the procedures. That part is ordinary, and it is the last
thing in this README for a reason.

You can also use it without adopting the agent at all. Import the runbooks you
already have, write policy rules of your own, and let your own agent ask
whether what it remembers is still valid. Those three are the product; the
agent is one consumer of it.

CockroachDB x AWS Hackathon submission
Ashfaq (Track A, shell) and Shawki (Track B, core engine)
Last updated: August 19, 2026

**Live demo:** https://main.d1fzvx73990zqu.amplifyapp.com
**Documentation, in the app:** https://main.d1fzvx73990zqu.amplifyapp.com/docs
**API:** https://d3t9yaye62k6ve.cloudfront.net

No login and no credentials. Everything a reviewer needs to do is a write, so
the demo is deliberately open. Press `Ctrl-K` and run **Start the guided
walkthrough** for the whole loop in about six minutes, or **Reset demo world**
at any time to put the sample data back.

| | |
|---|---|
| Integration suite | **109 passed, 0 failed, 1 skipped**, against a live CockroachDB Cloud cluster |
| Serving | **Amazon Bedrock** end to end: Claude Sonnet 4.6 (planner), Claude Haiku 4.5 (fast path), Titan Text Embeddings v2 |
| Measured speedup | **11.45x** (cold 13,158 ms, guided 1,149 ms), n=3 each, on Bedrock |
| Planner tokens avoided | **7,469 per reuse**, down to zero |
| Unlearn transaction | **4 writes**, fixed, whatever depends on the rule |
| Survivability | `SURVIVE ZONE FAILURE`, 3 voting replicas across separate AWS availability zones |
| Deployment | **live** on ECS Fargate, Lambda, SQS, S3, Secrets Manager, CloudFront and Amplify |

---

## The problem

Any tool can cache what worked. The trouble starts afterwards.

Your rollback window changes from 24 hours to 4. Every runbook that assumed the
old window is now a set of confidently wrong instructions, and nothing about it
looks wrong. It still matches the incident. It still executes cleanly. It just
does the wrong thing, quickly and automatically.

Cascade treats a remembered procedure as usable only while the rules it was
built on are still the current rules, and it checks that immediately before
every reuse rather than hoping somebody remembered to invalidate a cache.

## The loop

**Learn.** A novel incident arrives. The agent plans with tools, checks policy
before acting, and either remediates or escalates with a reason. A successful
run is compiled into a runbook, together with the exact policy rules it
consulted and the version each one was at.

**Reuse.** A similar incident arrives. Vector search finds the runbook, the
provenance check confirms every pinned rule is still current, its compiled
preconditions are evaluated, and the stored steps execute directly. No model is
called at any point on this path: retrieval is a vector index, freshness is a
join, and the precondition check is a predicate evaluation. The same incident
therefore gets the same answer every time.

**Unlearn.** You change a rule. Every runbook that depended on it is stale the
instant the transaction commits, in-flight tasks are interrupted before their
next side effect, and high-confidence runbooks are queued for relearning.

## The part that matters

Run `INC-1009` after shortening the rollback window and watch what happens.

The runbook still matches by vector distance. It is refused anyway, because the
provenance join says it was compiled against `rollback_window` v1 while head is
now v2. The task falls back to exploring, and then escalates, because that
deploy is five hours old and the new window is four.

Two refusals, for two different reasons. It refused to *reuse* because the
memory was stale, then refused to *act* because the new policy says no. A
system that only did the second would have run a stale procedure and hoped the
policy check caught it.

Stale knowledge is worse than no knowledge, because an agent will act on it
confidently. That refusal is the product.

---

## Quick start

Ten minutes. One container, two terminals. No cloud account and no API keys
required: Cascade ships with a deterministic local planner and a local
embedder, so the whole loop runs offline.

**Prerequisites:** Docker, Python 3.12 or newer, Node.js 20 or newer.

### 1. Start CockroachDB

```bash
docker run -d --name cascade-crdb \
  -p 26257:26257 -p 8080:8080 \
  cockroachdb/cockroach:latest start-single-node --insecure
```

### 2. Apply the six migrations, in order

`001` creates the schema and the vector index, `002` seeds policy and twelve
demo incidents, `003` adds negative memory, `004` adds retention and merge
lineage, `005` retains the step detail behind each run, and `006` turns policy
into data and adds connections, agent keys and the connector ledger.

```bash
cd backend

for f in 001_schema 002_seed 003_extensions 004_production 005_step_detail \n         006_platform; do
  docker cp migrations/$f*.sql cascade-crdb:/tmp/$f.sql
done

docker exec cascade-crdb ./cockroach sql --insecure \
  -e "DROP DATABASE IF EXISTS cascade CASCADE; CREATE DATABASE cascade;"

for f in 001 002 003 004 005 006; do
  docker exec cascade-crdb ./cockroach sql --insecure \
    --database=cascade --file=//tmp/$f.sql
done
```

Expect 19 tables, 4 rules, 6 services, 12 incidents, and the `pb_embed_idx`
vector index. `infra/02_migrate.sh` does the same against a remote cluster.

### 3. Configure

```bash
cp .env.example backend/.env
```

The three settings that matter locally:

```bash
DATABASE_URL=postgresql://root@localhost:26257/cascade?sslmode=disable
CASCADE_STUB_MODE=false      # flipping this to false IS the integration test
RUN_WORKER_IN_PROCESS=true   # local dev has no SQS or Lambda to drain the outbox
```

### 4. Start the backend

```bash
cd backend
pip install -e .
python run_local.py
```

Runs at `http://127.0.0.1:8000`.

> **Why `run_local.py` rather than bare `uvicorn`?** psycopg's async mode cannot
> drive the ProactorEventLoop that asyncio selects by default on Windows, and as
> of Python 3.14 `set_event_loop_policy` no longer influences the loop uvicorn
> builds for itself. The launcher constructs a selector loop explicitly. On
> Linux and macOS `uvicorn app.main:app` works directly, and that is what the
> Dockerfile runs.

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:3000`. In-app documentation is at `/docs`.

### Optional: connect a real model

Any one of these in `backend/.env` is enough, and the first that answers wins:

```bash
GROQ_API_KEY=gsk_...          # planner, tool-calling capable
HF_API_KEY=hf_...             # embeddings, BAAI/bge-large-en-v1.5 is 1024-d
OPENROUTER_API_KEY=sk-or-...  # planner fallback
AWS_REGION=us-east-1          # or Bedrock, using machine credentials
```

Chat falls back `bedrock, groq, openrouter, local`. Embeddings fall back
`bedrock, huggingface, local`. The two chains are independent, so chat can be
live while embeddings are not. Press `Ctrl-K` and run **Check which LLM
provider is serving** to see which is which, or call `/api/admin/smoke`.

---

## Using it on your own material

Everything the walkthrough shows runs on sample data that ships with the
product. These four take a couple of minutes each and run on yours. The console
tracks them under **Make it yours** in the Work view, and each one is checked
off by reading real state rather than by remembering that a button was pressed.

### Write a policy rule of your own

**Policy** then **New rule**. Pick a field, an operator and a value, say what
the refusal should read, and choose whether it binds:

| Mode | What it does |
|---|---|
| Advisory | Cited and versioned. Invalidates procedures when it changes. Blocks nothing. |
| Shadow | Evaluated and recorded, but does not block. Use it to see what a rule would have refused before letting it refuse anything. |
| Enforcing | Blocks the action when it fails. |

**Try it against the incidents** runs the candidate rule over the incident set
and reports exactly which ones it would refuse, using the same evaluator the
engine uses, so the preview cannot flatter the rule.

Until August 2026 this was impossible, and it would not have meant anything if
it had been: the eligibility check named three rule keys in Python, so a rule
you invented was stored, versioned, cascaded and correctly reported stale while
being enforced by nothing. Policy is now data, and the evaluator applies
whatever rules exist. The proof that the change was faithful is that the whole
pre-existing suite passes unchanged against rules that are now rows.

Advisory mode matters more than it looks. Staleness detection never needed a
predicate, only provenance, so you can paste in fifty policies as advisory in
an afternoon and get the entire runbook-rot product working the same day.

### Import a runbook you already have

**Procedures** then **Import a runbook**. Paste it in whatever shape it is
already in. Cascade reads it and proposes which policy rules it depends on,
each with the sentence it was drawn from, and nothing is written until you
confirm.

The confirmation is not ceremony. Linking sentences to policy is model output,
and a wrong citation would not fail loudly, it would quietly make a procedure
look governed while never going stale. A procedure with no citations is
refused outright for the same reason.

Imported procedures are governed, not executed. Their steps are prose a human
performs, so they are searchable and they go stale by exactly the same join as
a compiled runbook, but retrieval will never hand one to the executor.

### Send the result to Slack

**Connections** then **Connect an app**. Paste a Slack incoming webhook URL
(Discord and bare webhooks work too, and Discord needs no app and no admin
approval if your Slack workspace blocks installs). **Send test** delivers a
real message and reports the status code and latency it got back.

From then on, when the agent notifies on-call the message lands in the channel
as well as in the demo log. The mock world is layered under it rather than
replaced, so the seeded demo keeps working with nothing configured.

The safety property is the interesting part. Approving a gated action resumes
the task by re-running it, which is only safe because every side-effecting step
is idempotent on `{task_id}:{step_index}`. Remote services are not trusted to
honour an `Idempotency-Key` header, so `connector_calls` carries a unique
constraint and a replayed step is suppressed from our own ledger. The
connections list counts those suppressions, and the run trace shows them.

Connections are `dry_run` until you deliberately make them live, calls time out
at ten seconds, and three consecutive failures trip a breaker that escalates
the run rather than blocking it.

### Let your own agent ask

**Connections** then **Create key**. Choose where it will run and you get a
copy-paste block with the key already in it, plus the one command that
downloads the connector. It has no dependencies, so downloading it is the whole
install.

Then, in your own editor:

> is my rollback procedure still valid?

```
POST /api/memory/check
{"citations": [{"rule_key": "incident.rollback_window", "rule_version": 1}]}

-> {"valid": false,
    "summary": "Not valid. incident.rollback_window moved from v1 to v2
                (hours: 24 -> 4). Re-derive the procedure before acting on it."}
```

No planner, no execution, no coupling to how the caller works. An agent with a
completely different toolset can use this, which is why it is the piece worth
exposing. Change the rule in Cascade, ask again, and the answer changes, with
the version, the parameter delta and who moved it.

Keys are hashed, scoped (`memory:read`, `memory:write`, `runs:write`) and
revocable. Starting incidents is off by default: checking memory is read-only
and starting a run is not.

The console reacts while this happens. The key shows as live with a call count
and a last-seen time, and **What agents have been asking** lists each check and
its verdict. That is the evidence for a claim that would otherwise be a
sentence in a README.

### Restoring the sample world keeps all of it

**Restore sample** puts the seeded rules, services and incidents back and
clears what the agent learned. It does not touch the rules you wrote, the
procedures you imported, your connections or your keys, and it re-pins your
procedures' provenance to whatever policy is now head. Deleting someone's Slack
connection because they asked to restore sample data would be a bug, not a
feature.

---

## Demo flow

### 1. Learn

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1001"}'
```

The console badge reads **Exploring**. Steps stream in as they complete. A
runbook appears in the library a second or two later at confidence 0.30, with
its provenance edges listed and every dot green.

### 2. Reuse

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1002"}'
```

The badge now names the runbook and its version instead of reading
**Exploring**. Different service, same class of problem, no planner in the loop.

### 3. Unlearn

Preview the blast radius first. This is deterministic SQL and writes nothing.

```bash
curl -X POST http://127.0.0.1:8000/api/rules/incident.rollback_window/dry-run \
  -H "Content-Type: application/json" \
  -d '{"body": "Rollback allowed only within {hours} hours of deploy.", "params": {"hours": 4}}'
```

Then commit it. This one needs the admin token.

```bash
curl -X POST http://127.0.0.1:8000/api/rules/incident.rollback_window \
  -H "Content-Type: application/json" \
  -H "x-admin-token: dev-admin-token" \
  -d '{"body": "Rollback allowed only within {hours} hours of deploy.", "params": {"hours": 4}}'
```

The cascade commits as exactly four writes with no fan-out. The runbook
card flips to `suspect` with a red provenance dot, running tasks are
interrupted before their next side effect, and runbooks above 0.6 confidence
are queued for relearning as v2 with a `supersedes` link.

### 4. The refusal

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Remediate INC-1009"}'
```

Matched by vector search, refused as stale, explores instead, escalates under
the new rule. See "The part that matters" above for why this is the whole point.

---

## Architecture

```
Browser
  |  https
Next.js interface and server-side proxy
  |
FastAPI on ECS Fargate            13 routers, in-process interrupt bus, SSE
  |
  +--> CockroachDB                all durable state, vector index, MVCC history
  |
  +--> SQS --> Lambda worker      compile, rule_changed, relearn,
                 ^                 recheck_suspect, postmortem, insight_scan
                 |
          EventBridge, every 60s  the sweeper that makes the outbox correct
                                  rather than hopeful
```

Four processes and one database. There is deliberately no second source of
truth: staleness, history and provenance are all derived from CockroachDB
rather than mirrored into anything else.

---

## Key design decisions

### Changing a rule is O(1)

The obvious approach is to mark every dependent runbook stale, which means an
unbounded write set and heavy contention on exactly the table retrieval reads.
Instead the transaction is a fixed four writes: close the old rule version,
insert the new one, one outbox event, one audit entry.

Staleness then *derives* from the version bump. Every dependent runbook is
stale the instant this commits, and no runbook row was touched to make that
true. That is why the transaction is the same four writes whether there are
three runbooks or three thousand.

### Retrieval runs in two statements

Phase 1 is a pure nearest-neighbour query with **no predicate at all**. Phase 2
is a primary key lookup with the metadata filter. Phase 3, the freshness check,
lives in the executor because matching and permission are different questions.

This is not premature optimisation. An earlier version carried
`WHERE embedding IS NOT NULL` in phase 1, and that single predicate was enough
to make the optimizer abandon `pb_embed_idx` and full scan with a top-k sort.
The answers stayed correct, which is exactly why it went unnoticed.
`docs/query-plans.md` has both plans side by side.

### Provenance is grounded, not asserted

A model asked to summarise a run will happily cite a plausible-sounding rule it
never saw. Every citation is cross-checked against what was actually observed:
the policy snapshot the run read, and the versions the eligibility check
reported using. A citation corroborated by neither is dropped.

An invented edge would point at a rule the runbook does not really depend on,
so it would never go stale when the rule that matters changes. The runbook would
look fresh forever, which is precisely the failure this system exists to
prevent.

### Interrupts, three layers

An in-process bus delivers in microseconds and an SNS broadcast reaches peer
instances in about a second, but neither is authoritative. The durable
`tasks.interrupt_flag`, checked immediately before every side-effecting call, is
the guarantee. Correctness never depends on the fast path.

### Confidence is earned

New runbook starts at `candidate` and 0.30. Success adds 0.15 up to 0.99,
failure multiplies by 0.6, three successes and at least 0.60 promotes to
`active`, below 0.20 is terminal, and idle runbooks decay 0.98 per seven days.

Confidence and freshness answer different questions. Confidence asks whether
this has worked before. Freshness asks whether the rules it assumed are still
the rules. A runbook at 0.99 is quarantined the instant a dependency moves.

---

## Beyond the MVP

| Feature | What it does |
|---|---|
| Autonomy gating | Irreversible actions from runbooks below a confidence threshold stop and wait for a human. Approving *re-runs* the task, which is safe because every side-effecting tool is idempotent on `{task_id}:{step_index}`. Off by default, since a threshold above zero stops every first reuse. |
| Insight engine | Mines history and proposes policy changes, for example that widening a 4 hour window to 31 hours recovers three blocked incidents and blocks nothing new. Computed by replay over recorded episodes, not extrapolated. |
| Semantic triage | Not every rule change breaks everything. Widening a window cannot invalidate a runbook that ran inside the old one, so provably relaxing changes clear automatically. Uncertain always stays quarantined, and numeric comparison runs deterministically before any model is consulted. |
| Counterfactual replay | Before committing a policy change, re-decide every historical incident and report which would newly be automated and which newly blocked. |
| Time travel | `AS OF SYSTEM TIME` answers "what did the agent believe when it made that call", using CockroachDB's MVCC directly with no event-sourcing layer of our own. |
| Negative memory | Failed approaches become anti-playbooks and are surfaced to the planner as warnings. Advisory only, because a stale memory of failure must not veto something policy now permits. |
| Blast-radius graph | Rules to runbooks to tasks, with stale dependencies drawn red and dashed. |
| Auto postmortems | Any run that does not cleanly remediate gets a writeup grounded in the recorded trajectory. |
| Savings ledger | Tokens, dollars and engineer hours avoided, measured from episodes rather than projected. |
| Generalization | Merges near-duplicate runbooks. Members must share an identical tool sequence, merged confidence is the **minimum** of its members, and members are archived rather than deleted. |

---

## Performance

Measured August 14, 2026 on the **deployed** stack: Amazon Bedrock serving both
the planner and the embeddings, against a CockroachDB Cloud cluster. Three cold
runs and three reuses, one of each incident kind.

| Metric | Measured |
|---|---|
| Cold run (explore) | 13,158 ms, 4.7 steps, 7,469 planner tokens |
| Guided run (reuse) | 1,149 ms, 4.3 steps, **0 planner tokens** |
| Guided versus cold | **11.45x faster** |
| Planner tokens avoided per reuse | **7,469**, to zero |
| Unlearn transaction | **4 writes**, fixed |
| Vector retrieval | index confirmed by live `EXPLAIN`, in the app at `/architecture` |

Sample size is three per side and the figure moves with model latency, so
treat 4x as the order of magnitude rather than a constant. The steady number
is the token one: a reuse calls the planner zero times, and that is structural
rather than a measurement.

### Does it hold at size

`backend/scripts/seed_scale.py` seeds synthetic runbooks against synthetic
rules, moves one rule, and reports what the transaction wrote against what it
invalidated. Run against the CockroachDB Cloud cluster:

| runbooks depending on the rule | writes | runbooks left stale | cascade |
|---|---|---|---|
| 3,000 | **4** | 3,000 | 1,703 ms |
| 50,000 | **4** | 50,000 | **1,583 ms** |

Sixteen times the dependent set, and the cascade is *not slower*. The
difference between the two rows is network noise, because neither transaction
touched a single runbook row. That is the claim, and it is the reason it is
worth expressing staleness as a join.

Freshness for one runbook stayed at ~275 ms across both, since it reads that
runbook's own provenance edges and nothing else.

```bash
python scripts/seed_scale.py --runbooks 50000 --rules 2000
```

Everything it creates is prefixed `scale/` and removed afterwards, so it is
safe to point at the demo cluster.

### On the cascade, and why there is no millisecond target here

Earlier revisions claimed the cascade completes in under 100 ms. That was
measured against single-node CockroachDB in Docker, and it does not survive
contact with a multi-node Cloud cluster, where the same transaction takes a
couple of seconds of consensus and network.

Reporting it that way was measuring the wrong thing. The claim D1 makes is not
a latency budget, it is that **the write set does not grow with how much has
been learned**: four writes whether one runbook depends on the rule or a
hundred thousand. The integration suite now asserts the write count, which is
the property, instead of a wall clock, which is the network.

`/api/metrics` reports the serving provider and reason, so you can always tell
which regime a measurement came from.

---

## Security and safety

**Authorization exists.** Three roles ordered by privilege: viewer reads,
operator runs tasks and resolves approvals, admin changes policy and resets the
world. Enforced on every write endpoint. The approvals endpoint ignores any
client-supplied `resolved_by`, because who authorised an irreversible action is
not a field the caller gets to assert.

**Authentication does not.** No login, no user store, no sessions. Tokens are
shared secrets, not per-user credentials, and the `name:` prefix that shows up
in the audit log is self-asserted. 25 of the 35 endpoints need no credential at
all, including `POST /api/tasks` and `POST /api/copilot`.

**The public demo is deliberately left open**, and this is a decision rather
than an omission. Everything a reviewer needs to do is a write: run an
incident, change a rule, re-learn a runbook, reset the world. Putting a
password in front of that would make the submission unevaluable in order to
protect a database full of invented incidents. The blast radius is a demo
world with a reset button on it.

What is protected is the credential, not the data: privileged calls go through
a server-side proxy so the admin token never reaches the browser, and the
Copilot executes as a role with no write grants. To close the site anyway, set
`DEMO_USER` and `DEMO_PASSWORD` for `infra/06_deploy_frontend.sh` and Amplify
will gate it at the edge.

Real authentication would be Cognito or OIDC in front of CloudFront with
`Principal` resolved from a verified JWT. `app/auth.py` was written around that
seam. It is post-submission work, not a weekend of it.

**Credentials stay server-side.** Privileged calls go through a Next.js route
handler that attaches the token out of the browser's reach, behind an explicit
path allowlist. An earlier version put the admin token in a `NEXT_PUBLIC_`
variable, which is inlined into the client bundle at build time, and the deploy
script was reading it out of Secrets Manager in order to publish it in the page
source. After a clean build the token now appears only in the server bundle.

**The Ops Copilot is read-only,** four layers deep: it must parse as a single
`SELECT` or `WITH`, mutating keywords are rejected on word boundaries, the query
is wrapped in `LIMIT 200` with a 3 second timeout, and it executes as
`cascade_readonly`, which holds no write grants. The last layer is the one that
matters; the first three exist so a bad query fails loudly and cheaply.

**Budgets are ceilings, not truncation.** 15 steps, 25,000 tokens, 60 seconds
per task. Exceeding one fails the task, because a half-executed remediation is
worse than none.

**Everything else** uses parameterized statements with no string interpolation,
and outbox rows are claimed with `UPDATE ... WHERE claimed_at IS NULL` so
at-least-once delivery and a worker dying mid-job are both survivable.

---

## Testing

```bash
cd backend
python verify_integration.py          # 109 assertions, resets the world first
python verify_integration.py --keep   # run against existing state
```

It refuses to run in stub mode, so a green result can never be a canned one. It
talks to the engine directly rather than over HTTP, because the interrupt case
needs a task already carrying `interrupt_flag` before execution starts, which is
not reachable through the API without a race.

| Area | What is asserted |
|---|---|
| Schema and seed | 13 core tables, 4 head rules, 6 services, 12 incidents |
| Vector index | `EXPLAIN` selects `pb_embed_idx` |
| Learn | Cold run succeeds, episode written, outbox queued, runbook at 0.30, and **every provenance edge resolves to a real rule version** |
| Reuse | Guided mode entered, speedup reported, confidence rises by 0.15 |
| Policy in guided mode | A refused eligibility verdict blocks the side-effecting steps |
| Autonomy gate | Parks, applies nothing, resumes on approve, **remediates exactly once despite the replay**, rejects cleanly |
| Interrupt | Halts, **no side effect applied**, scratchpad persisted, flag cleared |
| Unlearn | Cascade is four writes, old version closed, staleness derived, **stale runbook refused**, status demoted |
| Triage, replay, time travel, graph | Semantics and integrity |
| Copilot | Answers with visible SQL, rejects 4 injection attempts, allows a normal `created_at` read |
| RBAC, TTL, generalization | Role ordering, retention scoping, merge lineage |
| Predicates | A rule applies, refuses and abstains as written; a missing fact is unknown rather than silently false; malformed rules are refused at authoring time |
| Rule authoring | **A rule nobody hardcoded gates the engine**, is recorded as provenance, and advisory and shadow modes block nothing |
| Import | A pasted runbook yields name and steps, **one with no citations is refused**, human steps are kept, **an imported procedure never wins retrieval**, and it goes stale by the same join |
| API keys | Scopes are enforced, the secret is never stored, revocation is immediate |
| Connectors | Each destination gets its own payload shape, **a replayed step is suppressed rather than sent twice**, and a failing connection is skipped rather than retried forever |
| Walkthrough | **No step waits only on a success-only event**, the cold run compiles, the runbook carries a checkable predicate, the second incident really reuses, the policy change invalidates it, and the stale runbook is refused on the record |
| Contract | All 11 signatures unchanged |

Frontend:

```bash
cd frontend && npm run build       # compiles and typechecks
```

---

## Deployment

**Request Bedrock model access first.** It is granted manually per account and
region and the approval is not instant. Until it lands every call returns
`AccessDeniedException`.

```bash
cd infra

./01_ccloud_provision.sh     # CockroachDB Cloud cluster
./02_migrate.sh              # schema, seed, vector index

./03_aws_bootstrap.sh        # S3, SQS, Secrets Manager, IAM, ECR

# Store the real connection strings before anything tries to connect
aws secretsmanager update-secret --secret-id cascade/dsn-app      --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-worker   --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-readonly --secret-string "postgresql://..."

./04_deploy_ecs.sh           # image to ECR, load balancer, Fargate service
./05_deploy_lambda.sh        # worker, SQS trigger, 60s EventBridge sweeper
./07_deploy_cloudfront.sh    # HTTPS in front of the load balancer, before 06
./06_deploy_frontend.sh      # Amplify, built against the CloudFront URL
```

**Order matters.** `07` runs before `06` because `NEXT_PUBLIC_API_URL` is baked
in at build time. Amplify serves over https, so pointing the frontend at the raw
http load balancer gets every request blocked as mixed content, taking the event
stream with it. `06` refuses to build against a non-https URL for exactly this
reason.

Two other traps worth knowing. `05` pins
`--platform manylinux2014_x86_64 --only-binary=:all:`, without which pip
resolves host wheels for the database driver's binary extension and the function
dies at import. `07` disables compression and caching, because CloudFront
buffers a compressed response and `/api/events` never ends, so the dashboard
would receive nothing at all.

**Verify:**

```bash
curl https://<cloudfront>/health
curl https://<cloudfront>/api/admin/verify-index -H "x-admin-token: $ADMIN_TOKEN"
curl https://<cloudfront>/api/admin/smoke        -H "x-admin-token: $ADMIN_TOKEN"
curl -N https://<cloudfront>/api/events          # must stream, not buffer
```

---

## Project structure

```
backend/
  app/
    main.py, config.py, db.py, bus.py
    auth.py                RBAC
    telemetry.py           OpenTelemetry, optional
    core/                  21 modules
      contracts.py         the Track A to Track B seam, 5 frozen signatures
      llm.py, providers.py provider chain and fallbacks
      retrieval.py, freshness.py, executor.py, compiler.py
      cascade.py, confidence.py, tools.py, copilot.py
      autonomy.py, insights.py, postmortem.py, savings.py
      triage.py, analysis.py, negative_memory.py
      fanout.py, generalize.py
    routers/               13 routers
  worker/                  6 job kinds
  migrations/              001 schema, 002 seed, 003 extensions, 004 production,
                           005 step detail
  verify_integration.py    109 assertions
  run_local.py             Windows selector-loop launcher

frontend/src/
  app/
    page.tsx               desktop application shell
    icon.svg               brand mark and favicon
    api/proxy/[...path]/   server-side privileged proxy
    docs/                  16-page product documentation site
  components/              13 components plus the docs toolkit

infra/                     7 scripts, 01 to 07
docs/                      query-plans.md, skills-review.md, multi-region.md
ground_truth/              specification and contract
```

---

## Technology

**CockroachDB** provides distributed vector indexing for runbook retrieval,
`AS OF SYSTEM TIME` for time travel, row-level TTL for retention, and
serializable transactions for the cascade. Cluster provisioning uses the ccloud
CLI, and the MCP server was used during development.

**AWS** provides Bedrock (Claude Sonnet for planning, Haiku for fast calls,
Titan for embeddings), Lambda for background work, ECS Fargate for the API, S3
for episode trajectories, SQS for events, and EventBridge for the sweeper.

**Stack:** Python 3.12 with FastAPI and psycopg3; Next.js 16 with React 19 and
TypeScript; CockroachDB v26 or newer, which the vector index requires.

---

## Documentation

**In the app.** Run it and open `/docs`. Sixteen pages covering what to type,
what each badge means, and how to get value from the product, organised as
Getting started, Using Cascade, Understanding it, and Reference.

**In the repository:**

- `CLAUDE.md`, integrated project memory, current status, and the roadmap
- `DEVIATIONS.md`, 16 documented deviations with rationale and impact
- `docs/query-plans.md`, vector index `EXPLAIN` verification, including the
  full-scan plan a single stray predicate produced before it was fixed
- `docs/skills-review.md`, CockroachDB Agent Skills findings
- `docs/multi-region.md`, survival goals and per-table localities
- `ground_truth/`, the build specification, the frozen Day 0 contract, and the
  track split

---

## Status

**Done.** Both tracks wired together and verified against a real database. The
full learn, reuse, unlearn, refuse sequence runs end to end. Vector index proven
by live `EXPLAIN`. Tier 1 through 3 features shipped. Interface rebuilt as a
desktop application shell with a command palette. Documentation site written.
109 of 109 assertions passing against the deployed stack on Bedrock.

**Usable on your own material.** Policy is data rather than three hardcoded
comparisons, so you can write rules the engine obeys. Runbooks you already have
can be imported and grounded in that policy. Slack, Discord and bare webhooks
receive real notifications with replay suppression proven against the ledger.
Other agents can call the memory layer over HTTP or MCP with scoped, revocable
keys.

**Deployed and reachable.** The full stack is live on AWS: ECS Fargate behind
CloudFront for the API, Lambda and SQS for the worker, Amplify for the console,
against a CockroachDB Cloud cluster running `SURVIVE ZONE FAILURE`. Bedrock is
serving both the planner and the embeddings, which `/api/metrics` reports as it
happens.

Two features were deliberately not built. Multi-tenancy needs an org column on
every table and scoping in every query, and half-done multi-tenancy is a
data-leak vector rather than a partial feature. Real external integrations were
skipped because the mock world is required to have zero external dependencies
precisely so a live call can never hang the demo.

---

## Team

Ashfaq, Track A: FastAPI routers, frontend, infrastructure.
Shawki, Track B: core memory engine, AI logic, worker jobs.

Repository: https://github.com/ashfaqstu/Cascade
Issues: https://github.com/ashfaqstu/Cascade/issues
License: MIT
