-- CASCADE Track B - Initial Seed Data
-- Day 0 - FROZEN after merge

-- Clean slate
TRUNCATE TABLE audit_log CASCADE;
TRUNCATE TABLE outbox CASCADE;
TRUNCATE TABLE episodes CASCADE;
TRUNCATE TABLE tasks CASCADE;
TRUNCATE TABLE playbook_deps CASCADE;
TRUNCATE TABLE playbooks CASCADE;
TRUNCATE TABLE rules CASCADE;
TRUNCATE TABLE approvals CASCADE;
TRUNCATE TABLE insights CASCADE;
TRUNCATE TABLE postmortems CASCADE;
TRUNCATE TABLE mock_action_log CASCADE;
TRUNCATE TABLE mock_incidents CASCADE;

-- =============================================================================
-- Initial Policy Rules (v1)
-- =============================================================================

INSERT INTO rules (rule_key, version, domain, body, params, changed_by) VALUES
('incident.rollback_window', 1, 'incident', 
 'Production rollbacks must occur within N hours of deploy', 
 '{"rollback_window_hours": 24}', 
 'system'),

('incident.approval_tier', 1, 'incident',
 'Determines which actions require manual approval based on service tier',
 '{"production": "requires_approval", "staging": "auto_execute"}',
 'system'),

('incident.notification', 1, 'incident',
 'Notification policy for incident actions',
 '{"severity_p1": true, "severity_p2": true, "severity_p3": false}',
 'system'),

('incident.single_action_limit', 1, 'incident',
 'Maximum number of actions per incident without escalation',
 '{"max_actions": 3}',
 'system');

-- =============================================================================
-- Mock Incidents (For Demo Scenarios)
-- =============================================================================

INSERT INTO mock_incidents (incident_id, kind, severity, service_name, service_tier, deploy_timestamp, state) VALUES
('INC-1001', 'bad_deploy', 'P1', 'api-gateway', 1, NOW() - INTERVAL '2 hours', 'open'),
('INC-1002', 'error_spike', 'P2', 'payment-service', 1, NOW() - INTERVAL '30 minutes', 'open'),
('INC-1003', 'resource_exhaustion', 'P1', 'database-cluster', 1, NOW() - INTERVAL '15 minutes', 'open'),
('INC-1004', 'bad_deploy', 'P2', 'auth-service', 2, NOW() - INTERVAL '1 hour', 'open');

-- =============================================================================
-- Audit Initial Setup
-- =============================================================================

INSERT INTO audit_log (kind, actor, details) VALUES
('system_init', 'system', '{"action": "seed_data", "version": "1.0"}');
