"""Ops Copilot router — natural language → read-only SQL synthesis.

Endpoints:
    POST /api/copilot — Ask a question, get SQL + results
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.contracts import answer_analytics_question
from app.core.models import CopilotAnswer

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class CopilotRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["Why did rollback runbooks fail this week?"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/copilot", response_model=CopilotAnswer)
async def ask_copilot(body: CopilotRequest):
    """Ops Copilot — synthesize read-only SQL from natural language.

    Uses cascade_readonly role (SELECT-only, 3s timeout).
    Shows the generated SQL in the response for transparency.
    Clearly labeled: "Exploratory — verify SQL before acting."
    """
    result = await answer_analytics_question(body.question)
    log.info("copilot query: %s → %d rows", body.question[:40], len(result.rows))
    return result
