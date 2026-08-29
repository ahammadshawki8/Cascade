"""Procedures, however they arrive.

A runbook the agent compiled from a successful run and a runbook someone wrote
in Confluence three years ago are the same governed object. Both cite policy at
a version, both go stale the moment that policy moves, and both should be
answerable for what they depend on.

Until now only the first kind could exist, which meant Cascade was useful only
to a team that had already adopted its agent. Importing is the wedge: point it
at the procedures you already have, and the staleness product works on day one
with the agent switched off entirely.
"""

from app.core.procedures.ingest import (
    ParsedProcedure,
    ProposedCitation,
    parse_document,
    propose_citations,
    register,
)

__all__ = [
    "ParsedProcedure",
    "ProposedCitation",
    "parse_document",
    "propose_citations",
    "register",
]
