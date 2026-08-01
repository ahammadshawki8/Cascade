"""
CASCADE Track B - Shared Data Models
FROZEN AFTER DAY 0 - Changes require contract PR
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


class ExecutionMode(str, Enum):
    EXPLORE = "explore"
    GUIDED = "guided"


class PlaybookStatus(str, Enum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    SUSPECT = "suspect"
    STALE = "stale"
    ARCHIVED = "archived"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class InsightKind(str, Enum):
    THRESHOLD_TREND = "threshold_trend"
    FAILURE_PATTERN = "failure_pattern"
    COVERAGE_GAP = "coverage_gap"


# ============================================================================
# Core Models
# ============================================================================

class PlaybookCandidate(BaseModel):
    """Result from retrieval phase"""
    playbook_id: UUID
    name: str
    version: int
    confidence: float
    distance: float
    status_cache: str


class StaleRule(BaseModel):
    """A single stale rule dependency"""
    rule_key: str
    expected_version: int
    actual_version: int


class FreshnessResult(BaseModel):
    """Point-of-use freshness check result"""
    is_fresh: bool
    stale_rules: list[StaleRule] = Field(default_factory=list)


class StepEvent(BaseModel):
    """SSE step event payload"""
    task_id: str
    step_index: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Optional[str] = None
    timestamp: datetime


class PlaybookSpec(BaseModel):
    """Compiled playbook specification"""
    name: str
    domain: str
    description: str
    preconditions: list[str]
    parameters: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    rule_citations: list[dict[str, Any]]


class ImpactResult(BaseModel):
    """Result of rule change impact analysis"""
    affected_playbooks: list[UUID]
    affected_count: int
    will_trigger_cascade: bool


class CopilotAnswer(BaseModel):
    """Ops Copilot response"""
    sql: str
    results: list[dict[str, Any]]
    row_count: int


class Insight(BaseModel):
    """Trend detection insight"""
    insight_id: UUID
    kind: InsightKind
    summary: str
    related_rule_key: Optional[str] = None
    suggested_params: Optional[dict[str, Any]] = None
    evidence: dict[str, Any]
    created_at: datetime
    dismissed: bool = False


# ============================================================================
# Configuration
# ============================================================================

class EngineConfig(BaseModel):
    """Engine configuration from environment"""
    aws_region: str = "us-east-1"
    database_url: str
    stub_mode: bool = True
    
    # Bedrock models
    agent_model_id: str = "anthropic.claude-sonnet-5"
    fast_model_id: str = "anthropic.claude-haiku-4-5"
    embed_model_id: str = "amazon.titan-embed-text-v2:0"
    
    # Budgets
    max_steps_per_task: int = 15
    max_wall_clock_seconds: int = 60
    max_tokens_per_task: int = 25000
    max_concurrent_tasks: int = 5
    
    # Retrieval
    retrieval_l2_threshold: float = 0.85
    dedup_l2_threshold: float = 0.40
    
    # Storage
    episodes_bucket: str = "cascade-episodes-local"
    
    class Config:
        env_prefix = ""
