-- CASCADE Track B - Database Schema
-- Day 0 - FROZEN after merge
-- CockroachDB Serverless, v26.x

-- Enable vector index feature (if needed)
-- SET CLUSTER SETTING feature.vector_index.enabled = true;

-- =============================================================================
-- Policy Rules (Versioned)
-- =============================================================================

CREATE TABLE IF NOT EXISTS rules (
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

-- =============================================================================
-- Compiled Playbooks
-- =============================================================================

CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    version INT NOT NULL DEFAULT 1,
    supersedes UUID REFERENCES playbooks(playbook_id),  -- Lineage
    status_cache VARCHAR(20) NOT NULL DEFAULT 'candidate',  -- active|candidate|suspect|stale|archived
    spec JSONB NOT NULL,  -- Full PlaybookSpec
    confidence FLOAT NOT NULL DEFAULT 0.5,
    uses INT NOT NULL DEFAULT 0,
    successes INT NOT NULL DEFAULT 0,
    failures INT NOT NULL DEFAULT 0,
    embedding VECTOR(1024),  -- Titan V2 embeddings
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CRITICAL: Vector index for Phase 1 ANN query
CREATE INDEX pb_embed_idx ON playbooks USING ivfflat (embedding vector_l2_ops);

-- Status + confidence index for filtering
CREATE INDEX playbooks_active_idx ON playbooks (domain, confidence DESC) 
    WHERE status_cache = 'active';

-- =============================================================================
-- Playbook Dependencies (Provenance)
-- =============================================================================

CREATE TABLE IF NOT EXISTS playbook_deps (
    playbook_id UUID NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    rule_key VARCHAR(100) NOT NULL,
    rule_version INT NOT NULL,
    citation TEXT,  -- Where in spec this rule was cited
    extraction_confidence FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (playbook_id, rule_key, rule_version),
    FOREIGN KEY (rule_key, rule_version) REFERENCES rules(rule_key, version)
);

CREATE INDEX deps_rule_idx ON playbook_deps (rule_key, rule_version);

-- =============================================================================
-- Tasks
-- =============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',  -- queued|running|succeeded|failed|awaiting_approval
    result JSONB,
    mode VARCHAR(10),  -- explore|guided
    playbook_id UUID REFERENCES playbooks(playbook_id),
    interrupt_flag BOOLEAN NOT NULL DEFAULT FALSE,
    interrupt_reason TEXT,
    scratchpad JSONB,  -- For interrupt resume
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX tasks_running_idx ON tasks (created_at) WHERE status = 'running';
CREATE INDEX tasks_status_idx ON tasks (status, created_at DESC);

-- =============================================================================
-- Episodes (Performance History)
-- =============================================================================

CREATE TABLE IF NOT EXISTS episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    outcome VARCHAR(20) NOT NULL,  -- success|failed
    mode VARCHAR(10) NOT NULL,  -- explore|guided
    steps INT NOT NULL,
    latency_ms INT NOT NULL,
    tokens INT NOT NULL,
    s3_key TEXT,  -- Full trajectory in S3
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX episodes_task_idx ON episodes (task_id);
CREATE INDEX episodes_mode_idx ON episodes (mode, created_at DESC);

-- =============================================================================
-- Transactional Outbox
-- =============================================================================

CREATE TABLE IF NOT EXISTS outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,  -- compile|rule_changed|relearn|recheck|postmortem
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMPTZ
);

CREATE INDEX outbox_unprocessed_idx ON outbox (created_at) 
    WHERE processed_at IS NULL AND claimed_at IS NULL;

-- =============================================================================
-- Audit Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,  -- rule_changed|playbook_compiled|task_executed|etc
    actor VARCHAR(100) NOT NULL,
    details JSONB NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_kind_idx ON audit_log (kind, at DESC);

-- =============================================================================
-- Extension Tables (Wire up Week 4+)
-- =============================================================================

-- Autonomy Gating
CREATE TABLE IF NOT EXISTS approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    playbook_id UUID REFERENCES playbooks(playbook_id),
    step_index INT NOT NULL,
    action TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)
);

CREATE INDEX approvals_pending_idx ON approvals (requested_at) WHERE status = 'pending';

-- Trend Detection
CREATE TABLE IF NOT EXISTS insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,  -- threshold_trend|failure_pattern|coverage_gap
    summary TEXT NOT NULL,
    related_rule_key VARCHAR(100),
    suggested_params JSONB,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX insights_active_idx ON insights (created_at DESC) WHERE NOT dismissed;

-- Postmortems
CREATE TABLE IF NOT EXISTS postmortems (
    postmortem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    s3_key TEXT NOT NULL,  -- Markdown in S3
    summary TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX postmortems_episode_idx ON postmortems (episode_id);

-- =============================================================================
-- Mock World (For Demo)
-- =============================================================================

CREATE TABLE IF NOT EXISTS mock_incidents (
    incident_id VARCHAR(20) PRIMARY KEY,  -- INC-1001, INC-1002, etc
    kind VARCHAR(50) NOT NULL,  -- bad_deploy|error_spike|resource_exhaustion
    severity VARCHAR(10) NOT NULL,  -- P1|P2|P3
    service_name VARCHAR(100) NOT NULL,
    service_tier VARCHAR(20) NOT NULL,  -- production|staging|dev
    deploy_timestamp TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL DEFAULT 'open',  -- open|mitigated|resolved
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mock_action_log (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(20) NOT NULL REFERENCES mock_incidents(incident_id),
    action VARCHAR(50) NOT NULL,  -- rollback|restart|scale_up|notify
    outcome VARCHAR(20) NOT NULL,  -- success|failed
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX action_log_incident_idx ON mock_action_log (incident_id, at DESC);
