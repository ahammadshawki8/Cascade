"""
CASCADE Track B - Mock World Tools
Day 1 implementation target

5 tools for SRE incident response:
1. get_incident - Fetch incident details
2. get_rules - Get current policy rules
3. check_remediation_eligibility - Verify action is allowed
4. apply_remediation - Execute remediation action
5. notify_oncall - Send notification
"""

from typing import Any


async def get_incident(incident_id: str) -> dict[str, Any]:
    """
    Fetch incident details from mock_incidents table.
    
    Args:
        incident_id: Incident identifier (e.g., "INC-1001")
    
    Returns:
        dict with: incident_id, kind, severity, service_name, service_tier,
                   deploy_timestamp, state
    """
    raise NotImplementedError("get_incident() - Day 1")


async def get_rules(domain: str = "incident") -> dict[str, Any]:
    """
    Get current policy rules for domain.
    
    Args:
        domain: Rule domain (default: "incident")
    
    Returns:
        dict with current rule values
    """
    raise NotImplementedError("get_rules() - Day 1")


async def check_remediation_eligibility(
    incident_id: str,
    action: str
) -> dict[str, Any]:
    """
    Check if remediation action is allowed per policy.
    
    Args:
        incident_id: Incident to check
        action: Proposed action (rollback, restart, scale_up)
    
    Returns:
        dict with: eligible (bool), reason (str)
    """
    raise NotImplementedError("check_remediation_eligibility() - Day 1")


async def apply_remediation(
    incident_id: str,
    action: str,
    params: dict[str, Any]
) -> dict[str, Any]:
    """
    Execute remediation action (writes to mock_action_log).
    
    Args:
        incident_id: Incident to remediate
        action: Action to take (rollback, restart, scale_up)
        params: Action parameters
    
    Returns:
        dict with: success (bool), action_id (str), outcome (str)
    """
    raise NotImplementedError("apply_remediation() - Day 1")


async def notify_oncall(
    incident_id: str,
    message: str,
    severity: str = "info"
) -> dict[str, Any]:
    """
    Send notification to on-call engineer.
    
    Args:
        incident_id: Related incident
        message: Notification text
        severity: info | warning | critical
    
    Returns:
        dict with: sent (bool), notification_id (str)
    """
    raise NotImplementedError("notify_oncall() - Day 1")


# Tool definitions for Claude
TOOL_DEFINITIONS = [
    {
        "name": "get_incident",
        "description": "Fetch incident details including severity, service info, and current state",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Incident identifier like INC-1001"
                }
            },
            "required": ["incident_id"]
        }
    },
    {
        "name": "get_rules",
        "description": "Get current policy rules governing incident response",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Rule domain, default is 'incident'"
                }
            }
        }
    },
    {
        "name": "check_remediation_eligibility",
        "description": "Check if a remediation action is allowed per current policy",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["rollback", "restart", "scale_up"],
                    "description": "Remediation action to check"
                }
            },
            "required": ["incident_id", "action"]
        }
    },
    {
        "name": "apply_remediation",
        "description": "Execute a remediation action (rollback, restart, scale_up)",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["rollback", "restart", "scale_up"]
                },
                "params": {
                    "type": "object",
                    "description": "Action-specific parameters"
                }
            },
            "required": ["incident_id", "action", "params"]
        }
    },
    {
        "name": "notify_oncall",
        "description": "Send notification to on-call engineer",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "message": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"]
                }
            },
            "required": ["incident_id", "message"]
        }
    }
]
