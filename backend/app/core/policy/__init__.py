"""Policy as data.

Until migration 006 a rule was prose in the database and a hand-written
comparison in `tools.py`. That meant a rule you invented would be stored,
versioned, given provenance edges and cascaded correctly, and then enforced by
nothing at all — a policy that decides nothing.

This package is the seam that fixes it: a rule carries a `predicate`, and one
evaluator applies whatever rules exist. The three hardcoded checks became three
seeded rows, and the existing assertion suite passing unchanged is what proves
the generalisation is faithful rather than merely plausible.
"""

from app.core.policy.facts import DOMAIN_FACTS, build_incident_facts
from app.core.policy.predicates import (
    OPS,
    PredicateError,
    Verdict,
    evaluate,
    evaluate_condition,
    validate_condition,
    validate_predicate,
)

__all__ = [
    "DOMAIN_FACTS",
    "OPS",
    "PredicateError",
    "Verdict",
    "build_incident_facts",
    "evaluate",
    "evaluate_condition",
    "validate_condition",
    "validate_predicate",
]
