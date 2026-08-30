# Cascade — Specification Deviations

Deviations from `CASCADE_BUILD_SPEC.md` (v3.1) forced by technical constraints.
Each entry records: what was specified · what was implemented · why · impact.

---

## 1. Vector index syntax — `CREATE VECTOR INDEX`, not `USING ivfflat`

**Specified** (`001_schema.sql`):
```sql
CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);
```

**Implemented:**
```sql
CREATE VECTOR INDEX pb_embed_idx ON playbooks (embedding);   -- outside the txn
```

**Why.** `USING ivfflat (... vector_l2_ops)` is **pgvector** syntax. CockroachDB
rejects it and ships its own C-SPANN vector index. The original statement failed,
the surrounding migration partially applied, and `pb_embed_idx` silently did not
exist while the schema file continued to claim it did. It also cannot run inside
the migration's explicit transaction, because it starts a backfill job.

**Impact.** None on behaviour — `CREATE VECTOR INDEX` defaults to the L2 metric,
which is exactly what decision D2 requires. `lists = 100` has no C-SPANN
equivalent and is not needed. Verified: `docs/query-plans.md`.

---

## 2. Retrieval phase 1 carries no predicate at all

**Specified.** D3 says never to mix a vector `ORDER BY` with scalar filters.

**Implemented.** Phase 1 has no `WHERE` clause whatsoever — not even
`embedding IS NOT NULL`. NULL distances are discarded in Python.

**Why.** That single predicate was enough to make the optimizer abandon
`pb_embed_idx` and full-scan with a top-k sort. D3 is stricter in practice than
it reads. `dedup_check()` had the same defect and was restructured identically.

**Impact.** None. Phase 2 re-reads those ids anyway, so the filtering is free.
Both plans recorded in `docs/query-plans.md`.

---

## 3. Playbooks are embedded by their trigger text, not their goal

**Specified.** §6.1 implies embedding the compiled spec.

**Implemented.** The stored vector is the embedding of the **originating request**
("Remediate INC-1001"). The goal and preconditions are excluded.

**Why.** Retrieval compares against an operator's phrasing, so the index has to
live in that space — query-to-query, not query-to-document. Embedding
goal + preconditions put a ~30-token document against a 2-token query and pushed
even exact-family matches past the L2 threshold (measured: 1.239 vs a 0.85
threshold). It also made every playbook look alike, because they all share the
same precondition boilerplate.

**Impact.** Improves retrieval. Preconditions are still enforced — by the
precondition check at execution time, which is where they belong.

---

## 4. `apply_remediation` sets `state = 'mitigated'`

**Specified.** `tools.py` set `state = 'remediated'`.

**Implemented.** `'mitigated'`.

**Why.** `mock_incidents` has `CHECK (state IN ('open','mitigated','resolved'))`.
`'remediated'` is not a member, so every remediation would have aborted.

**Impact.** None — `'mitigated'` is the schema's intended post-remediation state.

---

## 5. Idempotency keys live in `mock_action_log.details`

**Specified.** §5.3 requires idempotent side-effecting tools.

**Implemented.** The key is stored in the existing `details` JSONB column and
matched with `details ->> 'idempotency_key'`.

**Why.** The Day-0 schema is frozen and has no dedicated column. Adding one
would have required a contract PR for no behavioural gain.

**Impact.** None. Replay protection verified by `verify_integration.py`.

---

## 6. Compile trajectories travel in the outbox payload

**Specified.** Episodes write the full trajectory to S3; the worker reads it back.

**Implemented.** The trajectory is also inlined in the `compile` outbox payload.
S3 is still written when `EPISODES_BUCKET` is configured, and the worker falls
back to S3 when the payload has no trajectory.

**Why.** `episodes` has no trajectory column, so with no S3 bucket configured
(local dev) there was no path from a successful run to the compiler at all.

**Impact.** Payload is bounded by `max_steps_per_task` (15), so rows stay small.

---

## 7. Bedrock has a deterministic local fallback

**Specified.** §2 pins three Bedrock models and assumes they are reachable.

**Implemented.** Real Bedrock clients (boto3 → `bedrock-runtime`) with automatic
fallback to a deterministic local path when credentials are absent, model access
is not granted, or the circuit breaker opens:

| Model | Fallback |
|-------|----------|
| Titan Embeddings V2 | L2-normalized 1024-d signed-hash bag of unigrams + bigrams |
| Claude Sonnet (planner) | policy-faithful planner: inspect → read rules → check eligibility → remediate + notify, or escalate |
| Claude Haiku (precondition / params / SQL) | field-grounded precondition check, regex param extraction, keyword-matched built-in queries |

**Why.** No AWS credentials were available during integration, and the entire
learn/reuse/unlearn loop is otherwise untestable.

**Impact — read this before quoting numbers.**
- `llm_status()` returns `degraded` whenever a fallback is active. It is surfaced
  at `GET /api/metrics` (`llm` field), on the metric bar as an amber dot, and at
  `GET /api/admin/smoke`. The demo can never silently imply it is using Bedrock.
- **Cold-vs-guided latency is only meaningful with Bedrock live.** In degraded
  mode the planner is instant, so the measured 3.5-3.9× reflects database
  round-trips alone. Re-measure before quoting a figure.
- The fallback embedder normalizes incident ids to a single token, so
  "Remediate INC-1001" and "Remediate INC-1002" embed identically. That is
  correct for retrieval — the id is a parameter, not intent — but it is coarser
  than Titan and will not generalize across paraphrases.

---

## 8. Local dev runs the outbox worker in-process

**Specified.** §7.2 runs the worker as a Lambda behind SQS.

**Implemented.** `RUN_WORKER_IN_PROCESS=true` starts a 2s polling loop inside the
API. Deployments leave it `false`; Lambda owns the queue there.

**Why.** Local dev has no SQS and no Lambda, so the learn loop stopped at
"compile event queued" and no playbook was ever produced.

**Impact.** None on production. Same claim → dispatch → mark-processed path;
only the trigger differs.

---

## 9. Local API launcher (`run_local.py`)

**Specified.** `uvicorn app.main:app --reload`.

**Implemented.** `python run_local.py` on Windows.

**Why.** psycopg's async mode refuses to run on the ProactorEventLoop that
asyncio selects by default on Windows, and as of Python 3.14
`set_event_loop_policy` no longer influences the loop uvicorn builds for itself.
The selector loop is constructed explicitly via `asyncio.run(..., loop_factory=)`.

**Impact.** None on deployment — the Dockerfile runs uvicorn directly on Linux.

---

## 10. Frontend adapts the API playbook shape

**Specified.** `RunbookLibrary` consumes `usage_count` / `success_count` /
`failure_count`, with `is_stale` inside `spec.rule_citations`.

**Implemented.** `adaptPlaybook()` in `page.tsx` maps the frozen API shape
(`uses` / `successes` / `failures`, freshness on `deps`) onto the component's.

**Why.** The component was built against stub data that diverged from the frozen
`models.py`. Both sides are contract-frozen for different reasons, so the
adaptation sits between them.

**Impact.** None. Staleness still comes from the provenance join, not the spec.

---

## 11. LLM providers beyond Bedrock

**Specified.** §2 pins three Bedrock models.

**Implemented.** A provider chain — `bedrock → groq → openrouter → local` for
chat, `bedrock → huggingface → local` for embeddings — selected in
`core/providers.py`. Bedrock remains first and is the deployed path.

**Why.** Bedrock is pay-per-token with no free tier. Development and CI need to
exercise the full learn/reuse/unlearn loop without incurring cost or blocking
on model-access approval.

**Impact.** `llm_status()` reports `degraded` whenever anything below Bedrock
serves a request, and `/api/admin/smoke` names the actual provider. Embedding
width is enforced at 1024-d to match `VECTOR(1024)`; a model returning another
width is reshaped and loudly logged rather than silently stored.

---

## 12. Migration 003 (additive) for Tier 1–2 features

**Specified.** `001_schema.sql` is frozen at Day 0.

**Implemented.** `003_extensions.sql`, additive only — a new `anti_playbooks`
table, extra columns on `approvals` / `insights` / `postmortems`, and a widened
`outbox.kind` CHECK. `001` is untouched.

**Why.** Approvals had no way to resume (no record of the pending tool and
args); insights had no idempotency key for a repeated scan; postmortems
required a non-null `s3_key` that cannot exist without a bucket.

**Impact.** An existing deployment applies `003` without a rebuild.
`admin/reset` was updated to clear `anti_playbooks` — a table added after the
reset list was written would otherwise have leaked state across demo resets.

---

## 13. Bedrock model IDs are inference profiles, and the pinned models were unavailable

**Specified.** §2 pins `anthropic.claude-sonnet-5` (agent + compiler) and
`anthropic.claude-haiku-4-5` (fast path), and instructs that an ID unavailable
in the account or region be substituted with the closest available Claude
Sonnet/Haiku ID and recorded here.

**Implemented.**

```
BEDROCK_AGENT_MODEL_ID=us.anthropic.claude-sonnet-4-6
BEDROCK_FAST_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
```

**Why.** Two separate findings, verified live against account 897545289507 in
us-east-1 on August 11, 2026.

1. **On-demand invocation requires an inference profile id**, not a bare model
   id. Profile ids carry a `us.` or `global.` region prefix. Calling the bare
   `anthropic.claude-sonnet-5` returns `AccessDeniedException` reading "not
   available for this account", and the bare dated Haiku id returns
   `ValidationException` naming the inference-profile requirement outright.
   The first of those is badly misleading: it reads as a model-access problem
   when it is actually a throughput-mode problem. Bare ids are
   provisioned-throughput only.
2. **The newest generation is not granted on this account.** A live sweep of
   `bedrock-runtime converse` found `us.anthropic.claude-sonnet-4-6`,
   `us.anthropic.claude-sonnet-4-5-20250929-v1:0`,
   `us.anthropic.claude-haiku-4-5-20251001-v1:0` and
   `amazon.titan-embed-text-v2:0` granted, while `us.anthropic.claude-sonnet-5`,
   `us.anthropic.claude-opus-5`, `us.anthropic.claude-opus-4-8` and
   `us.anthropic.claude-opus-4-7` were all refused. Sonnet 4.6 is the closest
   available model to the pinned Sonnet 5 and supports the tool calling the
   planner and compiler depend on.

**Impact.** None on architecture. Titan returns 1024 dimensions, matching
`VECTOR(1024)` exactly, so retrieval is unaffected. Latency figures must be
re-measured on Sonnet 4.6 rather than carried over from Groq. If Sonnet 5
access is granted later, swapping `BEDROCK_AGENT_MODEL_ID` back is a one-line
change with no code impact.

---

## Not deviations — bugs found and fixed during integration

Recorded because they were mis-reported as complete: `contracts.py` was never
wired to the engine; two incompatible `models.py` files coexisted; `run_txn` was
misused so the "O(1) atomic cascade" was not atomic; the Copilot's SQL validator
rejected any query selecting `created_at`; `admin/reset` replayed seed INSERTs
without clearing. See `Claude.md` for the full table.

**The most serious one, found while building Tier 1:** guided mode called
`check_remediation_eligibility`, recorded the answer, and then ran
`apply_remediation` regardless. Explore mode was safe because the planner reads
the result; the guided path replayed spec steps mechanically. A tier-2 incident
outside the rollback window would have been remediated in direct violation of
policy — and of the spec's own non-negotiable rule #3. Fixed and
regression-tested (`policy: an ineligible incident is never remediated`).

---

## 13. `PlaybookSpec` bounds widened, and `manual_steps` added

**Day-0 contract:** `preconditions` 1 to 6, `steps` 2 to 8, and every field of
`PlaybookSpec` frozen as the compiler's output contract.

**What was built:** `preconditions` up to 24, `steps` up to 64 with no minimum,
and a new `manual_steps` list.

**Why:** a runbook someone wrote in Confluence has as many steps as it has, and
most of them are prose a human performs rather than tool calls this engine can
make. Importing one was impossible under the old bounds, and importing is what
makes the product useful to a team that has not adopted the agent.

**Impact:** none on anything that parsed before. Widening a maximum cannot
invalidate an existing document, and the compiler is still constrained by its
own prompt and by `_safety_lint`. The `rule_citations` minimum of 1 was
deliberately left alone: a procedure with no provenance can never be found
stale, which would make the library quietly untrustworthy. An imported
procedure therefore has zero executable steps and is filtered out of retrieval
in `_phase2_pk_filter`, so it can be searched and governed but never replayed.

## 14. A twelfth contract function, rather than a wider signature

**Day-0 contract:** eleven functions in `contracts.py`, compared by exact
signature in the assertion suite.

**What was built:** `change_rule` keeps its exact four parameters and now
carries a rule's predicate and enforcement mode forward unchanged.
`change_rule_definition` and `create_rule` were added alongside it.

**Why:** changing how a rule decides is a policy change in the fullest sense and
has to move through the same cascade, but widening the frozen signature would
break the contract assertion and every caller's expectation of what it accepts.
Adding is additive; widening is not.

**Impact:** none. All eleven original signatures still assert clean.

## 15. `enforcement` is deliberately absent from the `get_rules` tool output

**What happened:** adding one field to that tool's return value changed the
compiled preconditions enough that a tier-3 incident stopped matching a runbook
it had matched before. Retrieval hit, precondition miss, silent loss of reuse,
and three autonomy assertions failed.

**Why it stays out:** that output is the compiler's input as well as the
planner's, so it is a model-shaped surface where any change is a behaviour
change. The planner does not need the field, because policy binds through
`check_remediation_eligibility` whatever `get_rules` says. It is exposed to
humans and to external agents through the API instead.

**Impact:** none, and one regression avoided. Recorded because the temptation to
add it back will recur.

## 16. Preconditions are compiled to predicates, not left as prose

**Day-0 contract:** `PlaybookSpec.preconditions` is a list of sentences, checked
before reuse by asking a model whether they hold.

**What was built:** the sentences remain, for a person reading the runbook, and
`precondition_predicate` was added beside them. That is what actually decides
whether a runbook applies.

**Why:** the prose check was an LLM call on the hot path, re-asking the same
question on every reuse and free to answer differently each time. It did: a
compiled precondition reading "the deploy is recent enough for the rollback
window to permit rollback" required date arithmetic from a raw timestamp, the
model got it wrong, retrieval hit, the precondition missed, and reuse died
silently. A reviewer hit it inside five minutes and the guided walkthrough hung.

**Impact:** the reuse path now calls no model at all. Retrieval is a vector
index, freshness is a join, preconditions are an evaluation. The
nondeterminism moved from the hot path to the cold one, where it is validated:
a compiled predicate must reference real fields, must reference policy
parameters that actually exist, and **must hold for the incident it was
compiled from**. Anything else is rejected in favour of a predicate derived
structurally from the trajectory. Older runbooks with no predicate still fall
back to the prose check, so nothing already stored broke.

The parameter check is not theoretical. The model's first attempt cited
`auto_remediate_tier.max_tier` when the parameter is `min_tier`; it resolved to
nothing, evaluated to UNKNOWN, was treated as satisfied, and would have passed
forever while checking nothing.

---

*Last updated: August 15, 2026*
