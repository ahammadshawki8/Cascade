"""
CASCADE Track B - Playbook Compiler
Day 4 COMPLETE: Trajectory → PlaybookSpec → Database

Compiles successful trajectories into reusable playbooks with:
- Pydantic validation
- Dependency extraction
- Safety linting
- Deduplication
- Vector embedding
"""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from .models import PlaybookSpec
from .retrieval import dedup_check


# Whitelisted tools for safety
ALLOWED_TOOLS = {
    "get_incident",
    "get_rules", 
    "check_remediation_eligibility",
    "apply_remediation",
    "notify_oncall"
}


async def compile_playbook(
    episode_id: UUID,
    task_id: UUID,
    trajectory: list[dict],
    db,
    llm_client=None,
    embed_client=None,
    supersedes: Optional[UUID] = None
) -> UUID:
    """
    Compile trajectory into reusable playbook.
    
    Steps:
    1. Ask Claude Sonnet to extract PlaybookSpec JSON
    2. Validate against Pydantic schema
    3. Verify rule dependencies against trajectory
    4. Safety lint
    5. Check for duplicates
    6. Generate embedding
    7. Insert playbooks + playbook_deps + audit in one txn
    
    Args:
        episode_id: Source episode
        task_id: Source task
        trajectory: Execution steps
        db: Database connection
        llm_client: Claude Sonnet for extraction
        embed_client: Titan for embedding
        supersedes: Previous playbook version (for re-learn)
    
    Returns:
        New playbook_id
    
    Raises:
        ValueError: If validation/safety checks fail
    """
    # Extract PlaybookSpec from trajectory
    try:
        spec = await _extract_spec(trajectory, llm_client)
    except Exception as e:
        # Mark outbox as failed
        raise ValueError(f"Spec extraction failed: {e}")
    
    # Validate spec (Pydantic does this automatically)
    if not isinstance(spec, PlaybookSpec):
        raise ValueError("Invalid PlaybookSpec structure")
    
    # Verify dependencies against trajectory
    deps = _extract_dependencies(spec, trajectory)
    if not deps:
        raise ValueError("No rule citations found - playbook must reference rules")
    
    # Safety lint
    violations = _safety_lint(spec)
    if violations:
        raise ValueError(f"Safety violations: {', '.join(violations)}")
    
    # Generate embedding
    embedding_text = f"{spec.name}\n{spec.description}\n" + "\n".join(spec.preconditions)
    
    try:
        if embed_client:
            embedding = await embed_client.embed(embedding_text)
        else:
            from .llm import EmbedClient
            embedding = await EmbedClient().embed(embedding_text)
    except NotImplementedError:
        # Stub mode - no embedding
        embedding = None
    
    # Dedup check (if embedding available)
    if embedding and not supersedes:
        existing_id = await dedup_check(embedding, spec.domain, db)
        if existing_id:
            # Update existing playbook's success counter instead
            await db.q(
                "UPDATE playbooks SET successes = successes + 1, uses = uses + 1 WHERE playbook_id = %s",
                (str(existing_id),)
            )
            return existing_id
    
    # Insert playbook + deps in transaction
    playbook_id = await _insert_playbook_txn(
        spec=spec,
        embedding=embedding,
        deps=deps,
        supersedes=supersedes,
        db=db
    )
    
    # Enqueue compile success event (for SSE notification)
    # Worker will POST /internal/sse to notify frontend
    
    return playbook_id


async def _extract_spec(trajectory: list[dict], llm_client=None) -> PlaybookSpec:
    """
    Use Claude Sonnet to extract structured PlaybookSpec.
    
    For Day 4 stub: Return minimal valid spec.
    Real implementation uses Claude to analyze trajectory.
    
    Args:
        trajectory: Execution steps
        llm_client: Claude Sonnet client
    
    Returns:
        Validated PlaybookSpec
    """
    # STUB for Day 4: Generate minimal valid spec from trajectory
    # Real implementation would call Claude Sonnet with compilation prompt
    
    # Extract incident type from first tool call
    incident_data = None
    for step in trajectory:
        if step.get("tool_name") == "get_incident":
            incident_data = step.get("tool_output", {})
            break
    
    if not incident_data or isinstance(incident_data, dict) and incident_data.get("error"):
        raise ValueError("No valid incident data in trajectory")
    
    kind = incident_data.get("kind", "unknown")
    
    # Build minimal spec
    spec_dict = {
        "name": f"Remediate {kind}",
        "domain": "incident",
        "description": f"Automated remediation for {kind} incidents",
        "preconditions": [
            f"Incident is of kind {kind}",
            "Incident is open",
            "Service tier allows automation"
        ],
        "parameters": [
            {"name": "incident_id", "type": "string", "description": "Incident identifier"}
        ],
        "steps": [
            {
                "tool": "get_incident",
                "args": {"incident_id": "{incident_id}"}
            },
            {
                "tool": "check_remediation_eligibility",
                "args": {"incident_id": "{incident_id}", "action": "restart"}
            },
            {
                "tool": "apply_remediation",
                "args": {"incident_id": "{incident_id}", "action": "restart", "params": {}}
            },
            {
                "tool": "notify_oncall",
                "args": {"incident_id": "{incident_id}", "message": "Remediation complete"}
            }
        ],
        "rule_citations": [
            {
                "rule_key": "incident.auto_remediate_tier",
                "rule_version": 1,
                "used_in_step": 1,
                "why": "Checked tier eligibility"
            },
            {
                "rule_key": "incident.notify",
                "rule_version": 1,
                "used_in_step": 3,
                "why": "Required notification after action"
            }
        ]
    }
    
    # Validate with Pydantic
    spec = PlaybookSpec(**spec_dict)
    return spec


def _extract_dependencies(
    spec: PlaybookSpec,
    trajectory: list[dict]
) -> list[tuple[str, int, str, float]]:
    """
    Extract rule dependencies from citations in spec.
    
    Args:
        spec: Compiled playbook spec
        trajectory: Original trajectory (for version verification)
    
    Returns:
        List of (rule_key, rule_version, citation, confidence)
    """
    deps = []
    
    # Get rules from trajectory
    rules_snapshot = {}
    for step in trajectory:
        if step.get("tool_name") == "get_rules":
            rules_data = step.get("tool_output", {})
            for rule in rules_data.get("rules", []):
                rules_snapshot[rule["rule_key"]] = rule["version"]
    
    # Extract from rule_citations
    for citation in spec.rule_citations:
        rule_key = citation["rule_key"]
        cited_version = citation["rule_version"]
        
        # Verify against trajectory
        if rule_key in rules_snapshot:
            if rules_snapshot[rule_key] != cited_version:
                # Version mismatch - use trajectory version as truth
                cited_version = rules_snapshot[rule_key]
        
        citation_text = citation.get("why", f"step {citation.get('used_in_step', 0)}")
        confidence = 0.9  # High confidence for explicit citations
        
        deps.append((rule_key, cited_version, citation_text, confidence))
    
    return deps


def _safety_lint(spec: PlaybookSpec) -> list[str]:
    """
    Static safety checks on playbook.
    
    Checks:
    - All tools are whitelisted
    - No unbounded loops (step count ≤ 8)
    - apply_remediation preceded by check_remediation_eligibility
    - All parameter placeholders defined
    
    Args:
        spec: Playbook to check
    
    Returns:
        List of safety violations (empty if safe)
    """
    violations = []
    
    # Check step count
    if len(spec.steps) > 8:
        violations.append(f"Too many steps: {len(spec.steps)} > 8")
    
    if len(spec.steps) < 2:
        violations.append(f"Too few steps: {len(spec.steps)} < 2")
    
    # Check tool whitelist
    for i, step in enumerate(spec.steps):
        tool = step.get("tool")
        if tool not in ALLOWED_TOOLS:
            violations.append(f"Step {i}: Disallowed tool '{tool}'")
    
    # Check apply_remediation has preceding check
    has_check = False
    for i, step in enumerate(spec.steps):
        tool = step.get("tool")
        if tool == "check_remediation_eligibility":
            has_check = True
        elif tool == "apply_remediation":
            if not has_check:
                violations.append(f"Step {i}: apply_remediation without check_remediation_eligibility")
    
    # Check parameter references
    param_names = {p["name"] for p in spec.parameters}
    for i, step in enumerate(spec.steps):
        args = step.get("args", {})
        for key, value in args.items():
            if isinstance(value, str) and "{" in value:
                # Extract placeholder
                import re
                placeholders = re.findall(r'\{(\w+)\}', value)
                for ph in placeholders:
                    if ph not in param_names:
                        violations.append(f"Step {i}: Undefined parameter '{ph}'")
    
    return violations


async def _insert_playbook_txn(
    spec: PlaybookSpec,
    embedding: Optional[list[float]],
    deps: list[tuple[str, int, str, float]],
    supersedes: Optional[UUID],
    db
) -> UUID:
    """
    Insert playbook + dependencies in single transaction.
    
    Args:
        spec: Validated playbook spec
        embedding: Vector embedding (or None in stub mode)
        deps: Rule dependencies
        supersedes: Previous version (for lineage)
        db: Database connection
    
    Returns:
        New playbook_id
    """
    playbook_id = uuid4()
    
    # Determine version
    version = 1
    if supersedes:
        # Increment version
        rows = await db.q(
            "SELECT version FROM playbooks WHERE playbook_id = %s",
            (str(supersedes),)
        )
        if rows:
            version = rows[0]["version"] + 1
    
    async def txn(cur):
        # Insert playbook
        await db.q(
            """
            INSERT INTO playbooks (
                playbook_id, name, domain, version, supersedes,
                status_cache, spec, confidence, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(playbook_id),
                spec.name,
                spec.domain,
                version,
                str(supersedes) if supersedes else None,
                "candidate",  # New playbooks start as candidates
                json.dumps(spec.dict()),
                0.30,  # Initial confidence
                embedding  # May be None
            )
        )
        
        # Insert dependencies
        for rule_key, rule_version, citation, confidence in deps:
            await db.q(
                """
                INSERT INTO playbook_deps (
                    playbook_id, rule_key, rule_version,
                    citation, extraction_confidence
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (str(playbook_id), rule_key, rule_version, citation, confidence)
            )
        
        # Insert audit log
        await db.q(
            """
            INSERT INTO audit_log (kind, actor, details)
            VALUES (%s, %s, %s)
            """,
            (
                "playbook.compiled",
                "system",
                json.dumps({
                    "playbook_id": str(playbook_id),
                    "name": spec.name,
                    "version": version,
                    "supersedes": str(supersedes) if supersedes else None
                })
            )
        )
        
        return playbook_id
    
    return await db.run_txn(txn)
