# Cascade

**Agent memory that knows when it has expired.**

Every procedure this system learns is pinned to the exact version of every
policy rule it was derived from. Change one rule and all of them stop being
trusted, in a transaction of four writes, whether one procedure depends on that
rule or a hundred thousand. Nothing is marked stale, because staleness is a
join, not a column.

**Live:** https://main.d1fzvx73990zqu.amplifyapp.com
**API:** https://d3t9yaye62k6ve.cloudfront.net

No login. Everything a reviewer needs to do here is a write, so the demo is
deliberately open.

---

## Who this is for

**The person on call at 3am**, and the team that writes the runbooks they reach
for.

**The bottleneck is not finding a procedure. It is knowing whether the one you
found is still true.** A runbook is written against the policy of the day it was
written: roll back within 24 hours, never auto-fix a tier-1 service, one
automated action per incident. Those numbers change. The runbook does not. It
still matches the incident, it still executes cleanly, and it now does the wrong
thing quickly and with confidence.

Nothing about a stale procedure looks stale. That is what makes it expensive:
the failure is silent at the moment it matters and discovered afterwards, in the
review for the incident it caused.

**Why it is worth solving.** Teams respond to this today by not automating.
Procedures stay advisory, a human reads them and decides, and most of the value
of having written them down is lost. The alternative is automating and accepting
that some fraction of runs will confidently apply superseded policy. Cascade is
an attempt at a third option: a procedure carries the versions of the rules it
was derived from, and refuses itself when any of them moves.

---

## How it works

**Learn.** A novel incident arrives. The agent plans with tools, checks policy
before acting, and either remediates or escalates with a reason. A successful
run is compiled into a runbook together with the exact policy rules it consulted
and the version each was at.

**Reuse.** A similar incident arrives. Vector search finds the runbook, the
provenance check confirms every pinned rule is still current, its compiled
preconditions are evaluated, and the stored steps execute directly. No model is
called anywhere on this path: retrieval is an index, freshness is a join, and
preconditions are a predicate evaluation. The same incident gets the same answer
every time.

**Unlearn.** You change a rule. Every runbook that depended on it is stale the
instant the transaction commits, in-flight tasks are interrupted before their
next side effect, and high-confidence runbooks are queued for re-derivation.

### The part that matters

Run `INC-1009` after shortening the rollback window. The runbook still matches
by vector distance. It is refused anyway, because the provenance join says it
was compiled against `rollback_window` v1 while head is v2. It re-plans from
scratch and escalates.

Matched by meaning. Refused by provenance.

---

## Measured against a baseline

The full method, per-case results and the reverted experiments are in
[`IMPROVEMENT_CHANGELOG.md`](IMPROVEMENT_CHANGELOG.md). Raw output is in
[`backend/eval/out/`](backend/eval/out/) and rendered in the **Evidence** screen
of the running app.

Twelve seeded incidents, decided twice — once under the policy the runbooks were
learned under, then again with one rule tightened. Twenty-two scored decisions
per arm, identical cases, same model on all three.

| Metric | Direct prompt | Cached runbook | Cascade |
|---|---|---|---|
| Policy-correct decisions | 86.4% | 86.4% | **95.5%** |
| Unsafe actions | 0 | 0 | 1 |
| Median latency | 2,530 ms | 2,515 ms | 4,877 ms |
| Planner tokens | 7,118 | 9,821 | 36,641 |

**The expected result did not happen, and that is reported rather than
revised.** The evaluation was built expecting the baselines to carry a stale
procedure into phase two and execute it. Neither did, and neither took a single
unsafe action: handed the current policy, Claude Sonnet 4.6 notices that the
live rule and the remembered procedure disagree and sides with the rule, citing
the new version by name.

So the honest headline is **accuracy and cost, not safety**. Cascade is more
accurate and roughly five times more expensive in tokens.

What did separate them is narrower and more interesting:

- **The cached-runbook arm got worse after the policy change**, 90.9% to 81.8%,
  and its new errors were on resource-exhaustion incidents that the rollback
  window does not govern at all. A change held in a prompt is absorbed as a mood
  rather than as a scope. A predicate carrying a `when` clause cannot make that
  mistake.
- **Cascade was the only arm to decide `INC-1011` correctly** in both phases.
- **Reuse costs nothing when it happens**: a guided run makes no model call.

Cascade's single unsafe result was a defect of ours, and a reporting one rather
than an unsafe act: an already-resolved incident was recorded as `remediated`
after a one-step run that never called a remediation tool. The evaluation found
it, it is fixed, and the number is left as measured because the defect is the
more useful artifact.

---

## Running it

Full setup from a clean machine, with exact commands for the solution, the
baselines and the evaluation, is in [`REPRODUCTION.md`](REPRODUCTION.md).

```bash
# database
docker compose up -d crdb && make reset

# backend — run_local.py, not bare uvicorn, on Windows
cd backend && pip install -e . && python run_local.py

# frontend
cd frontend && npm install && npm run dev
```

Migrations do **not** apply in numeric order: `006` adds the columns `002`
inserts into, so the seed runs last. `make reset` handles it.

### Verifying it

```bash
cd backend && python verify_integration.py        # 118 assertions, in process
cd backend && python -m eval.verify_features --api <host> --admin-token <token>
cd backend && python -m eval.run_eval    --api <host> --admin-token <token>
```

`verify_integration.py` refuses to run in stub mode, so a green result can never
be a canned one. `verify_features.py` walks the product's claims over HTTP
against a live deployment: learn, reuse with no model call, a four-write
cascade, and the refusal.

---

## Architecture

One CockroachDB cluster holds all four kinds of memory — policy, procedures,
episodes and in-flight state — plus the embeddings, so there is nothing to keep
in sync.

```
frontend/         Next.js 16 application shell and a 17-page documentation site
backend/app/      FastAPI: 21 core modules, 11 routers
  core/policy/    the predicate language and the one evaluator that applies it
  core/           retrieval, freshness, compiler, executor, cascade, confidence
backend/worker/   6 job kinds, drained from a transactional outbox
backend/eval/     baselines, the evaluation harness, feature verification
backend/migrations/  6 migrations
infra/            7 deployment scripts, CockroachDB Cloud through to CloudFront
```

Serving on **Amazon Bedrock** end to end: Claude Sonnet 4.6 for planning and
compilation, Claude Haiku 4.5 for fast paths, Titan Text Embeddings v2 for the
1024-dimension vectors the index is built on.

Deployed on ECS Fargate behind CloudFront, with a Lambda worker on SQS and the
frontend on Amplify.

### Design decisions worth defending

**Policy is data.** A rule carries a predicate and an enforcement mode, and one
evaluator applies whatever rules exist. A rule you invent is enforced, versioned
and cascaded exactly like the ones that shipped. Before this, three rule keys
were named in Python and a user-authored rule was stored, versioned and
correctly reported stale while being enforced by nothing.

**Enforcement lives in tools, not in the conversation.** `apply_remediation`
re-reads current policy and refuses on its own. The agent plans; the tools
decide. An agent cannot talk its way past a rule.

**Reuse is deterministic.** Preconditions compile to predicates, validated
structurally and against the incident they were learned from. There is no model
on the reuse path at all.

**Staleness is derived, never stored.** A flag can be forgotten by any writer
that does not know it exists. A join cannot.

[`DEVIATIONS.md`](DEVIATIONS.md) records 16 places this departs from its own
specification, with the reasoning and the cost.

---

## Using it on your own material

None of it requires adopting the agent.

- **Import runbooks you already have.** Paste one; the model proposes which
  policy rules it depends on, you confirm, and it is governed identically to a
  compiled one.
- **Write policy rules.** Pick a fact, a comparison and a value. The engine
  enforces it from then on.
- **Let your own agent ask.** `POST /api/memory/check` answers "is what I
  remember still valid" with no planner and no execution, over HTTP or MCP.
  Scoped, hashed, revocable keys.
- **Send results somewhere.** Slack, Discord or a bare webhook, with an
  idempotency ledger that suppresses replays.

```bash
curl -X POST https://d3t9yaye62k6ve.cloudfront.net/api/memory/check \
  -H "Authorization: Bearer csk_..." \
  -d '{"citations":[{"rule_key":"incident.rollback_window","rule_version":1}]}'
```

```json
{ "valid": false,
  "summary": "Not valid. incident.rollback_window moved from v1 to v2
              (hours: 24 -> 4). Re-derive the procedure before acting on it." }
```

---

## Security

**There is no authentication.** No login, no user store, no sessions. Tokens are
shared secrets and role names are self-asserted. The admin token is kept out of
the browser by a server-side proxy with an explicit route allowlist, which stops
the credential leaking but is not access control: anyone who can reach the site
can change policy. That is deliberate for an open demo and is the first thing to
change for anything else. `auth.py` was designed around a `Principal` resolved
from a verified JWT, which is where OIDC would attach.

Consequential actions are gated: an autonomy check can park an action for a
human, and approving re-runs the task, which is only safe because every
side-effecting tool is idempotent on `(task_id, step_index)`.

---

## Documentation

- [`IMPROVEMENT_CHANGELOG.md`](IMPROVEMENT_CHANGELOG.md) — how this got here,
  what was reverted, and the failure mode it is still exposed to
- [`REPRODUCTION.md`](REPRODUCTION.md) — clean-environment setup and every
  command
- [`DEVIATIONS.md`](DEVIATIONS.md) — 16 deviations, with rationale
- [`docs/query-plans.md`](docs/query-plans.md) — the `EXPLAIN` proof, including
  the full-scan plan one stray predicate produced
- [`docs/multi-region.md`](docs/multi-region.md) — survival goals and what they
  change
- [`docs/skills-review.md`](docs/skills-review.md) — 12 schema and query
  findings, each a live defect at the time
- **`/docs` in the running app** — 17 pages written for using the product

---

## Licence

MIT.
