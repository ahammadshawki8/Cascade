"""Shared types — the vocabulary both tracks speak.

OWNER: Shawki (Track B). FROZEN AFTER DAY 0.
Changing any shape here requires a contract PR (WORKFLOW.md §4).

Track A imports these for response models; Track B implements against them.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations (mirror the CHECK constraints in migrations/001_schema.sql)
# ---------------------------------------------------------------------------

ToolName = Literal[
    "get_incident",
    "get_rules",
    "check_remediation_eligibility",
    "apply_remediation",
    "notify_oncall",
]

PlaybookStatus = Literal["candidate", "active", "suspect", "invalidated", "rejected"]
TaskStatus = Literal[
    "queued", "running", "interrupted", "awaiting_approval", "succeeded", "failed"
]
TaskResult = Literal["remediated", "escalated"]
ExecutionMode = Literal["explore", "guided"]
EpisodeOutcome = Literal["success", "failure", "interrupted"]
RemediationAction = Literal["restart", "rollback", "scale_up"]


# ============================================================================
# Additional Enums (from Track B for extension features)
# ============================================================================

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class InsightKind(str, Enum):
    THRESHOLD_TREND = "threshold_trend"
    FAILURE_PATTERN = "failure_pattern"
    COVERAGE_GAP = "coverage_gap"


# ============================================================================
# Risk Configuration
# ============================================================================

# Risk map for autonomy gating (decision D-2). Static, so the LLM cannot
# influence it. Lives here so both confidence.py and the UI can read it.
TOOL_RISK: dict[str, Literal["none", "low", "high"]] = {
    "get_incident": "none",
    "get_rules": "none",
    "check_remediation_eligibility": "none",
    "notify_oncall": "low",
    "apply_remediation": "high",
}

# ---------------------------------------------------------------------------
# PlaybookSpec — the compiler's output contract (spec §6.1)
# ---------------------------------------------------------------------------


class Step(BaseModel):
    """One tool call in a compiled playbook.

    `args` values may contain "{param}" placeholders declared in
    PlaybookSpec.params. `idempotency_key` must NEVER appear here — the
    executor injects deterministic keys (spec §5.3).
    """

    tool: ToolName
    args: dict[str, str] = Field(default_factory=dict)


class RuleCitation(BaseModel):
    """Provenance edge: this rule influenced this step."""

    rule_key: str
    rule_version: int
    used_in_step: int
    why: str


class PlaybookSpec(BaseModel):
    """Strict schema. Compiler output is rejected unless this parses."""

    goal: str
    preconditions: list[str] = Field(min_length=1, max_length=6)
    params: dict[str, Literal["string", "int"]] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=2, max_length=8)
    rule_citations: list[RuleCitation] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class Rule(BaseModel):
    rule_key: str
    version: int
    domain: str
    body: str
    params: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    changed_by: str = "system"


# ---------------------------------------------------------------------------
# Playbooks & provenance
# ---------------------------------------------------------------------------


class PlaybookDep(BaseModel):
    rule_key: str
    rule_version: int
    citation: str | None = None
    extraction_confidence: float = 0.5
    # Populated by the API for the UI's fresh/stale provenance dot.
    is_stale: bool | None = None
    head_version: int | None = None


class Playbook(BaseModel):
    playbook_id: UUID
    name: str
    domain: str
    version: int = 1
    supersedes: UUID | None = None
    status_cache: PlaybookStatus = "candidate"
    invalid_reason: str | None = None
    spec: PlaybookSpec
    confidence: float = 0.30
    uses: int = 0
    successes: int = 0
    failures: int = 0
    deps: list[PlaybookDep] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaybookCandidate(BaseModel):
    """Retrieval result (spec §5.5). `distance` is L2 — never cosine (D3)."""

    playbook_id: UUID
    name: str
    version: int
    confidence: float
    distance: float
    status_cache: PlaybookStatus
    spec: PlaybookSpec | None = None


# ---------------------------------------------------------------------------
# Freshness — point-of-use authority (spec §5.6, D1)
# ---------------------------------------------------------------------------


class StaleDep(BaseModel):
    rule_key: str
    depends_on: int   # the version the playbook was compiled against
    head: int         # the current head version


# Alias for Track B compatibility
class StaleRule(BaseModel):
    """A single stale rule dependency (Track B format)"""
    rule_key: str
    expected_version: int
    actual_version: int


class Fresh(BaseModel):
    """Empty freshness join result — safe to execute."""

    kind: Literal["fresh"] = "fresh"


class Stale(BaseModel):
    """At least one dep points at a non-head rule version. NEVER execute.

    Deliberately carries stale_deps (not a bare bool) so the UI can explain
    *why* and the worker can enqueue recheck_suspect.
    """

    kind: Literal["stale"] = "stale"
    stale_deps: list[StaleDep]


FreshnessResult = Fresh | Stale


# ---------------------------------------------------------------------------
# Tasks & episodes
# ---------------------------------------------------------------------------


class TrajectoryStep(BaseModel):
    index: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    at: datetime | None = None


class Task(BaseModel):
    task_id: UUID
    input: str
    status: TaskStatus = "queued"
    result: TaskResult | None = None
    mode: ExecutionMode | None = None
    playbook_id: UUID | None = None
    interrupt_flag: bool = False
    interrupt_reason: str | None = None
    scratchpad: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("scratchpad", mode="before")
    @classmethod
    def _null_scratchpad_is_empty(cls, value: Any) -> Any:
        # tasks.scratchpad is a nullable JSONB column; a task that was never
        # interrupted has no state to carry, which is {} rather than None.
        return {} if value is None else value


class Episode(BaseModel):
    episode_id: UUID
    task_id: UUID
    outcome: EpisodeOutcome
    mode: ExecutionMode
    steps: int
    latency_ms: int   # EXCLUDES compile time (metrics contract, WORKFLOW.md I2)
    tokens: int
    s3_key: str | None = None
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Cascade / impact
# ---------------------------------------------------------------------------


class ImpactedPlaybook(BaseModel):
    playbook_id: UUID
    name: str
    version: int
    confidence: float
    status_cache: PlaybookStatus


class ImpactedTask(BaseModel):
    task_id: UUID
    input: str
    elapsed_ms: int


class ImpactResult(BaseModel):
    """Returned by both change_rule() (after commit) and
    simulate_rule_change() (dry-run, no writes)."""

    rule_key: str
    old_version: int | None = None
    new_version: int | None = None
    impacted_playbooks: list[ImpactedPlaybook] = Field(default_factory=list)
    impacted_tasks: list[ImpactedTask] = Field(default_factory=list)
    committed: bool = False


# ---------------------------------------------------------------------------
# Ops Copilot (spec §8.1)
# ---------------------------------------------------------------------------


class CopilotAnswer(BaseModel):
    question: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    refused: bool = False
    message: str | None = None
    disclaimer: str = (
        "Exploratory — generated SQL shown above; verify before acting."
    )


# ---------------------------------------------------------------------------
# Metrics (the demo money-shot, spec §8)
# ---------------------------------------------------------------------------


class ModeMetrics(BaseModel):
    avg_ms: float | None = None
    avg_tokens: float | None = None
    avg_steps: float | None = None
    runs: int = 0


class RetrievalMetrics(BaseModel):
    hits: int = 0
    precondition_misses: int = 0
    stale_blocks: int = 0


class Metrics(BaseModel):
    cold: ModeMetrics = Field(default_factory=ModeMetrics)
    guided: ModeMetrics = Field(default_factory=ModeMetrics)
    retrieval: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    llm: Literal["ok", "degraded"] = "ok"
    # "degraded" only means "not Bedrock". It covers both a real fallback
    # provider and the local planner, and those are very different situations
    # for anyone reading the latency numbers, so name the provider rather than
    # letting the UI guess from the status alone.
    llm_provider: str | None = None
    llm_reason: str | None = None


# ---------------------------------------------------------------------------
# Extensions (staged; tables exist from Day 0)
# ---------------------------------------------------------------------------


class Approval(BaseModel):
    approval_id: UUID
    task_id: UUID
    playbook_id: UUID | None = None
    step_index: int
    action: str
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    reason: str | None = None
    requested_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class Insight(BaseModel):
    insight_id: UUID
    kind: str
    summary: str
    related_rule_key: str | None = None
    suggested_params: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    dismissed: bool = False


class Postmortem(BaseModel):
    postmortem_id: UUID
    episode_id: UUID
    s3_key: str
    summary: str
    generated_at: datetime | None = None
