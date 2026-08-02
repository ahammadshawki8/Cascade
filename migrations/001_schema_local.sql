-- CASCADE Track B - Local Development Schema
-- This is identical to 001_schema.sql but WITHOUT the ivfflat vector index
-- (Vector indexing requires CockroachDB Cloud - not available in local Docker)
-- 
-- For STUB mode development, this is sufficient.
-- Track A will use the full schema with vector index on CockroachDB Cloud.

-- Rules (Policy) - Temporal Versioning
CREATE TABLE rules (
    rule_key VARCHAR(100) NOT NULL,
    version INT NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    body TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,  -- NULL = current version
    changed_by VARCHAR(100) NOT NULL,
    PRIMARY KEY (rule_key, version)
);

CREATE INDEX rules_current_idx ON rules (rule_key, valid_to) WHERE valid_to IS NULL;

-- Playbooks (Compiled Runbooks)
CREATE TABLE playbooks (
    playbook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    version INT NOT NULL DEFAULT 1,
    supersedes UUID REFERENCES playbooks(playbook_id),
    status_cache VARCHAR(20) NOT NULL DEFAULT 'candidate'
        CHECK (status_cache IN ('active','candidate','suspect','stale','archived')),
    spec JSONB NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0.30,
    uses INT NOT NULL DEFAULT 0,
    successes INT NOT NULL DEFAULT 0,
    failures INT NOT NULL DEFAULT 0,
    embedding VECTOR(1024),  -- Kept for schema compatibility, but index omitted
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- NOTE: Vector index omitted for local dev (requires CockroachDB Cloud)
-- CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops);
-- For STUB mode, this index isn't used anyway (retrieve() returns mocks)

-- Status + confidence index for filtering
CREATE INDEX playbooks_active_idx ON playbooks (domain, confidence DESC) 
    WHERE status_cache = 'active';

-- Playbook Dependencies (Provenance)
CREATE TABLE playbook_deps (
    playbook_id UUID NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    rule_key VARCHAR(100) NOT NULL,
    rule_version INT NOT NULL,
    citation TEXT,
    extraction_confidence FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (playbook_id, rule_key, rule_version),
    FOREIGN KEY (rule_key, rule_version) REFERENCES rules(rule_key, version)
);

CREATE INDEX deps_rule_idx ON playbook_deps (rule_key, rule_version);

-- Tasks (Working Memory)
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','succeeded','failed','awaiting_approval')),
    result JSONB,
    mode VARCHAR(10),
    playbook_id UUID REFERENCES playbooks(playbook_id),
    interrupt_flag BOOLEAN NOT NULL DEFAULT FALSE,
    interrupt_reason TEXT,
    scratchpad JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX tasks_running_idx ON tasks (created_at) WHERE status = 'running';
CREATE INDEX tasks_status_idx ON tasks (status, created_at DESC);

-- Episodes (Performance History)
CREATE TABLE episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    outcome VARCHAR(20) NOT NULL,
    mode VARCHAR(10) NOT NULL,
    steps INT NOT NULL,
    latency_ms INT NOT NULL,
    tokens INT NOT NULL,
    s3_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX episodes_task_idx ON episodes (task_id);
CREATE INDEX episodes_mode_idx ON episodes (mode, created_at DESC);

-- Outbox (Transactional Outbox Pattern)
CREATE TABLE outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL
        CHECK (kind IN ('compile','rule_changed','relearn','recheck','postmortem')),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMPTZ
);

CREATE INDEX outbox_unprocessed_idx ON outbox (created_at) 
    WHERE processed_at IS NULL AND claimed_at IS NULL;

-- Audit Log (Append-Only)
CREATE TABLE audit_log (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    details JSONB NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_kind_idx ON audit_log (kind, at DESC);

-- Extension Tables (Wire up Week 4+)

-- Approvals (Autonomy Gating)
CREATE TABLE approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    playbook_id UUID REFERENCES playbooks(playbook_id),
    step_index INT NOT NULL,
    action TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','expired')),
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)
);

CREATE INDEX approvals_pending_idx ON approvals (requested_at) 
    WHERE status = 'pending';

-- Insights (Trend Detection)
CREATE TABLE insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    related_rule_key VARCHAR(100),
    suggested_params JSONB,
    evidence JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX insights_active_idx ON insights (created_at DESC) 
    WHERE NOT dismissed;

-- Postmortems
CREATE TABLE postmortems (
    postmortem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL UNIQUE REFERENCES episodes(episode_id),
    s3_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX postmortems_episode_idx ON postmortems (episode_id);

-- Mock World (Demo Environment)

CREATE TABLE mock_incidents (
    incident_id VARCHAR(20) PRIMARY KEY,
    kind VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    service_tier INT NOT NULL,
    deploy_timestamp TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE mock_action_log (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(20) NOT NULL REFERENCES mock_incidents(incident_id),
    action VARCHAR(50) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX action_log_incident_idx ON mock_action_log (incident_id, at DESC);
