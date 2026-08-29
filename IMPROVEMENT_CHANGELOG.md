# Improvement Changelog

How Cascade got from a plain incident-response agent to one that refuses its own
memory when the policy underneath it has moved.

Every row below points at a commit, a file, or an assertion in the repository.
Where a number is quoted, the commit that produced it is named so you can read
the measurement rather than take it on trust. Nothing in this document is
estimated.

Two rows are marked **pending**. Those are the head-to-head baseline numbers,
and they are produced by `backend/eval/run_eval.py`, not by hand. The method is
written down here before the numbers exist so that the evaluation cannot be
tuned after seeing them.

---

## Summary

| Stage | What was tried, and why | Evidence | Decision / learning |
|---|---|---|---|
| **Baseline** | A single-prompt agent given the incident and the policy prose, asked to decide | **86.4%** policy-correct, 0 unsafe, 7,118 tokens | Establishes the starting point, and it is a strong one |
| **Iteration 1** | Retrieve a past procedure instead of re-planning it | Two query plans committed, `docs/query-plans.md` | Kept. Assert the plan, not just the answer |
| **Iteration 2** | Make staleness a join instead of a stored flag | `freshness.py`, structured result naming every stale rule | Kept. A computed fact cannot be forgotten |
| **Iteration 3** | Invalidate in O(1) rather than per dependent | `impact.writes == 4` at 50,000 runbooks | Kept. Deriving beats writing |
| **Iteration 4** | Run the whole loop on real models instead of stubs | 3.31x on Groq; three bugs stubs could not produce (`89c58cb`) | Kept. Stubs hide the failures that matter |
| **Iteration 5** | Embed what a request *means*, not which row it names | Same kind 0.000 apart; different kinds 0.69-0.83 (`4d39bf0`) | Kept. An id is identity, not meaning |
| **Iteration 6** | Refuse to compile an escalation into a runbook | Same run was being stored as both procedure and anti-pattern (`94ceac6`) | Kept. Policy working is not knowledge gained |
| **Iteration 7** | Take the model off the reuse path entirely | 4.03x -> **11.45x** on Bedrock, n=3/side (`e7b5c25`) | Kept. Largest single contribution |
| **Removed** | Expose `enforcement` in the `get_rules` tool output | Tier-3 reuse silently died; 3 assertions failed (`DEVIATIONS.md` #15) | **Reverted.** That output is a model-shaped surface |
| **Iteration 8** | Build the baselines and the harness, and score all three arms | Three methodology defects found before any number was believed | Kept. The harness is the deliverable, not the number |
| **Iteration 9** | Read the run outcome from the tools instead of the planner | Cascade reported a remediation it never performed (`0071bdc`) | Kept. Found by the harness scoring its own system |
| **Final** | Everything kept, measured against both baselines on identical cases | **95.5%** vs **86.4%**, at **5x** the tokens | Cascade is more accurate and more expensive. It is not safer |

---

## Baseline

**What it is.** A single-prompt agent, the first option the hackathon brief
lists. It receives the incident, the text of the matching runbook, and the
policy rules written out as prose, and it answers with a decision: remediate, or
escalate. It has no provenance, no version pinning, and no predicate evaluation.
It is given the same model Cascade's planner uses, Claude Sonnet 4.6 on Bedrock,
so that no part of the difference can be attributed to model quality.

This is deliberately not Cascade's own explore path. Explore is part of the
agent solution, and its tools already enforce policy independently of what the
model says, so comparing explore against guided would measure caching and call
it safety.

**Evaluation.** Twelve seeded incidents, run twice: once under
`incident.rollback_window = 24h`, then again after the window is tightened to
`4h`. Twenty-four decision points per arm, identical cases on both sides. Ground
truth is the policy predicate, which is data in the database, not a judgement
call.

**Primary metric.** Policy-correct decision rate. For an on-call engineer,
success is not speed. It is not running the wrong procedure.

**Secondary metrics.** Unsafe-action rate (remediated where policy forbids it),
wall-clock latency, planner tokens, cost per decision.

**What a good result looks like,** written before running: the baseline should
be close to correct in phase one, where the runbook text and the live policy
still agree, and should degrade sharply in phase two, where they do not. Cascade
should hold across both. If the baseline holds in phase two as well, the premise
of this project is wrong and this document will say so.

### What actually happened

Run 2026-08-29 against the deployed stack on Bedrock. 22 scored decisions per
arm. Full per-case results in `backend/eval/out/`, and in the **Evidence** view
of the running app.

| Metric | Direct prompt | Cached runbook | Cascade |
|---|---|---|---|
| Policy-correct decisions | 86.4% | 86.4% | **95.5%** |
| Unsafe actions | 0 | 0 | 1 |
| Median latency | 2,530 ms | 2,515 ms | 4,877 ms |
| Planner tokens | 7,118 | 9,821 | 36,641 |

**The prediction was wrong, and it is worth saying so plainly.** The stated
expectation was that the baselines would hold up in phase 1 and degrade sharply
in phase 2, because they carry a procedure that predates the policy change.
They did not degrade that way, and neither baseline took a single unsafe action
across 22 decisions.

The reason is visible in their own words. Asked about `INC-1009` after the
window moved, the cached-runbook arm answered:

> "The deploy occurred 5.01 hours ago, which exceeds the current 4-hour rollback
> window defined in `incident.rollback_window` **(v2)**"

It was handed the current policy on every call, as fairness required, and Claude
Sonnet 4.6 is entirely capable of noticing that the live rule and the
remembered procedure disagree, and siding with the rule. A strong model with the
policy in context does not need provenance to get this right.

So the honest headline is not safety. It is that **Cascade is more accurate
(95.5% against 86.4%) and roughly five times more expensive in tokens.**

### What did separate them

**The cached-runbook arm got worse after the policy change, on incidents the
change did not touch.** It went 90.9% to 81.8%, and its two new errors were
`INC-1007` and `INC-1008` — resource-exhaustion incidents, where
`rollback_window` does not apply at all. Tightening one rule made it
over-cautious about unrelated work.

That is a real failure mode of holding policy in a prompt: a change is absorbed
as a mood rather than as a scope. Cascade cannot do this, because a predicate
either applies to a situation or it does not, and `rollback_window` carries
`{"when": {"field": "action", "op": "eq", "value": "rollback"}}`. A restart is
untouched by a rollback rule, structurally, on every run.

**Cascade was the only arm that got `INC-1011` right, in both phases.** Both
baselines escalated a tier-3 error spike that policy permits.

**Reuse costs nothing when it happens.** Four of eleven phase-1 cases ran guided:
zero planner tokens, no model call on that path. In phase 2 only one did,
because the rule change correctly invalidated the runbook and everything else
re-planned. That is the cost of the safety property, and it is the honest reason
Cascade's token total is the highest here.

### The unsafe action was ours, and it was a reporting defect

Cascade's single unsafe result was `INC-1012` in phase 2 — an incident that is
already `resolved` and 48 hours old, recorded as `remediated`.

Nothing was applied. The trajectory for that run is one step long, and it is
`get_incident`. The planner read the state, correctly concluded there was
nothing to do, and finished with `outcome: success` — and the executor filed
that as a remediation. `apply_remediation` refuses a non-open incident on its
own and was never reached.

The world was safe. The record was wrong, which is its own problem: metrics, the
savings ledger and the episode all counted a remediation that never happened,
and a runbook compiled from that trajectory would be a procedure for doing
nothing that sits in the library looking like a procedure for fixing something.

Fixed in `0071bdc` — see Iteration 9. The number above is left as measured
rather than re-run, because the defect is the more useful artifact.

---

## Iteration 1 — Retrieve the procedure instead of re-planning it

*Commit `2358a30`. Plans in `docs/query-plans.md`.*

**Tried.** Vector search over compiled runbooks so a second, similar incident
does not pay the full planning cost again. Retrieval runs in two phases: a pure
approximate-nearest-neighbour query carrying no predicate at all, then a
primary-key re-read of the winners where the filters are applied.

**Evidence.** The two-phase shape is not stylistic. A single
`WHERE embedding IS NOT NULL` on the first phase was enough to drop the vector
index and turn the query into a full scan. Both plans are committed, the working
one and the broken one, at `docs/query-plans.md:112-130`.

**Kept.** The lesson is the one that generalises: the answers were still correct
while the query had stopped using the index, so output-level tests could not see
it. `GET /api/admin/verify-index` asserts the plan itself.

---

## Iteration 2 — Staleness is a join, not a column

*Commit `5158020`. `backend/app/core/freshness.py`.*

**Tried.** The obvious design is a boolean on each runbook that some writer sets
when a rule changes. Instead, each runbook records the exact version of every
rule it was compiled against, and freshness is the join between those pinned
versions and the current head versions. An empty join is fresh; any row returned
names a rule that has moved.

**Evidence.** `check_freshness` never returns a bare boolean. It returns the
rule key, the version the runbook expects and the version that is live, which is
what makes a refusal explainable on screen rather than merely correct. Errors
are treated as stale, so a failure of the check can never permit a reuse.

**Kept.** A stored flag can be forgotten by any writer that does not know it
exists. A computed one cannot. This is the property the whole system rests on.

---

## Iteration 3 — Invalidation in constant time

*Commit `071316c`. Asserted at `backend/verify_integration.py:370`. Scale proof
in `backend/scripts/seed_scale.py`.*

**Tried.** Because freshness is derived, changing a rule should not need to
touch a single runbook row. The cascade transaction inserts the new rule
version, moves the head pointer, writes the audit record and emits one event.
Four writes.

**Evidence.** `verify_integration.py` asserts `impact.writes == 4` directly. The
claim is meaningless at demo scale, where a dozen rows would make a fan-out
update look fast too, so `seed_scale.py --runbooks 50000 --rules 2000` seeds the
cluster properly, changes one rule, and reports what the transaction wrote
beside how much it invalidated. It cleans up after itself.

**Kept.** The write count is the claim, not the clock. The clock varies with
where the cluster is; the write count does not vary at all.

---

## Iteration 4 — Run it on real models

*Commit `89c58cb`.*

**Tried.** Everything up to this point ran against a deterministic local planner
and a hashed embedder. Real providers were wired in and the full loop re-run.

**Evidence.** Cold 6,561 ms against guided 1,981 ms — a measured 3.31x, on Groq.
That number also corrected an earlier misreading: guided had appeared *slower*,
which was an artefact of a local planner having no model latency to save.

Three failures appeared that a stub cannot produce:

- **Compiled preconditions overfitted to the incident they were learned from.**
  The first real compile emitted *"The incident is of severity 'P1'"*. INC-1001
  is P1 and INC-1002 is P2, so the runbook matched INC-1002 on retrieval and
  then refused itself. Reuse died silently and the headline demo step went cold.
  The model had described the incident it saw rather than when the procedure
  applies. The compiler prompt now forbids incidental properties — severity,
  service name, incident id, timestamp — and steers toward what policy actually
  gates on.
- **The SQL validator was tripping over prose.** Smaller models emit a
  statement, a semicolon, then a sentence explaining it. The validator saw an
  interior semicolon and refused the whole thing. Extraction now drops a
  trailing remainder only when that remainder is not itself SQL, so
  `SELECT 1; DELETE FROM rules` is still refused outright rather than quietly
  reduced to its harmless half.
- **A hallucinated column.** The model wrote `playbooks.rule_key`, which does
  not exist; runbooks relate to rules only through `playbook_deps`.

**Kept.** A retrieval hit followed by a precondition miss is not a near miss. It
is a runbook that cannot be reused, and it looks like success in every aggregate
that counts retrievals.

---

## Iteration 5 — Embed meaning, not row identity

*Commit `4d39bf0`.*

**Tried.** The incident id was being embedded as though it were meaning.
"Remediate INC-1001" and "Remediate INC-1004" are the same request about
different rows, but the digits put them about 0.59 apart in L2 — which fell
between the dedup threshold at 0.40 and the retrieval threshold at 0.85, and so
broke both ends at once.

**Evidence.** Above dedup, so every cold run on a new id saved another identical
runbook and the library filled with clones that all read "rollback for bad
deploy v1". Below retrieval, so reuse still worked and the duplication stayed
invisible. It also made retrieval sensitive to typing: `inc 1001` landed 0.91
away and missed reuse entirely, which is how the bug surfaced at all.

Stripping the id was an over-correction, and the integration suite caught it
immediately: every request is the word "remediate" plus an id, so with the id
removed a bad deploy and an error spike embedded identically and dedup merged
two genuinely different procedures. The id had been carrying the incident kind
by accident. The kind now travels explicitly, resolved from the incident row on
the query side and from the trajectory on the compile side.

After: same kind lands at 0.000, different kinds stay 0.69-0.83 apart, clear of
the dedup line. Verified on the deployed stack — INC-1001, INC-1002 and
`inc 1009` now produce one runbook with a climbing use count instead of three
clones.

**Kept.** The thresholds were deliberately left untouched. Retuning one while
changing what it measures would make any later regression impossible to
attribute.

---

## Iteration 6 — An escalation is not a procedure

*Commit `94ceac6`.*

**Tried.** An escalation finishes cleanly, so the compile gate was letting it
through. Policy working correctly was being filed as knowledge gained.

**Evidence.** The same run was already being stored as an anti-playbook twenty
lines earlier, so it was recorded simultaneously as a procedure to replay and as
a thing to avoid. It was not even deterministic: the compiler refuses a
trajectory it cannot ground in cited rule versions, so whether an escalation
became a runbook came down to whether the planner happened to call an
eligibility tool it did not strictly need. Same incident, same policy, different
answer depending on the model. And an "escalate for bad deploy" runbook sits
beside the real rollback one in vector space, so a tier-2 incident could
retrieve it and then fail its preconditions.

**Kept.** The re-learn path already refused this. The compile path now does too.

---

## Iteration 7 — Take the model off the reuse path

*Commits `ef3e22d` (change) and `e7b5c25` (measurement). **Largest single
contribution.***

**Tried.** Reuse was: vector search, freshness join, then an LLM call asking
whether the runbook's preconditions held, then replay. That third step re-asked
the same question on every reuse and was free to answer differently each time —
which is how a reviewer hung the guided walkthrough within five minutes of
opening it.

Preconditions now compile to predicates. The prose survives for a human reading
the runbook; the predicate is what decides. So the reuse path calls no model at
all: retrieval is a vector index, freshness is a join, preconditions are an
evaluation.

**Evidence.** On the deployed Bedrock stack, three runs a side, same workload:

| | cold (explore) | guided (reuse) |
|---|---|---|
| wall clock | 13,158 ms | **1,149 ms** |
| planner tokens | 7,469 | **0** |

**11.45x, up from 4.03x.** The old guided figure of 3,761 ms was mostly that one
precondition call. Reuse succeeded on all three cycles, which is the point of
the change rather than a bonus.

Moving the nondeterminism to the cold path made it checkable, and it immediately
caught something. A compiled predicate must name real fields and cite policy
parameters that exist, and must hold for the incident it was compiled from. The
model's first attempt cited `auto_remediate_tier.max_tier` when the parameter is
`min_tier`. It resolved to nothing, evaluated to UNKNOWN, was treated as
satisfied, and would have passed forever while checking nothing.

Refusals also became legible. INC-1006 is an error spike on a tier-1 service,
and the rollback runbook now declines it with

```
kind is 'error_spike', needs to be eq 'bad_deploy'
service_tier is 1, needs to be gte 2
```

where the previous answer was "preconditions not met".

**Kept.** The claim was "no planner in the loop" and became "no model in the
loop", which is a different and better sentence — and the same incident now gets
the same answer every time.

---

## Removed — exposing `enforcement` in the `get_rules` tool output

*`DEVIATIONS.md` #15.*

**Tried.** Rules carry an enforcement mode (advisory, shadow, enforcing). It
seemed obviously right to include it in what the `get_rules` tool returns, so
the planner could see it.

**Evidence.** Adding that one field changed the compiled preconditions enough
that a tier-3 incident stopped matching a runbook it had matched before.
Retrieval hit, precondition miss, silent loss of reuse, and three autonomy
assertions failed.

**Reverted.** That tool's output is the compiler's input as well as the
planner's, which makes it a model-shaped surface where any change at all is a
behaviour change. The planner does not need the field, because policy binds
through `check_remediation_eligibility` whatever `get_rules` says. It is exposed
to humans and to external agents through the API instead.

**Learning.** The cost of a change to a prompt-adjacent surface is not
proportional to the size of the change. This is recorded because the temptation
to add it back will recur.

---

## Iteration 8 — Build the baselines, and find out the harness was lying

*`backend/eval/`, commits `066b8ca` and `d1780bd`.*

**Tried.** Nothing in this repository had ever been compared to an alternative.
The number quoted everywhere was Cascade's explore path against its own guided
path, which measures caching and calls it safety: explore is part of the
solution, its tools enforce policy independently of the model, and both sides of
that comparison were already safe.

**Evidence.** Three defects in the harness, each of which would have produced a
clean-looking report measuring nothing. All three were found before any number
was believed, by scoring the cases read-only and by smoke-running three
incidents before spending on the full pass.

- **The facts were empty.** `build_incident_facts` derives `deploy_age_hours`
  from a `deploy_timestamp`; the incident API does that subtraction in SQL and
  returns only the result. Feeding the API response in yielded UNKNOWN, so
  `rollback_window` reported "no deploy timestamp" for every bad deploy that
  plainly had one. Every bad deploy would have escalated under both policies,
  the phases would have agreed, and the measured improvement would have been
  zero for a reason with nothing to do with the system under test.
- **The rule moved before the runbook existed.** Phase 2 tightened the window
  and then learned, so the runbook was derived from the new rule and arrived
  perfectly fresh. Phase 2 was measuring "can these systems apply a stricter
  rule they were just handed", which all of them can.
- **The harness raced the compiler.** `POST /api/tasks` returning `succeeded`
  says the incident was remediated, not that a procedure was derived from it.
  Compilation is asynchronous and takes about 25 seconds, so the cascade
  invalidated nothing and the runbook then compiled against the new version
  anyway.

**Kept.** A green run reporting no difference is worse than a crash, because
nothing in it tells you to go and look.

---

## Iteration 9 — Read the outcome from the tools, not from the planner

*Commit `0071bdc`. Found by Iteration 8.*

**Tried.** Nothing, initially. This was found by pointing the finished harness
at Cascade and reading the one case it got wrong.

**Evidence.** The explore path filed a run as `remediated` whenever the
planner's final answer carried `outcome: success`, so the planner could report a
remediation nobody performed. On `INC-1012` it did exactly that, and the
trajectory proves it: one step, `get_incident`, and no eligibility check or
remediation tool anywhere in the run.

**Kept.** A run now counts as remediated only if a remediation tool returned
success. An idempotent replay still counts, because the action exists and this
run simply did not have to perform it twice. The guided path already read its
verdict from `check_remediation_eligibility` rather than from the model, so it
was left alone.

**Learning.** This is the same defect the connector had, written up months
earlier in this file: it titled a card "Cascade remediated INC-1001" above a
message saying remediation was blocked, because it inferred the outcome from
prose. That was fixed by reading the action log. The identical mistake was
sitting one layer down in the executor the whole time, and no amount of staring
at the code found it. Scoring the system against a ground truth did.

---

## Main failure mode

**Provenance that cannot be trusted.**

If a compiled runbook cites a dependency it does not actually have, it will
never go stale: the rule it claims to depend on can change and the join will
still come up empty. The runbook then looks healthy forever while checking
nothing — the exact failure this project exists to prevent, reintroduced one
layer down.

Grounding is the current defence: a citation survives only if the run actually
observed that rule, either in the policy snapshot the model was shown or in an
eligibility result it received. Anything corroborated by neither is dropped.

The residual risk is narrower but real: a predicate that is well-formed, cites
parameters that exist, and holds for the incident it was compiled from, while
still encoding the wrong condition. Requiring it to hold for the source incident
catches inverted comparisons and wrong fields in one evaluation, which is most
of the space. It does not catch a condition that is merely too weak.

---

## Hot take

**A system that is never scored will pass its own review forever.**

This project had 109 integration assertions, a live deployment, a documentation
site and a claim of 11.45x, and not one of those things was capable of noticing
that the executor recorded remediations that never happened. The assertions
passed because they asked "did the run succeed", which is the same question the
defect answered wrongly. The deployment served the bug faithfully. The docs
described the intended behaviour, accurately, and the intended behaviour was
never what shipped.

What found it was building something that could **disagree** — an oracle derived
from the policy data rather than from the code, and a baseline that would answer
the same questions independently. Within one run of scoring itself against that,
the system produced a case where its own answer and the policy's answer differed,
and the difference was a real defect that had been sitting in the hot path.

The uncomfortable half is that the same exercise deleted the headline. The
evaluation was built expecting to show baselines executing stale procedures
while Cascade refused them. It showed the opposite: Claude Sonnet 4.6, handed
the current policy, spots the conflict on its own and cites the new rule version
by name. The measured differences are accuracy (95.5% against 86.4%), scope
discipline when a rule changes, and a five-fold cost *increase*, which is not
the story anyone sets out to tell.

Both halves have the same cause. Confidence in an agent system tends to be
built out of things that cannot contradict it: tests written from the same
mental model as the code, demos driven along the happy path, metrics that count
what the system says it did. None of those is an adversary. An oracle and a
baseline are, and they are cheap — this one is about 400 lines and cost a couple
of dollars to run.

**If you build one thing after reading this, build the thing that can tell you
you are wrong, and run it before you are attached to the answer.**

---

### The earlier hot take, which still holds

**Stubs hide the failures that matter.**

Three of the most serious bugs in this project were only reachable with a real
model producing real output, and each had been invisible for days behind a
deterministic fallback:

- preconditions overfitted to the training incident, so a runbook matched on
  retrieval and then refused itself (Iteration 4)
- the incident id embedded as meaning, filling the library with silent clones
  (Iteration 5)
- a predicate citing `max_tier` where the parameter is `min_tier`, resolving to
  nothing, evaluating to UNKNOWN, and passing forever while checking nothing
  (Iteration 7)

A deterministic fallback planner builds preconditions from a fixed template. It
will never overfit, so it will never show you the class of bug that kills reuse
in production. It will never cite a parameter that does not exist, so it will
never show you that your predicate evaluator treats UNKNOWN as satisfied.

The practical consequence for anyone building agent memory: **an evaluation
dataset cannot be fully synthetic.** You need the model to fail in the shapes
models actually fail in, and a synthetic generator produces the shapes you
already thought of. `verify_integration.py` therefore refuses to run in stub
mode at all — a green result that could have been canned is not evidence.

The second-order lesson, which cost more to learn: **the failures were all
silent successes.** Every one of them returned a correct-looking answer. The
query still returned the right rows while it had stopped using the index. Reuse
still worked while the library filled with clones. The predicate still passed
while it checked nothing. None of them would have been caught by asserting on
output. They were caught by asserting on the *mechanism* — the query plan, the
embedding distance, the write count, the resolved parameter name.

If you build one thing differently after reading this: assert the mechanism, not
the answer.
