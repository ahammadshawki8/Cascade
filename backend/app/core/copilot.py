"""Ops Copilot — natural language to read-only SQL (spec §8.1, D6).

OWNER: Shawki (Track B).

The honest half of our MCP story: this panel synthesizes SQL, *shows it*, and
labels the result exploratory. It is not a source of truth and the UI says so.

Defence in depth, because an LLM writes the query:
    1. the statement must parse as a single SELECT / WITH
    2. mutating keywords are rejected on word boundaries
    3. execution is wrapped in LIMIT 200 and a 3s timeout
    4. it runs as cascade_readonly, which has no write grants at all

Layer 4 is the one that actually matters — 1-3 are there so a bad query fails
loudly and cheaply instead of reaching the database.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from .models import CopilotAnswer

log = logging.getLogger(__name__)

MAX_ROWS = 200
TIMEOUT_SECONDS = 3.0

# Word-boundary matching matters: a naive substring check rejects
# "SELECT created_at ..." because it contains "CREATE".
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT|REVOKE|TRUNCATE|MERGE|"
    r"UPSERT|EXEC|EXECUTE|COPY|IMPORT|BACKUP|RESTORE|SET|CALL)\b",
    re.IGNORECASE,
)
_STARTS_READONLY = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)

SCHEMA_CONTEXT = """\
rules(rule_key, version, domain, body, params JSONB, valid_from, valid_to, changed_by)
    valid_to IS NULL marks the current version of a rule.
playbooks(playbook_id, name, domain, version, supersedes, status_cache, spec JSONB,
          confidence, uses, successes, failures, embedding, created_at, updated_at)
    status_cache in ('candidate','active','suspect','invalidated','rejected')
playbook_deps(playbook_id, rule_key, rule_version, citation, extraction_confidence)
    provenance edges; a playbook is stale when rule_version != the rule's head version
tasks(task_id, input, status, result, mode, playbook_id, interrupt_flag,
      interrupt_reason, scratchpad, created_at, finished_at)
    status in ('queued','running','interrupted','awaiting_approval','succeeded','failed')
    mode in ('explore','guided')
episodes(episode_id, task_id, outcome, mode, steps, latency_ms, tokens, s3_key, created_at)
    outcome in ('success','failure','interrupted')
outbox(event_id, kind, payload JSONB, created_at, processed_at, claimed_by, claimed_at)
audit_log(entry_id, kind, actor, details JSONB, at)
approvals(approval_id, task_id, playbook_id, step_index, action, status, reason,
          requested_at, resolved_at, resolved_by)
insights(insight_id, kind, summary, related_rule_key, suggested_params, evidence,
         created_at, dismissed)
postmortems(postmortem_id, episode_id, s3_key, summary, generated_at)
mock_incidents(incident_id, kind, severity, service_name, service_tier,
               deploy_timestamp, state, error_rate, cpu_usage, created_at)
mock_action_log(action_id, incident_id, action, outcome, details, at)"""

_SYSTEM_PROMPT = f"""You write read-only CockroachDB SQL for an SRE dashboard.

Schema:
{SCHEMA_CONTEXT}

Rules:
- Emit exactly one SELECT or WITH statement. Nothing else, no prose, no markdown.
- Never emit INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/GRANT/SET.
- Name columns explicitly; avoid SELECT *.
- Use -> and ->> for JSONB columns.
- Keep result sets small; add ORDER BY and LIMIT where sensible."""


class UnsafeSQL(ValueError):
    """The synthesized statement is not a safe read-only query."""


async def answer_analytics_question(question: str, db) -> CopilotAnswer:
    """Synthesize SQL, validate it, run it, and return both SQL and rows."""
    from .llm import FastClient, llm_status

    sql = await FastClient().generate(
        system=_SYSTEM_PROMPT, user=question.strip(), max_tokens=600
    )
    sql = _strip_markdown(sql) if sql else None
    source = "bedrock"

    if not sql:
        sql = _canned_sql(question)
        source = "builtin"
        if not sql:
            return CopilotAnswer(
                question=question,
                refused=True,
                message=(
                    "SQL synthesis is unavailable (Bedrock "
                    f"{llm_status()}) and this question doesn't match a built-in "
                    "query. Try: active runbooks, stale runbooks, recent tasks, "
                    "cold vs guided latency, current rules, or recent rule changes."
                ),
            )

    try:
        _validate_sql(sql)
    except UnsafeSQL as exc:
        log.warning("copilot refused %r: %s", sql[:120], exc)
        return CopilotAnswer(
            question=question,
            sql=sql,
            refused=True,
            message=f"Refused: {exc}",
        )

    wrapped = _apply_limit(sql)
    started = time.perf_counter()
    try:
        rows = await asyncio.wait_for(db.q(wrapped), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        return CopilotAnswer(
            question=question,
            sql=sql,
            refused=True,
            message=f"Query exceeded the {TIMEOUT_SECONDS:.0f}s read timeout.",
        )
    except Exception as exc:
        return CopilotAnswer(
            question=question, sql=sql, refused=True, message=f"Execution failed: {exc}"
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    columns = list(rows[0].keys()) if rows else []
    values = [[_scalar(row[column]) for column in columns] for row in rows]

    log.info("copilot [%s] %d rows in %dms", source, len(values), elapsed_ms)
    return CopilotAnswer(
        question=question,
        sql=sql,
        columns=columns,
        rows=values,
        message=f"{len(values)} row(s) in {elapsed_ms}ms"
        + ("" if source == "bedrock" else " · built-in query (Bedrock unavailable)"),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_sql(sql: str) -> None:
    stripped = _COMMENT.sub(" ", sql).strip().rstrip(";").strip()
    if not stripped:
        raise UnsafeSQL("empty statement")
    if not _STARTS_READONLY.match(stripped):
        raise UnsafeSQL("statement must begin with SELECT or WITH")
    if ";" in stripped:
        raise UnsafeSQL("only a single statement is allowed")

    match = _FORBIDDEN.search(stripped)
    if match:
        raise UnsafeSQL(f"mutating keyword {match.group(0).upper()!r} is not permitted")


def _apply_limit(sql: str) -> str:
    """Cap the result set without disturbing the operator's own LIMIT."""
    stripped = sql.strip().rstrip(";").strip()
    if re.search(r"\bLIMIT\s+\d+\s*$", stripped, re.IGNORECASE):
        return stripped
    return f"SELECT * FROM ({stripped}) AS copilot_result LIMIT {MAX_ROWS}"


def _strip_markdown(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _scalar(value: Any) -> Any:
    """Make a DB value JSON-serializable for the response model."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Built-in queries — keeps the panel useful when Bedrock is unavailable
# ---------------------------------------------------------------------------

_BUILTINS: list[tuple[frozenset[str], str]] = [
    (
        frozenset({"stale", "invalid", "outdated"}),
        """
        SELECT p.name, p.version, d.rule_key, d.rule_version AS compiled_against,
               r.version AS current_version, p.status_cache
        FROM playbook_deps d
        JOIN playbooks p ON p.playbook_id = d.playbook_id
        JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
        WHERE d.rule_version != r.version
        ORDER BY p.name
        """,
    ),
    (
        frozenset({"latency", "faster", "speed", "guided", "cold", "compare"}),
        """
        SELECT mode, count(*)::INT AS runs, avg(latency_ms)::INT AS avg_ms,
               avg(steps)::FLOAT AS avg_steps, avg(tokens)::INT AS avg_tokens
        FROM episodes
        WHERE outcome = 'success'
        GROUP BY mode
        ORDER BY mode
        """,
    ),
    (
        frozenset({"rule", "rules", "policy"}),
        """
        SELECT rule_key, version, domain, body, params, changed_by, valid_from
        FROM rules
        WHERE valid_to IS NULL
        ORDER BY rule_key
        """,
    ),
    (
        frozenset({"task", "tasks", "recent", "incident"}),
        """
        SELECT task_id, input, status, result, mode, created_at, finished_at
        FROM tasks
        ORDER BY created_at DESC
        LIMIT 20
        """,
    ),
    (
        frozenset({"playbook", "playbooks", "runbook", "runbooks", "active"}),
        """
        SELECT name, version, status_cache, confidence, uses, successes, failures
        FROM playbooks
        ORDER BY confidence DESC
        """,
    ),
    (
        frozenset({"audit", "change", "changed", "history"}),
        """
        SELECT kind, actor, details, at
        FROM audit_log
        ORDER BY at DESC
        LIMIT 20
        """,
    ),
]


def _canned_sql(question: str) -> str | None:
    """Best-matching built-in query, or None if nothing matches."""
    words = set(re.findall(r"[a-z]+", question.lower()))
    best, best_score = None, 0
    for keywords, sql in _BUILTINS:
        score = len(words & keywords)
        if score > best_score:
            best, best_score = sql, score
    return " ".join(best.split()) if best else None
