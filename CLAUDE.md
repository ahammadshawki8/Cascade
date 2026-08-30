# Cascade — working notes

Context for anyone, human or agent, picking this up. The user-facing
introduction is [`README.md`](README.md); this is the operational detail that
does not belong there.

---

## What this is

An incident-response agent whose memory expires. Every procedure it learns is
pinned to the versions of the policy rules it was derived from, and refuses
itself when any of them moves. Three verbs: **learn**, **reuse**, **unlearn**.

## The three things most likely to trip you up

1. **`python run_local.py`, never bare `uvicorn`, on Windows.** psycopg's async
   mode cannot drive the default ProactorEventLoop, and since Python 3.14
   `set_event_loop_policy` no longer affects the loop uvicorn builds for itself.
   The launcher constructs a selector loop explicitly. Linux and macOS are
   unaffected; the Dockerfile runs uvicorn directly.

2. **Migrations do not apply in numeric order.** `006` adds the `predicate` and
   `enforcement` columns that `002` inserts into, so the seed runs last:
   `001 → 003 → 004 → 005 → 006 → 002`. `make reset` does this correctly.

3. **`RUN_WORKER_IN_PROCESS=true` locally.** There is no SQS or Lambda on a
   laptop, so without it the compile event is queued and no runbook ever
   appears, which reads as the system failing to learn. It must be `false` in a
   deployment or two consumers race.

## The sample world ages

`002_seed.sql` writes deploy timestamps as `NOW() - INTERVAL '2 hours'`. That is
absolute: after a few days every bad deploy is outside the rollback window, so
every cold run escalates, nothing is ever learned, and the demo silently stops
being able to tell its own story. The inbox detects this and offers the fix; the
evaluation harness resets at the top of each phase for the same reason.

---

## Deployment

The frontend auto-deploys: Amplify builds `frontend/` on every push to `main`.

**The backend does not.** There is no CI for it. Changes to `backend/` reach the
live API only by running `infra/04_deploy_ecs.sh`, which builds a Docker image,
so it needs Docker running and AWS credentials.

Order matters elsewhere: `07` before `06`, because `NEXT_PUBLIC_API_URL` is baked
in at build time and Amplify serves https, so pointing the frontend at the raw
http ALB gets every request blocked as mixed content, SSE included.

### Known gap

Three backend fixes are committed but **not on the live API**, because of the
above:

| Commit | What it corrects |
|---|---|
| `f4ba8fd` | The LLM status flag latches: one throttled call leaves it reading `degraded` for the life of the process while Bedrock serves every request |
| `0071bdc` | The explore path recorded `remediated` from the planner's claim rather than from whether a remediation tool ran |
| — | `GET /api/rules/{key}` never selected `predicate` or `enforcement`, so every rule reported as advisory however it was configured |

`eval/verify_features.py` fails exactly one assertion against the deployed API
for the third of these, and that failure is left visible rather than softened.

---

## Verifying

```bash
cd backend && python verify_integration.py     # 118 assertions, in process
cd backend && python -m eval.verify_features --api <host> --admin-token <token>
cd backend && python -m eval.run_eval    --api <host> --admin-token <token>
cd frontend && npm run build                   # compiles and typechecks
```

`verify_integration.py` refuses to run in stub mode, so a green result can never
be canned. It talks to the engine directly rather than over HTTP because the
interrupt case needs a task already carrying `interrupt_flag` before execution
starts, which is not reachable through the API without a race.

`verify_features.py` is the deployment-facing counterpart: it walks the product's
claims over HTTP in the order a person would read them.

---

## Interface model

Four destinations are the product — **Work**, **Procedures**, **Policy**,
**Connections** — plus **Extensions**, the shelf everything else comes from.
Evidence, Architecture, Intelligence, Copilot, Approvals, the command palette
button and the docs link all start uninstalled and each argues for itself on
that shelf with a purpose, a usage note and a worked example.

**Work mode** empties the workspace: it resets learned state and hides the
seeded incidents, while every rule, procedure, connection and key the user
brought survives. It does *not* hide policy, because those rules are enforced on
every run and a policy screen showing nothing while four rules gate every
decision is the exact failure this project exists to prevent.

The walkthrough explains all five screens before running anything, then
demonstrates the loop live. That ordering is deliberate: a cold run takes about
thirteen seconds, and somebody who understands the product will wait for it
while somebody ten seconds in will not.

---

## Design decisions worth not re-litigating

**Autonomy gating is off by default** (`AUTONOMY_MIN_CONFIDENCE=0`), because any
threshold above zero parks every first reuse for a human. That is right for
production and wrong for a demo, so Approvals is empty unless somebody changes
it, and the extension description says so.

**Resume-by-replay, not coroutine suspension.** Approving re-runs the task, which
is only safe because every side-effecting tool is idempotent on
`(task_id, step_index)` — asserted directly in the suite.

**Triage can only clear, never permit.** It re-pins a dependency forward when a
change is provably relaxing. It cannot mark a stale procedure usable while a
version mismatch stands, and any uncertainty leaves everything quarantined.

**Generalisation is conservative.** Members must share an identical tool
sequence, provenance is the union pinned at head, confidence is the minimum of
the members, and members are archived rather than deleted.

**A real model overfits preconditions; a deterministic one never will.** The
first compile on a live model emitted "the incident is of severity 'P1'", which
made a P2 incident match on retrieval and then refuse itself. Compiled
preconditions are model output and therefore a quality surface: a retrieval hit
followed by a precondition miss is not a near miss, it is a runbook that cannot
be reused, and that pair in `/api/metrics` is the signal.

**Deliberately not built:** multi-tenancy, because half-done tenancy is a
data-leak vector rather than a partial feature; and live integrations behind the
mock world, because the mock having zero external dependencies is what stops a
live call hanging a demonstration.

---

## Open risks

| Risk | State |
|---|---|
| Three backend fixes not deployed | See the table above. Needs Docker and `infra/04` |
| No authentication | By design for an open demo. `Principal` is the seam where OIDC attaches |
| Evaluation is n=1 per case | 22 decisions per arm, one run. Re-running would tell you how much of the gap is noise |
| Cascade costs 5x the tokens | Measured and reported. The reuse path is free; the cost is re-planning after invalidation |
