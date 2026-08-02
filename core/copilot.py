"""
CASCADE Track B - Ops Copilot
Day 11 COMPLETE: SQL synthesis for analytics queries

Provides read-only SQL generation for exploring CASCADE state.
Uses Claude Haiku for fast SQL synthesis.

Safety:
- Read-only (SELECT/WITH only)
- Single statement validation
- 3s timeout + LIMIT 200 wrapper
- Executed as cascade_readonly role
"""

import asyncio
import json
from typing import Any

from .llm import FastClient
from .models import CopilotAnswer


async def answer_analytics_question(question: str, db) -> CopilotAnswer:
    """
    Answer analytics question via SQL synthesis.
    
    Flow:
    1. Generate SQL with Claude Haiku
    2. Validate: SELECT/WITH only, single statement
    3. Execute with timeout + row limit
    4. Return SQL + results for UI display
    
    Args:
        question: Natural language question
        db: Database connection
    
    Returns:
        CopilotAnswer with sql, results, and metadata
    """
    fast_client = FastClient()
    
    # Schema context for SQL generation
    schema_context = """
CASCADE Database Schema:

## Core Tables

rules (rule_key, version, domain, body, params, valid_from, valid_to, changed_by)
- Policy rules with temporal versioning
- valid_to IS NULL = current version

playbooks (playbook_id, name, domain, version, supersedes, status_cache, spec, 
           confidence, uses, successes, failures, embedding, created_at, updated_at)
- Compiled playbooks with confidence tracking
- status_cache: 'candidate', 'active', 'suspect', 'rejected'

playbook_deps (playbook_id, rule_key, rule_version, citation, extraction_confidence)
- Provenance edges linking playbooks to rules

tasks (task_id, input, status, result, mode, playbook_id, 
       interrupt_flag, interrupt_reason, scratchpad, created_at, finished_at)
- Task execution records
- status: 'queued', 'running', 'succeeded', 'failed', 'awaiting_approval'
- mode: 'explore', 'guided'

episodes (episode_id, task_id, outcome, mode, steps, latency_ms, 
          tokens, s3_key, created_at)
- Performance history

outbox (event_id, kind, payload, created_at, processed_at, claimed_by, claimed_at)
- Transactional outbox for async jobs

audit_log (entry_id, kind, actor, details, at)
- Audit trail

## Extension Tables (Week 4+)

approvals (approval_id, task_id, playbook_id, step_index, action,
           status, reason, requested_at, resolved_at, resolved_by)

insights (insight_id, kind, summary, related_rule_key,
          suggested_params, evidence, created_at, dismissed)

postmortems (postmortem_id, episode_id, s3_key, summary, generated_at)

## Mock World

mock_incidents (incident_id, kind, severity, service_name, service_tier, 
                deploy_timestamp, state, created_at)

mock_action_log (action_id, incident_id, action, outcome, at)
"""
    
    # Prompt for SQL synthesis
    system_prompt = """You are a SQL expert for CockroachDB. Generate safe, read-only SQL queries.

CRITICAL RULES:
1. ONLY generate SELECT or WITH statements
2. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, GRANT, REVOKE
3. Return a single SQL statement (no semicolons except at end)
4. Use proper CockroachDB syntax
5. Always use explicit column names (avoid SELECT *)
6. Include reasonable filters to limit result size
7. Use JOINs carefully with proper conditions
8. For JSON columns (spec, params, details), use -> or ->> operators

Return ONLY the SQL query, no explanation."""
    
    user_prompt = f"""Schema:
{schema_context}

Question: {question}

Generate a SQL query to answer this question. Remember: read-only, single statement, CockroachDB syntax."""
    
    try:
        # Generate SQL
        sql = await fast_client.generate(
            system=system_prompt,
            user=user_prompt,
            max_tokens=1000
        )
        
        # Clean SQL (remove markdown code blocks if present)
        sql = sql.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()
        
        # Validate SQL
        _validate_sql(sql)
        
        # Wrap with LIMIT to prevent huge results
        if "LIMIT" not in sql.upper():
            # Add LIMIT 200 wrapper
            sql = f"SELECT * FROM ({sql}) AS subq LIMIT 200"
        
        # Execute with timeout (3s)
        try:
            rows = await asyncio.wait_for(
                db.q(sql),
                timeout=3.0
            )
            
            # Convert rows to dict list
            results = [dict(row) for row in rows]
            
            return CopilotAnswer(
                sql=sql,
                results=results,
                row_count=len(results),
                execution_time_ms=0,  # TODO: track actual time
                error=None
            )
        
        except asyncio.TimeoutError:
            return CopilotAnswer(
                sql=sql,
                results=[],
                row_count=0,
                execution_time_ms=3000,
                error="Query timeout (3s limit)"
            )
        
        except Exception as e:
            return CopilotAnswer(
                sql=sql,
                results=[],
                row_count=0,
                execution_time_ms=0,
                error=f"Execution error: {str(e)}"
            )
    
    except ValueError as e:
        # Validation error
        return CopilotAnswer(
            sql="",
            results=[],
            row_count=0,
            execution_time_ms=0,
            error=f"SQL validation failed: {str(e)}"
        )
    
    except Exception as e:
        # Generation error
        return CopilotAnswer(
            sql="",
            results=[],
            row_count=0,
            execution_time_ms=0,
            error=f"SQL generation failed: {str(e)}"
        )


def _validate_sql(sql: str) -> None:
    """
    Validate SQL is read-only and safe.
    
    Args:
        sql: SQL to validate
    
    Raises:
        ValueError: If SQL is invalid or unsafe
    """
    sql_upper = sql.upper()
    
    # Must start with SELECT or WITH
    if not (sql_upper.strip().startswith("SELECT") or sql_upper.strip().startswith("WITH")):
        raise ValueError("Query must start with SELECT or WITH")
    
    # Dangerous keywords not allowed
    forbidden = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "GRANT", "REVOKE", "TRUNCATE", "MERGE", "EXEC", "EXECUTE"
    ]
    
    for keyword in forbidden:
        if keyword in sql_upper:
            raise ValueError(f"Forbidden keyword: {keyword}")
    
    # Single statement only (no semicolons except at end)
    semicolon_count = sql.count(";")
    if semicolon_count > 1:
        raise ValueError("Multiple statements not allowed")
    
    if semicolon_count == 1 and not sql.rstrip().endswith(";"):
        raise ValueError("Semicolon must be at end if present")
