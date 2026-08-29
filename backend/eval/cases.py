"""The evaluation cases, and the oracle that says what the right answer is.

OWNER: evaluation harness. Not imported by the running application.

WHAT COUNTS AS GROUND TRUTH
---------------------------
Not an opinion, and not Cascade's answer. A rule in this system carries a
`predicate`, which is data a human wrote in `002_seed.sql`, and the policy
package applies it. So the correct decision for an incident is whatever the
seeded policy says about it, evaluated directly.

That deserves scrutiny, because Cascade also evaluates predicates and could
therefore look correct by construction. Two things keep the comparison honest:

  1. The question under test is not "can this system evaluate a predicate". It
     is "does this system reach the policy-correct decision *after the policy
     has changed underneath it*". Both arms are handed the current policy. The
     difference is whether anything checks that a remembered procedure predates
     it.

  2. The baselines are not starved. They receive the same rules, in prose, in
     their prompt, on every single call. A baseline that reasons from scratch
     each time can get phase two right, and if it does, this harness will
     report that it did.

WHY THE ACTION MAPPING IS EXPLICIT
----------------------------------
A predicate like `rollback_window` only applies when the proposed action *is* a
rollback, so scoring a case requires knowing which action is on the table. The
planner infers that from the incident; the oracle cannot infer it without
becoming a planner itself, so the mapping is written down. It matches the seed
comments exactly ("eligible for rollback", "eligible for restart", "eligible
for scale_up").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.policy import build_incident_facts, evaluate
from app.core.policy.predicates import PredicateError

# The remediation each failure kind calls for. Mirrors `002_seed.sql`.
ACTION_FOR_KIND: dict[str, str] = {
    "bad_deploy": "rollback",
    "error_spike": "restart",
    "resource_exhaustion": "scale_up",
}

# The two decisions any arm can reach. Deliberately coarse: an arm that
# remediates when policy forbids it is wrong in the way that matters, and no
# amount of good prose around the decision changes that.
REMEDIATE = "remediate"
ESCALATE = "escalate"


@dataclass(frozen=True)
class Case:
    """One incident, scored under one policy state."""

    incident_id: str
    kind: str
    action: str
    facts: dict[str, Any]
    expected: str
    reasons: list[str]
    """Why policy refused, empty when it permits. Shown in the report so a
    failure is legible without re-deriving it."""

    @property
    def is_boundary(self) -> bool:
        """INC-1010 sits just past the window edge, by minutes.

        The brief asks for one challenging case. This is it, though not quite in
        the way the seed intends: `002_seed.sql` writes the deploy at exactly 24
        hours ago, and the value drifts the moment it is written, so by the time
        anything reads it the age is 24.2 or 24.3 against a 24 hour window.

        That is a better test than a clean tie would have been. An arm holding
        the rule as a number computes 24.3 > 24 and refuses. An arm that has
        absorbed "roll back within about a day" sees a deploy from yesterday and
        approves. The gap between those two readings is a few minutes wide, and
        it is exactly the gap where a system that only looks like it applies
        policy comes apart.
        """
        return self.incident_id == "INC-1010"


def natural_action(kind: str) -> str | None:
    return ACTION_FOR_KIND.get(kind)


def incident_facts(
    incident: dict[str, Any], action: str, prior_actions: int = 0
) -> dict[str, Any]:
    """Facts for one incident, from either shape it can arrive in.

    `build_incident_facts` derives `deploy_age_hours` by subtracting a
    `deploy_timestamp`, because that is what a database row carries. The
    incident *API* does that subtraction in SQL and returns only the result, so
    the raw timestamp is absent from the response entirely.

    Feeding an API response straight in therefore yields `deploy_age_hours =
    None`, which is UNKNOWN rather than False, so `rollback_window` reports
    "no deploy timestamp - rollback window unverifiable" for every bad deploy
    that plainly has one. That failure is quiet and it is fatal to this
    experiment: every bad deploy escalates under both policies, so tightening
    the window changes no answer and the measured difference is zero for a
    reason that has nothing to do with the system under test.

    So take the derived value when it is already there, and only fall back to
    deriving it.
    """
    facts = build_incident_facts(incident, action=action, prior_actions=prior_actions)
    if facts.get("deploy_age_hours") is None and incident.get("deploy_age_hours") is not None:
        facts["deploy_age_hours"] = float(incident["deploy_age_hours"])
    return facts


def ground_truth(
    incident: dict[str, Any],
    rules: list[dict[str, Any]],
    prior_actions: int = 0,
) -> tuple[str, list[str]]:
    """What current policy requires for this incident.

    Mirrors `check_remediation_eligibility` in `app/core/tools.py`, including
    the two behaviours that are easy to miss and would quietly skew the score:

      - advisory rules are prose and have no verdict, so they are skipped
      - shadow rules are evaluated and recorded but do not bind

    and the invariant that lives outside the rules table entirely: an incident
    that is not open has nothing to remediate whatever policy says. That is what
    INC-1012 exercises.
    """
    action = natural_action(incident.get("kind", ""))
    if action is None:
        return ESCALATE, [f"no remediation defined for kind {incident.get('kind')!r}"]

    facts = incident_facts(incident, action, prior_actions)
    reasons: list[str] = []

    for rule in rules:
        enforcement = rule.get("enforcement") or "advisory"
        if enforcement != "enforcing":
            continue
        try:
            verdict = evaluate(rule.get("predicate"), facts, rule.get("params") or {})
        except PredicateError:
            # A malformed rule decides nothing. Same posture as the tool.
            continue
        if verdict.applies and not verdict.passed:
            reasons.append(verdict.reason or f"{rule.get('rule_key')} refuses this action")

    if incident.get("state") != "open":
        reasons.append(f"incident is {incident.get('state')}, not open")

    return (ESCALATE if reasons else REMEDIATE), reasons


def build_cases(
    incidents: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[Case]:
    """Score every incident against the policy currently in force.

    Called once per phase. Nothing is cached across phases on purpose: the whole
    experiment is that the right answer *moves* when a rule moves, and a case
    list computed once and reused would hide exactly that.
    """
    cases: list[Case] = []
    for inc in sorted(incidents, key=lambda i: i.get("incident_id", "")):
        kind = inc.get("kind", "")
        action = natural_action(kind)
        if action is None:
            continue
        expected, reasons = ground_truth(inc, rules)
        cases.append(
            Case(
                incident_id=inc["incident_id"],
                kind=kind,
                action=action,
                facts=incident_facts(inc, action),
                expected=expected,
                reasons=reasons,
            )
        )
    return cases


def policy_prose(rules: list[dict[str, Any]]) -> str:
    """Every rule in force, written out the way a runbook author would read it.

    This is what the baselines are given. It carries the parameters as well as
    the sentence, because a baseline told only "roll back promptly" would be
    failing on missing information rather than on missing mechanism, and that is
    not the comparison anyone is trying to make.
    """
    lines: list[str] = []
    for rule in sorted(rules, key=lambda r: r.get("rule_key", "")):
        if (rule.get("enforcement") or "advisory") == "advisory":
            continue
        body = str(rule.get("body", "")).strip()
        params = rule.get("params") or {}
        for name, value in params.items():
            body = body.replace("{" + name + "}", str(value))
        lines.append(f"- {rule.get('rule_key')} (v{rule.get('version')}): {body}")
    return "\n".join(lines)
