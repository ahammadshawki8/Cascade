"""
CASCADE Track B - Ops Copilot
Day 11 implementation target (after MVP gate)

SQL synthesis from natural language for read-only analytics.
"""

from .models import CopilotAnswer


async def answer_analytics_question(question: str) -> CopilotAnswer:
    """
    Synthesize and execute SQL for analytics question.
    
    Steps:
    1. Use Claude Haiku to generate SQL from question
    2. Validate: must start with SELECT/WITH, single statement
    3. Execute as cascade_readonly role with:
       - 3 second timeout
       - LIMIT 200 wrapper
    4. Return SQL + results for display
    
    Args:
        question: Natural language question
    
    Returns:
        CopilotAnswer with SQL and results
    """
    raise NotImplementedError("answer_analytics_question() - Day 11")


def _validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validate generated SQL for safety.
    
    Checks:
    - Starts with SELECT or WITH
    - Single statement (no semicolons except terminator)
    - No write operations
    - No dangerous functions
    
    Args:
        sql: Generated SQL
    
    Returns:
        (is_valid, error_message)
    """
    raise NotImplementedError("_validate_sql() - Day 11")
