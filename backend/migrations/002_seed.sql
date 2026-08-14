-- Cascade — Seed Data (Day 0 Contract)
-- Seed rules, mock services, and demo incidents

BEGIN;

-- ============================================================================
-- SEED RULES (v1 baseline)
-- ============================================================================

-- `predicate` is how the rule decides, and `enforcement` is whether its verdict
-- binds. Both were hardcoded in tools.py until migration 006; keeping them here
-- matters because a demo reset replays this file, and a restored world whose
-- rules gate nothing would look identical right up until the agent ignored one.
INSERT INTO rules (rule_key, version, domain, body, params, changed_by, predicate, enforcement) VALUES
(
    'incident.auto_remediate_tier',
    1,
    'incident',
    'Automated remediation is allowed only for services at tier {min_tier} or higher. Tier 1 (production-critical) services require manual approval.',
    '{"min_tier": 2}',
    'system',
    '{
        "require": {"field": "service_tier", "op": "gte", "param": "min_tier"},
        "deny": "service tier {service_tier} is below the automation floor of tier {min_tier} - manual approval required"
    }',
    'enforcing'
),
(
    'incident.rollback_window',
    1,
    'incident',
    'Rollback is allowed only if the deploy happened within the last {hours} hours. Beyond this window, rollback is considered too risky.',
    '{"hours": 24}',
    'system',
    '{
        "when": {"field": "action", "op": "eq", "value": "rollback"},
        "require": {"field": "deploy_age_hours", "op": "lte", "param": "hours"},
        "deny": "deploy was {deploy_age_hours}h ago, outside the {hours}h rollback window",
        "unknown": "no deploy timestamp - rollback window unverifiable"
    }',
    'enforcing'
),
(
    'incident.notify',
    1,
    'incident',
    'On-call must be notified after any automated remediation action is taken.',
    '{}',
    'system',
    -- An obligation, not a precondition: there is nothing here to gate on, and
    -- pretending otherwise would block every action until a notification that
    -- has not happened yet.
    NULL,
    'advisory'
),
(
    'incident.single_action',
    1,
    'incident',
    'Maximum one automated remediation action is allowed per incident. Multiple automated actions require escalation.',
    '{}',
    'system',
    '{
        "require": {"field": "prior_actions", "op": "eq", "value": 0},
        "deny": "incident already has an automated remediation - single-action limit reached"
    }',
    'enforcing'
);

-- ============================================================================
-- MOCK SERVICES
-- ============================================================================

INSERT INTO mock_services (service_name, tier, description) VALUES
('svc-payments', 1, 'Payment processing (tier 1 - critical)'),
('svc-checkout', 2, 'Shopping cart and checkout (tier 2)'),
('svc-search', 2, 'Product search (tier 2)'),
('svc-recommendations', 3, 'Product recommendations (tier 3)'),
('svc-analytics', 3, 'Analytics pipeline (tier 3)'),
('svc-notifications', 3, 'Email and push notifications (tier 3)');

-- ============================================================================
-- MOCK INCIDENTS (12 scenarios covering happy path, tier blocks, window blocks)
-- ============================================================================

-- INC-1001: Bad deploy on tier 2, within window, eligible for rollback
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1001', 'bad_deploy', 'P1', 'svc-checkout', 2, NOW() - INTERVAL '2 hours', 'open');

-- INC-1002: Bad deploy on tier 2, within window (same class as 1001 - for reuse demo)
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1002', 'bad_deploy', 'P2', 'svc-search', 2, NOW() - INTERVAL '3 hours', 'open');

-- INC-1003: Bad deploy on tier 1 (production-critical), BLOCKED by auto_remediate_tier rule
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1003', 'bad_deploy', 'P1', 'svc-payments', 1, NOW() - INTERVAL '1 hour', 'open');

-- INC-1004: Bad deploy on tier 2, but deploy was 30 hours ago, BLOCKED by rollback_window
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1004', 'bad_deploy', 'P2', 'svc-checkout', 2, NOW() - INTERVAL '30 hours', 'open');

-- INC-1005: Error spike on tier 2, eligible for restart
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state, error_rate) VALUES
('INC-1005', 'error_spike', 'P2', 'svc-search', 2, NULL, 'open', 15.3);

-- INC-1006: Error spike on tier 1, BLOCKED
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state, error_rate) VALUES
('INC-1006', 'error_spike', 'P1', 'svc-payments', 1, NULL, 'open', 8.7);

-- INC-1007: Resource exhaustion on tier 3, eligible for scale_up
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state, cpu_usage) VALUES
('INC-1007', 'resource_exhaustion', 'P3', 'svc-recommendations', 3, NULL, 'open', 94.2);

-- INC-1008: Resource exhaustion on tier 2, eligible
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state, cpu_usage) VALUES
('INC-1008', 'resource_exhaustion', 'P2', 'svc-search', 2, NULL, 'open', 89.5);

-- INC-1009: Bad deploy on tier 3, within window, eligible
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1009', 'bad_deploy', 'P3', 'svc-analytics', 3, NOW() - INTERVAL '5 hours', 'open');

-- INC-1010: Bad deploy at the boundary (exactly 24 hours ago)
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1010', 'bad_deploy', 'P2', 'svc-notifications', 3, NOW() - INTERVAL '24 hours', 'open');

-- INC-1011: Error spike on tier 3, eligible
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state, error_rate) VALUES
('INC-1011', 'error_spike', 'P3', 'svc-notifications', 3, NULL, 'open', 22.1);

-- INC-1012: Already resolved incident (for history testing)
INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1012', 'bad_deploy', 'P2', 'svc-checkout', 2, NOW() - INTERVAL '48 hours', 'resolved');

COMMIT;
