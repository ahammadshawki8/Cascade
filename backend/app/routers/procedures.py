"""Procedures — bringing your own runbooks under governance.

OWNER: Shawki (Track B).

    POST /api/procedures/parse   read a pasted runbook, propose its citations
    POST /api/procedures         commit it, with the citations a human confirmed

Two calls rather than one, because the linking step is model output and model
output does not get to write provenance unreviewed. The compiler's over-fitted
preconditions were the same class of problem, and they were only caught because
they happened to break reuse loudly. A wrong citation would not break anything
loudly; it would just quietly make a runbook look governed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import OPERATOR, Principal, require
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()

require_operator = require(OPERATOR)


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=40_000)
    name: str | None = None


class ConfirmedCitation(BaseModel):
    rule_key: str
    rule_version: int
    evidence: str | None = None


class ImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    goal: str = Field(default="", max_length=1000)
    steps: list[str] = Field(default_factory=list)
    citations: list[ConfirmedCitation] = Field(default_factory=list)
    source_ref: str | None = None
    origin: str = "imported"


@router.post("/procedures/parse")
async def parse_procedure(body: ParseRequest):
    """Read a runbook and say what it looks like it depends on. Writes nothing.

    The response is built for a confirmation screen: every proposed citation
    carries the sentence it was drawn from, so a reviewer is approving evidence
    rather than trusting a label.
    """
    from app.core.procedures import parse_document, propose_citations

    parsed = parse_document(body.text)
    if body.name:
        parsed.name = body.name

    rules: list[dict] = []
    if not _stub_mode():
        from app.db import q

        rules = list(
            await q(
                """
                SELECT rule_key, version, body, params
                FROM rules WHERE valid_to IS NULL ORDER BY rule_key
                """
            )
        )

    proposals = await propose_citations(body.text, rules)

    return {
        "name": parsed.name,
        "goal": parsed.goal,
        "steps": parsed.manual_steps,
        "citations": [
            {
                "rule_key": p.rule_key,
                "rule_version": p.rule_version,
                "evidence": p.evidence,
                "confidence": p.confidence,
                "rule_body": p.rule_body,
            }
            for p in proposals
        ],
        "available_rules": [
            {"rule_key": r["rule_key"], "version": r["version"], "body": r["body"]}
            for r in rules
        ],
        "note": (
            "Nothing has been saved. Confirm the citations below: they are what "
            "makes this procedure go stale when policy moves, and a procedure "
            "with none can never be found stale at all."
        ),
    }


@router.post("/procedures", status_code=201)
async def import_procedure(
    body: ImportRequest, principal: Principal = Depends(require_operator)
):
    """Commit a procedure with the citations a human confirmed."""
    if _stub_mode():
        return {"procedure_id": "00000000-0000-0000-0000-000000000001", "name": body.name}

    if body.origin not in ("imported", "authored"):
        raise HTTPException(422, "origin must be 'imported' or 'authored'")

    from app import db as db_module
    from app.core.procedures import register

    try:
        result = await register(
            name=body.name,
            goal=body.goal or body.name,
            steps=body.steps,
            citations=[(c.rule_key, c.rule_version) for c in body.citations],
            db=db_module,
            origin=body.origin,
            source_ref=body.source_ref,
            actor=principal.identity,
            evidence={c.rule_key: c.evidence for c in body.citations if c.evidence},
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    # The library and the metric strip both change; tell the UI rather than
    # waiting for its next poll.
    try:
        from app.bus import TOPIC_PLAYBOOK_CHANGED, sse

        await sse.publish(
            TOPIC_PLAYBOOK_CHANGED,
            {"action": "imported", "playbook_id": result["procedure_id"]},
        )
    except Exception as exc:
        log.debug("could not announce import: %s", exc)

    return result
