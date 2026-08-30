# Agent trajectories

Exported from what was recorded at the time, not written up afterwards. Each run stores its own call sequence in `episodes.trajectory`, and the retrieval decisions that explain the path it took are audit rows. So these are the calls that happened, including the refused ones.


Exported from `https://d3t9yaye62k6ve.cloudfront.net`.


Regenerate with:

```bash
python -m eval.export_trajectories --api <host> --admin-token <token>
```


---

## Explore: nothing in memory

The planner decides each step. Policy is consulted through a tool rather than described in the prompt, so the model cannot talk its way past a rule it does not like.


### What was asked

```
Remediate INC-1001
```


### The incident, as the tools saw it

```json
{
  "incident_id": "INC-1001",
  "kind": "bad_deploy",
  "severity": "P1",
  "service_name": "svc-checkout",
  "service_tier": 2,
  "state": "mitigated",
  "deploy_timestamp": "2026-08-30T01:02:47.213327+00:00",
  "deploy_age_hours": 2.0358127375
}
```


### Calls the run made


**Step 0 — `get_incident`**
_4 ms_


Arguments:
```json
{
  "incident_id": "INC-1001"
}
```

What the tool returned:
```json
{
  "cpu_usage": null,
  "created_at": "2026-08-30T03:02:47.213327+00:00",
  "deploy_timestamp": "2026-08-30T01:02:47.213327+00:00",
  "error_rate": null,
  "incident_id": "INC-1001",
  "kind": "bad_deploy",
  "service_name": "svc-checkout",
  "service_tier": 2,
  "severity": "P1",
  "state": "open"
}
```

**Step 1 — `get_rules`**
_4 ms_


Arguments:
```json
{
  "domain": "incident"
}
```

What the tool returned:
```json
{
  "domain": "incident",
  "rules": [
    {
      "body": "Automated remediation is allowed only for services at tier {min_tier} or higher. Tier 1 (production-critical) services require manual approval.",
      "params": {
        "min_tier": 2
      },
      "rule_key": "incident.auto_remediate_tier",
      "version": 1
    },
    {
      "body": "On-call must be notified after any automated remediation action is taken.",
      "params": {},
      "rule_key": "incident.notify",
      "version": 1
    },
    {
      "body": "Rollback is allowed only if the deploy happened within the last {hours} hours. Beyond this window, rollback is considered too risky.",
      "params": {
        "hours": 24
      },
      "rule_key": "incident.rollback_window",
      "version": 1
    },
    {
      "body": "Maximum one automated remediation action is allowed per incident. Multiple automated actions require escalation.",
      "params": {},
      "rule_key": "incident.single_action",
      "version": 1
    }
  ]
}
```

**Step 2 — `check_remediation_eligibility`**
_14 ms_


Arguments:
```json
{
  "action": "rollback",
  "incident_id": "INC-1001"
}
```

What the tool returned:
```json
{
  "action": "rollback",
  "eligible": true,
  "reasons": [],
  "rule_versions_used": {
    "incident.auto_remediate_tier": 1,
    "incident.rollback_window": 1,
    "incident.single_action": 1
  }
}
```

**Step 3 — `apply_remediation`**
_28 ms_


Arguments:
```json
{
  "action": "rollback",
  "incident_id": "INC-1001"
}
```

What the tool returned:
```json
{
  "action": "rollback",
  "action_id": "9a6c838a-6fd5-46cf-855e-8889877fdda9",
  "incident_state": "mitigated",
  "outcome": "success",
  "success": true
}
```

**Step 4 — `notify_oncall`**
_30 ms_


Arguments:
```json
{
  "incident_id": "INC-1001",
  "message": "Automated rollback was successfully applied to INC-1001 (svc-checkout, Tier 2, bad_deploy, P1). The incident state is now 'mitigated'. Action ID: 9a6c838a-6fd5-46cf-855e-8889877fdda9. Please verify service health and close the incident if confirmed stable."
}
```

What the tool returned:
```json
{
  "message": "Automated rollback was successfully applied to INC-1001 (svc-checkout, Tier 2, bad_deploy, P1). The incident state is now 'mitigated'. Action ID: 9a6c838a-6fd5-46cf-855e-8889877fdda9. Please verify service health and close the incident if confirmed stable.",
  "notification_id": "aabbdadb-a6b0-4988-a98c-3818fea50692",
  "sent": true
}
```

### Outcome

- Mode: `explore`
- Result: `remediated`
- Status: `succeeded`
- Steps: 5
- Wall clock: 14140 ms
- Planner tokens: 8893


---

## Guided: a runbook matched and was replayed

No model call anywhere on this path. Retrieval is a vector index, freshness is a join, and the preconditions are a predicate evaluation, so the same incident gets the same answer every time.


### What was asked

```
Remediate INC-1002
```


### The incident, as the tools saw it

```json
{
  "incident_id": "INC-1002",
  "kind": "bad_deploy",
  "severity": "P2",
  "service_name": "svc-search",
  "service_tier": 2,
  "state": "mitigated",
  "deploy_timestamp": "2026-08-30T00:02:47.213327+00:00",
  "deploy_age_hours": 3.0356695499999997
}
```


### Calls the run made


**Step 0 — `get_incident`**
_4 ms_


Arguments:
```json
{
  "incident_id": "INC-1002"
}
```

What the tool returned:
```json
{
  "cpu_usage": null,
  "created_at": "2026-08-30T03:02:47.213327+00:00",
  "deploy_timestamp": "2026-08-30T00:02:47.213327+00:00",
  "error_rate": null,
  "incident_id": "INC-1002",
  "kind": "bad_deploy",
  "service_name": "svc-search",
  "service_tier": 2,
  "severity": "P2",
  "state": "open"
}
```

**Step 1 — `get_rules`**
_5 ms_


Arguments:
```json
{
  "domain": "incident"
}
```

What the tool returned:
```json
{
  "domain": "incident",
  "rules": [
    {
      "body": "Automated remediation is allowed only for services at tier {min_tier} or higher. Tier 1 (production-critical) services require manual approval.",
      "params": {
        "min_tier": 2
      },
      "rule_key": "incident.auto_remediate_tier",
      "version": 1
    },
    {
      "body": "On-call must be notified after any automated remediation action is taken.",
      "params": {},
      "rule_key": "incident.notify",
      "version": 1
    },
    {
      "body": "Rollback is allowed only if the deploy happened within the last {hours} hours. Beyond this window, rollback is considered too risky.",
      "params": {
        "hours": 24
      },
      "rule_key": "incident.rollback_window",
      "version": 1
    },
    {
      "body": "Maximum one automated remediation action is allowed per incident. Multiple automated actions require escalation.",
      "params": {},
      "rule_key": "incident.single_action",
      "version": 1
    }
  ]
}
```

**Step 2 — `check_remediation_eligibility`**
_12 ms_


Arguments:
```json
{
  "action": "rollback",
  "incident_id": "INC-1002"
}
```

What the tool returned:
```json
{
  "action": "rollback",
  "eligible": true,
  "reasons": [],
  "rule_versions_used": {
    "incident.auto_remediate_tier": 1,
    "incident.rollback_window": 1,
    "incident.single_action": 1
  }
}
```

**Step 3 — `apply_remediation`**
_23 ms_


Arguments:
```json
{
  "action": "rollback",
  "incident_id": "INC-1002"
}
```

What the tool returned:
```json
{
  "action": "rollback",
  "action_id": "023c3cf3-9610-43db-854f-b73be147016a",
  "incident_state": "mitigated",
  "outcome": "success",
  "success": true
}
```

**Step 4 — `notify_oncall`**
_24 ms_


Arguments:
```json
{
  "incident_id": "INC-1002",
  "message": "Automated rollback was successfully applied to INC-1002. The incident state is now 'mitigated'. Please verify service health and close the incident if confirmed stable."
}
```

What the tool returned:
```json
{
  "message": "Automated rollback was successfully applied to INC-1002. The incident state is now 'mitigated'. Please verify service health and close the incident if confirmed stable.",
  "notification_id": "11901919-1dcf-4a1a-9b56-bb1bf325b4b2",
  "sent": true
}
```

### Outcome

- Mode: `guided`
- Result: `remediated`
- Status: `succeeded`
- Steps: 5
- Wall clock: 2462 ms
- Planner tokens: 0


---

## Refused: matched by meaning, refused on provenance

The runbook was still the closest match by vector distance and still looked healthy. It was refused because a rule it was compiled against has moved. This is the behaviour the whole system exists for.


### What was asked

```
Remediate INC-1009
```


### The incident, as the tools saw it

```json
{
  "incident_id": "INC-1009",
  "kind": "bad_deploy",
  "severity": "P3",
  "service_name": "svc-analytics",
  "service_tier": 3,
  "state": "open",
  "deploy_timestamp": "2026-08-29T22:02:47.213327+00:00",
  "deploy_age_hours": 5.035524713611111
}
```


### Calls the run made


**Step 0 — `get_incident`**
_4 ms_


Arguments:
```json
{
  "incident_id": "INC-1009"
}
```

What the tool returned:
```json
{
  "cpu_usage": null,
  "created_at": "2026-08-30T03:02:47.213327+00:00",
  "deploy_timestamp": "2026-08-29T22:02:47.213327+00:00",
  "error_rate": null,
  "incident_id": "INC-1009",
  "kind": "bad_deploy",
  "service_name": "svc-analytics",
  "service_tier": 3,
  "severity": "P3",
  "state": "open"
}
```

**Step 1 — `check_remediation_eligibility`**
_15 ms_


Arguments:
```json
{
  "action": "rollback",
  "incident_id": "INC-1009"
}
```

What the tool returned:
```json
{
  "action": "rollback",
  "eligible": false,
  "reasons": [
    "deploy was 5h ago, outside the 4h rollback window"
  ],
  "rule_versions_used": {
    "incident.auto_remediate_tier": 1,
    "incident.rollback_window": 2,
    "incident.single_action": 1
  }
}
```

**Step 2 — `notify_oncall`**
_29 ms_


Arguments:
```json
{
  "incident_id": "INC-1009",
  "message": "INC-1009 (bad_deploy on svc-analytics, Tier 3, P3) cannot be automatically remediated. Rollback is ineligible because the deploy occurred 5 hours ago, exceeding the 4-hour rollback window (policy: incident.rollback_window v2). Manual intervention is required."
}
```

What the tool returned:
```json
{
  "message": "INC-1009 (bad_deploy on svc-analytics, Tier 3, P3) cannot be automatically remediated. Rollback is ineligible because the deploy occurred 5 hours ago, exceeding the 4-hour rollback window (policy: incident.rollback_window v2). Manual intervention is required.",
  "notification_id": "8a9f0687-1c7f-4128-88dc-64a84067ec80",
  "sent": true
}
```

### Why it was refused

```json
[
  {
    "compiled_against": 1,
    "head": 2,
    "rule_key": "incident.rollback_window"
  }
]
```


Note that the refusal names the rule, the version the runbook expects and the version that is live. A refusal a reader cannot act on is only half a refusal.


### Outcome

- Mode: `explore`
- Result: `escalated`
- Status: `succeeded`
- Steps: 3
- Wall clock: 8950 ms
- Planner tokens: 5418


---

## Not represented in this export

These behaviours exist but no recent run exercised them, so nothing is shown rather than something being invented:

- Refused: matched, then failed its own preconditions
- Gated: parked for a human
