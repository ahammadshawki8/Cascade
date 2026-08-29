-- Cascade — Migration 006: from demo to platform
--
-- Four things change, and they are all seams that already existed implicitly.
--
--  1. A rule learns how to evaluate itself (`predicate`), so policy stops being
--     three hardcoded comparisons in tools.py and becomes data. `enforcement`
--     lets a rule be cited and versioned without gating anything, which is the
--     zero-friction on-ramp: staleness detection never needed the predicate,
--     only provenance did.
--
--  2. A procedure records where it came from (`origin`), so an imported runbook
--     and a compiled one are the same governed object with different
--     provenance. This is also what lets a demo reset restore the sample world
--     without destroying anything the user made.
--
--  3. API keys, so an external agent can call the memory layer as itself,
--     attributably and revocably.
--
--  4. Connections and their call ledger, so a step can reach a real system —
--     with idempotency enforced locally rather than trusted to the remote.

BEGIN;

-- ============================================================================
-- 1. POLICY BECOMES DATA
-- ============================================================================

-- The predicate a rule evaluates. NULL means the rule carries prose only: it
-- is still cited, versioned and cascaded, it simply does not gate execution.
ALTER TABLE rules ADD COLUMN IF NOT EXISTS predicate JSONB;

-- advisory  — cited and versioned, never blocks
-- shadow    — evaluated and recorded, never blocks
-- enforcing — evaluated, blocks when it fails
--
-- Deliberately not a CHECK constraint: the set is validated in app/core/policy
-- where the error can name the allowed values, and keeping it out of the schema
-- means adding a mode later is not a migration.
ALTER TABLE rules ADD COLUMN IF NOT EXISTS enforcement TEXT NOT NULL DEFAULT 'advisory';

-- Which facts a rule may reference, so the UI can offer fields rather than
-- asking someone to memorise them. Per domain, not per rule.
CREATE TABLE IF NOT EXISTS domain_facts (
    domain      VARCHAR(50)  NOT NULL,
    field       VARCHAR(64)  NOT NULL,
    kind        VARCHAR(16)  NOT NULL,   -- number | string | boolean
    label       TEXT         NOT NULL,
    choices     JSONB,                   -- for enumerated strings
    PRIMARY KEY (domain, field)
);

INSERT INTO domain_facts (domain, field, kind, label, choices) VALUES
    ('incident', 'kind', 'string', 'What kind of failure',
     '["bad_deploy","error_spike","resource_exhaustion"]'),
    ('incident', 'severity', 'string', 'Reported severity', '["P1","P2","P3"]'),
    ('incident', 'service_name', 'string', 'Service name', NULL),
    ('incident', 'service_tier', 'number', 'Service tier (1 = most critical)', NULL),
    ('incident', 'state', 'string', 'Incident state',
     '["open","mitigated","resolved","escalated"]'),
    ('incident', 'deploy_age_hours', 'number', 'Hours since the last deploy', NULL),
    ('incident', 'error_rate', 'number', 'Error rate', NULL),
    ('incident', 'cpu_usage', 'number', 'CPU usage', NULL),
    ('incident', 'action', 'string', 'Action being proposed',
     '["rollback","restart","scale_up"]'),
    ('incident', 'prior_actions', 'number', 'Automated actions already applied', NULL)
ON CONFLICT (domain, field) DO NOTHING;

-- Backfill the seeded rules with the predicates that were hardcoded in
-- tools.py. The evaluator is proved faithful by the existing assertion suite
-- passing unchanged against these rows.
UPDATE rules SET
    predicate = '{
        "require": {"field": "service_tier", "op": "gte", "param": "min_tier"},
        "deny": "service tier {service_tier} is below the automation floor of tier {min_tier} - manual approval required"
    }',
    enforcement = 'enforcing'
WHERE rule_key = 'incident.auto_remediate_tier';

UPDATE rules SET
    predicate = '{
        "when": {"field": "action", "op": "eq", "value": "rollback"},
        "require": {"field": "deploy_age_hours", "op": "lte", "param": "hours"},
        "deny": "deploy was {deploy_age_hours}h ago, outside the {hours}h rollback window",
        "unknown": "no deploy timestamp - rollback window unverifiable"
    }',
    enforcement = 'enforcing'
WHERE rule_key = 'incident.rollback_window';

UPDATE rules SET
    predicate = '{
        "require": {"field": "prior_actions", "op": "eq", "value": 0},
        "deny": "incident already has an automated remediation - single-action limit reached"
    }',
    enforcement = 'enforcing'
WHERE rule_key = 'incident.single_action';

-- incident.notify gates nothing; it is an obligation, not a precondition. It
-- stays advisory, which is exactly what it always was in practice.
UPDATE rules SET enforcement = 'advisory' WHERE rule_key = 'incident.notify';

-- ============================================================================
-- 2. PROCEDURES CARRY THEIR ORIGIN
-- ============================================================================

-- compiled — the agent learned it from a successful run
-- imported — brought in from outside (Markdown, YAML, JSON)
-- authored — written by hand in the console
-- merged   — generalized from several members (T3.8)
ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'compiled';

-- Where an imported procedure came from: a URL, a filename, a ticket.
ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS source_ref TEXT;

-- Existing merged runbooks predate the column; name them correctly.
UPDATE playbooks SET origin = 'merged'
WHERE origin = 'compiled' AND name LIKE 'generalized%';

-- ============================================================================
-- 3. API KEYS — an external agent calling as itself
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    key_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    -- SHA-256 of the presented key. The key itself is shown once, at creation,
    -- and is not recoverable afterwards.
    key_hash      STRING      NOT NULL UNIQUE,
    -- The first characters, for identifying a key in a list without holding it.
    key_prefix    STRING      NOT NULL,
    scopes        STRING[]    NOT NULL DEFAULT ARRAY['memory:read'],
    client        TEXT,                       -- claude-code | claude-desktop | cursor | http
    created_by    TEXT        NOT NULL DEFAULT 'admin',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    call_count    INT         NOT NULL DEFAULT 0,
    revoked_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys (key_hash) WHERE revoked_at IS NULL;

-- What agents actually asked, so the console can show the memory layer being
-- used from outside rather than asserting that it can be.
CREATE TABLE IF NOT EXISTS agent_activity (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id      UUID REFERENCES api_keys(key_id) ON DELETE CASCADE,
    key_name    TEXT,
    operation   TEXT        NOT NULL,   -- check | find | register | run
    detail      JSONB       NOT NULL DEFAULT '{}',
    verdict     TEXT,                   -- valid | stale | not_found | ok
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_activity_at_idx ON agent_activity (at DESC);

-- ============================================================================
-- 4. CONNECTIONS — reaching a real system
-- ============================================================================

CREATE TABLE IF NOT EXISTS connections (
    connection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    -- discord | slack | webhook. All three are the same HTTP transport with a
    -- different payload shape, which is why adding one is a template, not code.
    kind          TEXT        NOT NULL,
    -- The destination URL. Held here rather than in Secrets Manager because a
    -- webhook URL *is* the credential and the whole point is that a judge can
    -- paste one in without an AWS account; it is never returned by any read
    -- endpoint. See routers/connections.py.
    endpoint      TEXT        NOT NULL,
    config        JSONB       NOT NULL DEFAULT '{}',
    -- live    — really call it
    -- dry_run — build the request, record it, do not send
    mode          TEXT        NOT NULL DEFAULT 'dry_run',
    enabled       BOOL        NOT NULL DEFAULT true,
    -- Which tool this connection backs. NULL means it is only used for tests.
    tool_name     TEXT,
    created_by    TEXT        NOT NULL DEFAULT 'admin',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_ok_at    TIMESTAMPTZ,
    last_error    TEXT,
    failures      INT         NOT NULL DEFAULT 0
);

-- The idempotency ledger and the outbound audit trail, in one table.
--
-- The unique constraint is the safety property: resume-by-replay re-runs a
-- whole task, and without a local record a replayed step would page the on-call
-- twice. Remote services are not trusted to honour Idempotency-Key.
CREATE TABLE IF NOT EXISTS connector_calls (
    call_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id   UUID        NOT NULL REFERENCES connections(connection_id) ON DELETE CASCADE,
    task_id         UUID,
    step_index      INT,
    idempotency_key TEXT        NOT NULL,
    request         JSONB       NOT NULL DEFAULT '{}',
    response        JSONB,
    status_code     INT,
    duration_ms     INT,
    outcome         TEXT        NOT NULL DEFAULT 'sent',  -- sent | dry_run | failed | replayed
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS connector_calls_at_idx ON connector_calls (at DESC);

COMMIT;
