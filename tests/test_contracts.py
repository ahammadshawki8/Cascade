"""
Test contracts module (stub mode)
"""

import pytest
from uuid import uuid4

from core.contracts import (
    retrieve,
    check_freshness,
    run_task,
    change_rule,
    answer_analytics_question,
)


@pytest.mark.asyncio
async def test_retrieve_stub():
    """Test retrieve returns stub data"""
    result = await retrieve("Remediate INC-1001")
    assert result is not None
    assert result.name == "Rollback bad deploy"
    assert result.confidence > 0


@pytest.mark.asyncio
async def test_check_freshness_stub():
    """Test freshness check returns fresh in stub mode"""
    result = await check_freshness(uuid4())
    assert result.is_fresh is True
    assert len(result.stale_rules) == 0


@pytest.mark.asyncio
async def test_run_task_stub():
    """Test run_task completes without error"""
    task_id = uuid4()
    await run_task(task_id)
    # Should complete without exception


@pytest.mark.asyncio
async def test_change_rule_stub():
    """Test change_rule returns impact"""
    result = await change_rule(
        "incident.rollback_window",
        "New policy text",
        {"rollback_window_hours": 4},
        "admin@example.com"
    )
    assert result.affected_count > 0


@pytest.mark.asyncio
async def test_copilot_stub():
    """Test copilot returns stub answer"""
    result = await answer_analytics_question("How many tasks succeeded?")
    assert result.sql is not None
    assert len(result.results) > 0
