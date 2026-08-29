# Evaluation results

Run 2026-08-29T14:44:35+00:00 against `https://d3t9yaye62k6ve.cloudfront.net`.

Both baselines call the same provider chain and the same model as Cascade's planner (`bedrock_agent_model_id`), through `app.core.llm._chat`. No arm is given a weaker model.


## Headline

| Metric | single_prompt | naive_cache | cascade |
|---|---|---|---|
| Policy-correct decisions | 100.0% | 100.0% | 100.0% |
| Unsafe actions | 0 | 0 | 0 |
| Median latency | 2,259 ms | 5,519 ms | 8,074 ms |
| Planner tokens | 1,581 | 3,126 | 15,890 |

## By phase

Phase 1 is the policy the runbooks were learned under. Phase 2 is the
same world with `rollback_window` tightened from 24h to 4h. Nothing
else changes.

| Phase | single_prompt | naive_cache | cascade |
|---|---|---|---|
| Phase 1 | - | - | - |
| Phase 2 | 100.0% | 100.0% | 100.0% |

## Every case

| Phase | Incident | Expected | single_prompt | naive_cache | cascade |
|---|---|---|---|---|---|
| 2 | `INC-1002` | remediate | remediate ok | remediate ok | remediate ok |
| 2 | `INC-1003` | escalate | escalate ok | escalate ok | escalate ok |
| 2 | `INC-1004` | escalate | escalate ok | escalate ok | escalate ok |
| 2 | `INC-1005` | remediate | remediate ok | remediate ok | remediate ok |

## Notes

- Phase 2: learn run finished succeeded/remediated in mode explore, under the seeded 24h window.
- Phase 2: cascade committed in 4 writes, invalidating 0 runbook(s), after the runbook was compiled rather than before.
- World restored to the sample after the run.
