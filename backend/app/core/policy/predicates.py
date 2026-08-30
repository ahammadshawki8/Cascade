"""The predicate language, and the one evaluator that applies it.

Deliberately tiny. A rule may compare a fact to a literal or to one of its own
parameters, and combine those comparisons with all/any/not. That is the whole
language. If something needs a loop or arithmetic it is a tool, not a rule, and
the closed operator table below is what keeps that line from eroding.

    {
      "when":    {"field": "action", "op": "eq", "value": "rollback"},
      "require": {"field": "deploy_age_hours", "op": "lte", "param": "hours"},
      "deny":    "deploy was {deploy_age_hours}h ago, outside the {hours}h window",
      "unknown": "no deploy timestamp - rollback window unverifiable"
    }

`when` decides whether the rule has anything to say about this situation, and
`require` is what has to hold when it does. Splitting them matters for
provenance: a rule that does not apply was still *consulted*, and the version it
was consulted at is what the compiler turns into a `playbook_deps` edge.

Three-valued throughout. A comparison against a fact that is missing is
UNKNOWN, never False — the difference between "the deploy was too long ago" and
"there is no deploy timestamp, so this cannot be checked" is the difference
between a refusal a user can act on and one that misleads them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Ternary logic. `None` is UNKNOWN.
Tri = bool | None


class PredicateError(ValueError):
    """A predicate is malformed. Raised at authoring time, never at run time."""

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
# A closed table, by design. Adding an operator is one entry plus one truth
# table in the assertion suite; it is not a change to anything that calls this.


def _num(value: Any) -> float | None:
    """Coerce to a number, or None if it is not one.

    Comparisons cross a JSON boundary in both directions: a fact arrives from
    the database as an int or Decimal, a parameter arrives from a rule's JSONB
    as whatever the author typed. `"2"` and `2` have to mean the same thing or
    a rule someone wrote by hand silently stops matching.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _cmp(left: Any, right: Any, want: str) -> Tri:
    """Ordered comparison. Numeric when both sides are numbers, else textual."""
    ln, rn = _num(left), _num(right)
    if ln is not None and rn is not None:
        a, b = ln, rn
    elif isinstance(left, str) and isinstance(right, str):
        a, b = left, right  # type: ignore[assignment]
    else:
        return None

    if want == "lt":
        return a < b
    if want == "lte":
        return a <= b
    if want == "gt":
        return a > b
    return a >= b


def _eq(left: Any, right: Any) -> Tri:
    if left is None or right is None:
        return None
    ln, rn = _num(left), _num(right)
    if ln is not None and rn is not None:
        return ln == rn
    return str(left) == str(right)


def _in(left: Any, right: Any) -> Tri:
    if left is None:
        return None
    if not isinstance(right, list | tuple):
        return None
    return any(_eq(left, item) is True for item in right)


def _contains(left: Any, right: Any) -> Tri:
    if left is None or right is None:
        return None
    if isinstance(left, list | tuple):
        return any(_eq(item, right) is True for item in left)
    return str(right).lower() in str(left).lower()


OPS: dict[str, Any] = {
    "eq": _eq,
    "neq": lambda a, b: None if _eq(a, b) is None else not _eq(a, b),
    "lt": lambda a, b: _cmp(a, b, "lt"),
    "lte": lambda a, b: _cmp(a, b, "lte"),
    "gt": lambda a, b: _cmp(a, b, "gt"),
    "gte": lambda a, b: _cmp(a, b, "gte"),
    "in": _in,
    "nin": lambda a, b: None if _in(a, b) is None else not _in(a, b),
    "contains": _contains,
}

# Operators that take only a field, with no right-hand side.
UNARY_OPS: dict[str, Any] = {
    "exists": lambda a: a is not None,
    "missing": lambda a: a is None,
    "truthy": lambda a: bool(a) if a is not None else None,
}

# Offered to the rule builder in the UI, in the order a person would reach for
# them. Kept beside the table it describes so the two cannot drift.
OP_LABELS: dict[str, str] = {
    "eq": "is",
    "neq": "is not",
    "lt": "is less than",
    "lte": "is at most",
    "gt": "is greater than",
    "gte": "is at least",
    "in": "is one of",
    "nin": "is none of",
    "contains": "contains",
    "exists": "is known",
    "missing": "is not known",
    "truthy": "is true",
}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    """What a rule decided about one situation.

    `applies` is separate from `passed` because a rule that had nothing to say
    still consulted policy, and the version it consulted is what becomes a
    provenance edge.
    """

    applies: bool
    passed: bool
    reason: str | None = None
    unknown_fields: list[str] = field(default_factory=list)


def _resolve(cond: dict, facts: dict, params: dict) -> tuple[Any, Any, str]:
    """Pull the two sides of a comparison out of a condition."""
    name = cond.get("field")
    if not name:
        raise PredicateError("a condition needs a 'field'")
    left = facts.get(name)

    if "param" in cond:
        right = params.get(cond["param"])
    else:
        right = cond.get("value")
    return left, right, name


def _eval_cond(cond: Any, facts: dict, params: dict, missing: list[str]) -> Tri:
    """Evaluate one condition node, collecting the fields it could not read."""
    if not isinstance(cond, dict):
        raise PredicateError(f"expected a condition object, got {type(cond).__name__}")

    # Combinators. `all` is UNKNOWN-tolerant in the usual way: one False makes
    # the whole thing False even if a sibling is unknown, because no value of
    # the unknown could rescue it.
    if "all" in cond:
        results = [_eval_cond(c, facts, params, missing) for c in cond["all"]]
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
    if "any" in cond:
        results = [_eval_cond(c, facts, params, missing) for c in cond["any"]]
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    if "not" in cond:
        inner = _eval_cond(cond["not"], facts, params, missing)
        return None if inner is None else not inner

    op = cond.get("op")
    if op in UNARY_OPS:
        left, _, name = _resolve(cond, facts, params)
        result = UNARY_OPS[op](left)
        if result is None:
            missing.append(name)
        return result

    if op not in OPS:
        raise PredicateError(f"unknown operator {op!r}")

    left, right, name = _resolve(cond, facts, params)
    result = OPS[op](left, right)
    if result is None:
        missing.append(name)
    return result


def _render(template: str, facts: dict, params: dict) -> str:
    """Fill a message template from the facts and parameters it names.

    Floats are shown to one decimal so `30.166666h ago` reads as `30.2h ago`,
    and an unresolvable placeholder is left as written rather than raising: a
    rule that gates correctly must not fail because its explanation has a typo.
    """
    context: dict[str, Any] = {}
    for source in (facts, params):
        for key, value in source.items():
            if isinstance(value, float):
                context[key] = f"{value:.1f}".rstrip("0").rstrip(".")
            else:
                context[key] = value

    out = template
    for key, value in context.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def evaluate(predicate: dict | None, facts: dict, params: dict | None = None) -> Verdict:
    """Apply one rule's predicate to one situation.

    A rule with no predicate never applies — it is prose, cited and versioned
    but gating nothing. That is not a degenerate case, it is the on-ramp:
    staleness detection only ever needed provenance, so a policy set can be
    useful long before anyone writes a predicate for it.
    """
    if not predicate:
        return Verdict(applies=False, passed=True)

    params = params or {}
    missing: list[str] = []

    gate = predicate.get("when")
    if gate is not None:
        # UNKNOWN gate means "cannot tell whether this rule is relevant", which
        # is treated as not relevant. The alternative is refusing every action
        # whose shape we cannot determine, which turns an unrelated missing
        # field into a blanket denial.
        if _eval_cond(gate, facts, params, missing) is not True:
            return Verdict(applies=False, passed=True)

    requirement = predicate.get("require")
    if requirement is None:
        return Verdict(applies=True, passed=True)

    missing = []
    result = _eval_cond(requirement, facts, params, missing)

    if result is True:
        return Verdict(applies=True, passed=True)

    if result is None:
        template = predicate.get("unknown") or (
            "cannot be evaluated: " + ", ".join(sorted(set(missing))) + " unknown"
        )
        return Verdict(
            applies=True,
            passed=False,
            reason=_render(template, facts, params),
            unknown_fields=sorted(set(missing)),
        )

    template = predicate.get("deny") or "policy refuses this action"
    return Verdict(applies=True, passed=False, reason=_render(template, facts, params))


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------


def validate_condition(
    cond: Any,
    known_fields: set[str] | None = None,
    known_params: set[str] | None = None,
) -> None:
    """Check one condition tree on its own.

    A rule's predicate is a `{when, require, deny}` envelope, but a runbook's
    compiled precondition is a bare condition: it has nothing to say about
    when it applies, because a runbook that does not apply is simply not
    retrieved. Both need the same structural check, so it lives here.

    `known_params` matters more than it looks. A compiled predicate that cites
    `auto_remediate_tier.max_tier` when the parameter is actually `min_tier`
    resolves to nothing, compares against nothing, evaluates to UNKNOWN, and is
    then treated as satisfied. It passes every time and checks nothing, which is
    worse than failing: it looks like a working gate. Catching it here is the
    entire reason compiling a predicate is safer than interpreting prose.
    """
    if not isinstance(cond, dict):
        raise PredicateError("expected a condition object")

    for combinator in ("all", "any"):
        if combinator in cond:
            if not isinstance(cond[combinator], list) or not cond[combinator]:
                raise PredicateError(f"'{combinator}' needs a non-empty list")
            for child in cond[combinator]:
                validate_condition(child, known_fields, known_params)
            return
    if "not" in cond:
        validate_condition(cond["not"], known_fields, known_params)
        return

    op = cond.get("op")
    if op not in OPS and op not in UNARY_OPS:
        raise PredicateError(f"unknown operator {op!r}")
    name = cond.get("field")
    if not name:
        raise PredicateError("a condition needs a 'field'")
    if known_fields is not None and name not in known_fields:
        raise PredicateError(
            f"unknown field {name!r}; known fields are " + ", ".join(sorted(known_fields))
        )
    if op in OPS and "value" not in cond and "param" not in cond:
        raise PredicateError(
            f"'{op}' needs a 'value' or a 'param' to compare {name!r} against"
        )
    if known_params is not None and "param" in cond:
        ref = cond["param"]
        if ref not in known_params:
            raise PredicateError(
                f"unknown policy parameter {ref!r}; available parameters are "
                + ", ".join(sorted(known_params))
            )


def evaluate_condition(cond: Any, facts: dict, params: dict | None = None) -> Tri:
    """Evaluate a bare condition tree. UNKNOWN stays UNKNOWN."""
    if cond is None:
        return None
    return _eval_cond(cond, facts, params or {}, [])


def validate_predicate(predicate: Any, known_fields: set[str] | None = None) -> None:
    """Reject a malformed predicate when it is written, not when it fires.

    A rule that throws mid-run is worse than one that refuses: the run is
    already under way and the failure looks like the engine breaking rather than
    the policy being wrong. So authoring is where this is caught.
    """
    if predicate is None:
        return
    if not isinstance(predicate, dict):
        raise PredicateError("a predicate must be an object")

    unknown_keys = set(predicate) - {"when", "require", "deny", "unknown"}
    if unknown_keys:
        raise PredicateError(
            "unexpected key(s): " + ", ".join(sorted(unknown_keys))
        )
    if "require" not in predicate:
        raise PredicateError("a predicate needs a 'require' condition")

    for key in ("when", "require"):
        if predicate.get(key) is not None:
            validate_condition(predicate[key], known_fields)
