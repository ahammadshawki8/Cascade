-- Cascade — Production hardening (Tier 3)
--
-- Additive and idempotent. Safe to re-run, and safe to apply to a cluster that
-- already has data.

-- ============================================================================
-- T3.4 — ROW-LEVEL TTL
-- ============================================================================
-- `audit_log` and `episodes` are append-only and otherwise grow forever. This
-- was recommendation R2 from docs/skills-review.md.
--
-- CockroachDB expires rows with a background job, so this is retention rather
-- than a cron we have to write and monitor ourselves.
--
-- audit_log is kept far longer than episodes on purpose: it is the compliance
-- record of who changed policy, and the demo reset deliberately preserves it
-- (spec §3.4). Episodes are performance telemetry and age out sooner.

ALTER TABLE audit_log SET (
    ttl_expiration_expression = $$ at + INTERVAL '90 days' $$,
    ttl_job_cron = '@daily'
);

ALTER TABLE episodes SET (
    ttl_expiration_expression = $$ created_at + INTERVAL '30 days' $$,
    ttl_job_cron = '@daily'
);

-- Outbox rows are transient: once processed they are pure history, and the
-- sweeper only ever looks at unprocessed ones.
ALTER TABLE outbox SET (
    ttl_expiration_expression = $$ created_at + INTERVAL '7 days' $$,
    ttl_job_cron = '@daily'
);

-- Deliberately NOT given a TTL:
--   rules          temporal history is the provenance record; losing an old
--                  version would break freshness for any playbook pinned to it
--   playbooks      the learned memory itself
--   playbook_deps  the provenance edges
--   anti_playbooks negative memory is small and slow-moving

-- ============================================================================
-- T3.1 — RBAC support
-- ============================================================================
-- audit_log.actor already exists and is now written with a real identity
-- rather than a shared literal. Index it so "what did this person change"
-- is a fast question.
CREATE INDEX IF NOT EXISTS audit_actor_time_idx ON audit_log (actor, at DESC);

-- ============================================================================
-- T3.8 — Playbook lineage for merges
-- ============================================================================
-- `supersedes` already models v1 -> v2 from a re-learn. A merge is different:
-- several near-duplicate runbooks collapse into one generalized runbook, and
-- we want to keep the record of which ones were folded in.
ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS merged_from JSONB;
ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS generalized BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS playbooks_generalized_idx
    ON playbooks (domain, confidence DESC) WHERE generalized;
