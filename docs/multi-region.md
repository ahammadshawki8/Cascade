# Survivability and multi-region (T3.2)

**Status:** zone survival is **in force on the demo cluster and verifiable in
the app**. Region survival is configured here but not applied, because the
cluster spans one region and claiming otherwise would be false.

Read it live rather than believing this file: the **Architecture** view in the
running app calls `GET /api/architecture/survivability`, which returns
`SHOW REGIONS`, `SHOW SURVIVAL GOAL` and `SHOW ZONE CONFIGURATION` straight
from the cluster.

## What is actually in force, today

```
SHOW SURVIVAL GOAL FROM DATABASE cascade   ->  zone

SHOW REGIONS FROM DATABASE cascade
  aws-us-east-1   [1a, 1b, 1c, 1d, 1f]

SHOW ZONE CONFIGURATION FROM DATABASE cascade
  num_replicas = 3
  num_voters = 3
  constraints = '{+region=aws-us-east-1: 1}'
  voter_constraints = '[+region=aws-us-east-1]'
  lease_preferences = '[[+region=aws-us-east-1]]'
```

Three voting replicas, placed in separate AWS availability zones inside
`aws-us-east-1`. Losing an availability zone costs a leaseholder re-election
and nothing else: no failover script, no promotion, no data loss, and the
application never learns that it happened.

That is a real distributed-systems property and it is switched on. It is not
region survival, and the difference is stated plainly below rather than blurred.

## Getting from zone survival to region survival

One statement, once the cluster spans three or more regions:

```sql
ALTER DATABASE cascade SURVIVE REGION FAILURE;
```

The regions themselves are added at the cluster level in the CockroachDB Cloud
console, which is a provisioning and billing decision rather than a code
change. **Nothing in this repository changes.** No connection string, no query,
no migration: the application does not know or care how many regions it is
spread over, which is the entire argument for expressing survivability
declaratively instead of building failover into the app.

The rest of this document is what that configuration would be, and why.

---

CockroachDB's multi-region primitives are the reason it is the right database
for this system, so what follows records exactly what Cascade configures and
why — including the parts deliberately **not** turned on for the hackathon
cluster.

---

## Why it matters here

Cascade is an incident-response system. It is least useful at exactly the
moment a region is failing — which is when an on-call engineer most needs it.
A memory layer that goes down with the outage it exists to remediate is a
liability.

CockroachDB expresses this declaratively rather than through failover
scripting: you state the survival goal, and the database places replicas to
satisfy it.

---

## Configuration

```sql
ALTER DATABASE cascade SET PRIMARY REGION "us-east-1";
ALTER DATABASE cascade ADD REGION "us-west-2";
ALTER DATABASE cascade ADD REGION "eu-west-1";

-- Survive losing an entire region, not merely a node.
ALTER DATABASE cascade SURVIVE REGION FAILURE;
```

### Table localities — chosen per access pattern

```sql
-- Policy is read on every single eligibility check and written rarely.
-- GLOBAL gives every region a local, non-stale read at the cost of slower
-- writes, which is precisely the right trade for rules.
ALTER TABLE rules SET LOCALITY GLOBAL;

-- The same argument applies to compiled memory: retrieval reads it constantly,
-- compilation writes it occasionally.
ALTER TABLE playbooks     SET LOCALITY GLOBAL;
ALTER TABLE playbook_deps SET LOCALITY GLOBAL;

-- Operational data is written far more than it is read across regions, and an
-- incident is handled by whoever is on call in that region.
ALTER TABLE tasks    SET LOCALITY REGIONAL BY ROW;
ALTER TABLE episodes SET LOCALITY REGIONAL BY ROW;
ALTER TABLE outbox   SET LOCALITY REGIONAL BY ROW;

-- Audit is append-only and read rarely; regional-by-table keeps writes local.
ALTER TABLE audit_log SET LOCALITY REGIONAL BY TABLE IN "us-east-1";
```

`REGIONAL BY ROW` needs a `crdb_region` column, which CockroachDB adds
automatically and defaults from the gateway region — so a task created by the
`us-west-2` API instance is stored in `us-west-2` and read locally there.

---

## What this changes in the application

Very little, and that is the point.

| Concern | Effect |
|---------|--------|
| `rules` reads | `GLOBAL` — local latency in every region, no staleness |
| Freshness join | Unchanged; reads `rules` + `playbook_deps`, both `GLOBAL` |
| Cascade transaction | Still 4 writes. `rules` is `GLOBAL`, so the write is slower but the transaction shape does not change |
| Vector retrieval | `playbooks` is `GLOBAL`; the ANN query stays local |
| Outbox / worker | `REGIONAL BY ROW`; each region's worker drains its own rows |
| **Interrupts** | **This is the one that needs application work — see below** |

### Interrupts across regions

`InterruptBus` is in-process (decision D4). Multi-region means multiple API
instances, so a rule change handled in `us-east-1` cannot reach an executor
running in `eu-west-1` through the local bus.

That is what **T3.7** (`core/fanout.py`) exists for: the cascade publishes the
interrupt to SNS, every instance subscribes at `POST /internal/fanout`, and
each applies it to its own bus.

The durable `tasks.interrupt_flag` remains the correctness guarantee. SNS is
best-effort speed — a missed broadcast costs at most one extra step before the
durable check catches it, which is the same failure model as the post-commit
SQS publish (D5).

Enable with:

```bash
ENABLE_SNS_FANOUT=true
SNS_BUS_TOPIC_ARN=arn:aws:sns:us-east-1:<account>:cascade-bus
```

---

## Not applied to the demo cluster

The hackathon runs on a single-region free-tier cluster. `SURVIVE REGION
FAILURE` requires at least three regions, so applying these statements there
would fail — and asserting multi-region survivability we have not demonstrated
would be worse than saying plainly that we scoped it out.

To demonstrate it for real:

1. Provision a multi-region CockroachDB Cloud cluster (paid tier)
2. Apply the statements above after `002_seed.sql`
3. Confirm placement:
   ```sql
   SHOW REGIONS FROM DATABASE cascade;
   SELECT table_name, locality FROM [SHOW TABLES] WHERE locality IS NOT NULL;
   ```
4. Deploy an ECS service per region behind the same CloudFront distribution
5. Set `ENABLE_SNS_FANOUT=true` so interrupts cross regions
6. Verify by killing a region and re-running the demo

---

*Last updated: August 4, 2026*
