-- Cascade — Database Schema (Day 0 Contract)
-- FROZEN AFTER DAY 0. Changes require a contract PR.

-- Enable vector index setting for local dev (Cloud manages this automatically)
-- SET CLUSTER SETTING feature.vector_index.enabled = true;

BEGIN;

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Rules: versioned policy rules
CREATE TABLE IF NOT EXISTS rules (
    rule_key VARCHAR(100) NOT NULL,
    version INT NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    body TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}',
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,  -- NULL = current version
    changed_by VARCHAR(100) NOT NULL,
    PRIMARY KEY (rule_key, version),
    CHECK (version > 0),
    CHECK (valid_from < valid_to OR valid_to IS NULL)
);

CREATE INDEX rules_current_idx ON rules (rule_key, valid_to) WHERE valid_to IS NULL;
CREATE INDEX rules_domain_idx ON rules (domain, valid_from DESC);

-- Playbooks: compiled runbooks
CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(50) NOT NULL DEFAULT 'incident',
    version INT NOT NULL DEFAULT 1,
    supersedes UUID REFERENCES playbooks(playbook_id),
    status_cache VARCHAR(20) NOT NULL DEFAULT 'candidate',
    invalid_reason TEXT,
    spec JSONB NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0.5,
    uses INT NOT NULL DEFAULT 0,
    successes INT NOT NULL DEFAULT 0,
    failures INT NOT NULL DEFAULT 0,
    embedding VECTOR(1024),  -- Titan V2 embeddings (normalized, L2 metric)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status_cache IN ('candidate', 'active', 'suspect', 'invalidated', 'rejected')),
    CHECK (confidence >= 0 AND confidence <= 1),
    CHECK (uses >= 0 AND successes >= 0 AND failures >= 0),
    CHECK (successes + failures <= uses),
    CHECK (version > 0)
);

-- NOTE: the pb_embed_idx VECTOR index is created after COMMIT (see bottom of
-- this file) — it runs a backfill job and cannot be created inside an explicit
-- transaction.

CREATE INDEX playbooks_active_idx ON playbooks (domain, confidence DESC)
    WHERE status_cache = 'active';
CREATE INDEX playbooks_status_idx ON playbooks (status_cache, created_at DESC);
CREATE INDEX playbooks_lineage_idx ON playbooks (supersedes) WHERE supersedes IS NOT NULL;

-- Playbook dependencies: provenance edges (rule -> playbook)
CREATE TABLE IF NOT EXISTS playbook_deps (
    playbook_id UUID NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    rule_key VARCHAR(100) NOT NULL,
    rule_version INT NOT NULL,
    citation TEXT,
    extraction_confidence FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (playbook_id, rule_key, rule_version),
    FOREIGN KEY (rule_key, rule_version) REFERENCES rules(rule_key, version),
    CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1)
);

CREATE INDEX deps_rule_idx ON playbook_deps (rule_key, rule_version);
CREATE INDEX deps_playbook_idx ON playbook_deps (playbook_id);

-- Tasks: working memory
CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    result VARCHAR(20),
    mode VARCHAR(10),
    playbook_id UUID REFERENCES playbooks(playbook_id),
    interrupt_flag BOOLEAN NOT NULL DEFAULT FALSE,
    interrupt_reason TEXT,
    scratchpad JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CHECK (status IN ('queued', 'running', 'interrupted', 'awaiting_approval', 'succeeded', 'failed')),
    CHECK (result IN ('remediated', 'escalated') OR result IS NULL),
    CHECK (mode IN ('explore', 'guided') OR mode IS NULL)
);

CREATE INDEX tasks_running_idx ON tasks (created_at) WHERE status = 'running';
CREATE INDEX tasks_status_idx ON tasks (status, created_at DESC);
CREATE INDEX tasks_playbook_idx ON tasks (playbook_id) WHERE playbook_id IS NOT NULL;

-- Episodes: performance history
CREATE TABLE IF NOT EXISTS episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    outcome VARCHAR(20) NOT NULL,
    mode VARCHAR(10) NOT NULL,
    steps INT NOT NULL,
    latency_ms INT NOT NULL,
    tokens INT NOT NULL,
    s3_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (outcome IN ('success', 'failure', 'interrupted')),
    CHECK (mode IN ('explore', 'guided')),
    CHECK (steps > 0 AND latency_ms >= 0 AND tokens >= 0)
);

CREATE INDEX episodes_task_idx ON episodes (task_id);
CREATE INDEX episodes_mode_idx ON episodes (mode, created_at DESC);
CREATE INDEX episodes_outcome_idx ON episodes (outcome, mode, created_at DESC);

-- Outbox: transactional outbox pattern (D5)
CREATE TABLE IF NOT EXISTS outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMPTZ,
    CHECK (kind IN ('compile', 'rule_changed', 'relearn', 'recheck_suspect', 'postmortem'))
);

CREATE INDEX outbox_unprocessed_idx ON outbox (created_at) 
    WHERE processed_at IS NULL AND claimed_at IS NULL;
CREATE INDEX outbox_kind_idx ON outbox (kind, created_at DESC);

-- Audit log: append-only
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    details JSONB NOT NULL,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_kind_idx ON audit_log (kind, at DESC);
CREATE INDEX audit_actor_idx ON audit_log (actor, at DESC);

-- ============================================================================
-- EXTENSION TABLES (wire up Week 4+)
-- ============================================================================

-- Approvals: autonomy gating
CREATE TABLE IF NOT EXISTS approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    playbook_id UUID REFERENCES playbooks(playbook_id),
    step_index INT NOT NULL,
    action TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),
    CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    CHECK (step_index >= 0)
);

CREATE INDEX approvals_pending_idx ON approvals (requested_at) 
    WHERE status = 'pending';
CREATE INDEX approvals_task_idx ON approvals (task_id);

-- Insights: trend detection
CREATE TABLE IF NOT EXISTS insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    related_rule_key VARCHAR(100),
    suggested_params JSONB,
    evidence JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (kind IN ('threshold_trend', 'failure_pattern', 'coverage_gap'))
);

CREATE INDEX insights_active_idx ON insights (created_at DESC) 
    WHERE NOT dismissed;
CREATE INDEX insights_rule_idx ON insights (related_rule_key) 
    WHERE related_rule_key IS NOT NULL;

-- Postmortems
CREATE TABLE IF NOT EXISTS postmortems (
    postmortem_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID NOT NULL UNIQUE REFERENCES episodes(episode_id),
    s3_key TEXT NOT NULL,
    summary TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX postmortems_episode_idx ON postmortems (episode_id);

-- ============================================================================
-- MOCK WORLD (Demo Environment)
-- ============================================================================

-- Mock services
CREATE TABLE IF NOT EXISTS mock_services (
    service_name VARCHAR(100) PRIMARY KEY,
    tier INT NOT NULL,
    description TEXT,
    CHECK (tier >= 1 AND tier <= 3)
);

-- Mock incidents
CREATE TABLE IF NOT EXISTS mock_incidents (
    incident_id VARCHAR(20) PRIMARY KEY,
    kind VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    service_name VARCHAR(100) NOT NULL REFERENCES mock_services(service_name),
    service_tier INT NOT NULL,
    deploy_timestamp TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL DEFAULT 'open',
    error_rate FLOAT,
    cpu_usage FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (kind IN ('bad_deploy', 'error_spike', 'resource_exhaustion')),
    CHECK (severity IN ('P1', 'P2', 'P3')),
    CHECK (state IN ('open', 'mitigated', 'resolved')),
    CHECK (service_tier >= 1 AND service_tier <= 3)
);

CREATE INDEX mock_incidents_state_idx ON mock_incidents (state, created_at DESC);
CREATE INDEX mock_incidents_service_idx ON mock_incidents (service_name);

-- Mock action log
CREATE TABLE IF NOT EXISTS mock_action_log (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(20) NOT NULL REFERENCES mock_incidents(incident_id),
    action VARCHAR(50) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    details JSONB DEFAULT '{}',
    at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (action IN ('rollback', 'restart', 'scale_up', 'notify')),
    CHECK (outcome IN ('success', 'failed'))
);

CREATE INDEX action_log_incident_idx ON mock_action_log (incident_id, at DESC);

COMMIT;

-- ============================================================================
-- VECTOR INDEX (D2/D3) — must run outside the transaction
-- ============================================================================
-- CockroachDB v25.2+ ships C-SPANN vector indexes. `USING ivfflat (embedding
-- vector_l2_ops)` is pgvector syntax and is rejected by CRDB, which is why the
-- index was silently missing before. CREATE VECTOR INDEX defaults to the L2
-- metric, so the <-> operator in retrieval.py hits it. NEVER use <=> or <#>.
SET CLUSTER SETTING feature.vector_index.enabled = true;

CREATE VECTOR INDEX pb_embed_idx ON playbooks (embedding);
