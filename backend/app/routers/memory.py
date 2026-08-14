"""Memory API — the part another agent can actually use.

OWNER: Shawki (Track B).

Everything else in this project is Cascade doing the work: its planner, its
tools, its execution loop. That is a closed system, and adopting it means
adopting all of it.

This is the open half. An agent with its own planner, its own tools and its own
memory can ask one question here:

    "I remember a procedure that was written against these rule versions.
     Is it still valid?"

Answering that needs no LLM, no execution and no coupling to how the caller
works. It is the only genuinely novel thing in the project, and it is about a
hundred lines, which is the point.

    POST /api/memory/check        is what I remember still valid
    GET  /api/memory/rules        what policy exists to cite
    GET  /api/memory/procedures   what Cascade already knows
    POST /api/memory/procedures   register a procedure to be governed
    POST /api/memory/runs         hand a whole incident over
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.core import keys

log = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def require_scope(scope: str):
    """Require an API key carrying `scope`.

    Keys, not the shared admin token: the whole reason this surface exists is
    that the caller is someone else's software, and "someone else's software
    holds our admin credential" is not a design.
    """

    async def dependency(
        authorization: str | None = Header(default=None),
        x_cascade_key: str | None = Header(default=None),
    ) -> keys.KeyPrincipal:
        secret = x_cascade_key
        if not secret and authorization and authorization.lower().startswith("bearer "):
            secret = authorization[7:].strip()

        if not secret:
            raise HTTPException(
                401,
                "This endpoint needs a Cascade API key. Create one under "
                "Connections, then send it as 'Authorization: Bearer csk_...'.",
            )

        if _stub_mode():
            return keys.KeyPrincipal(key_id="stub", name="stub", scopes=keys.ALL_SCOPES)

        from app import db as db_module

        principal = await keys.resolve(secret, db_module)
        if principal is None:
            raise HTTPException(403, "That API key is not valid, or has been revoked.")
        if not principal.has(scope):
            raise HTTPException(
                403,
                f"This key does not carry the '{scope}' scope. It has: "
                + (", ".join(principal.scopes) or "none"),
            )
        await keys.record_use(principal, db_module)
        return principal

    return dependency


# Built once at import, like `require_admin` elsewhere. Calling require_scope()
# inline in a signature default would construct a new dependency per request.
needs_read = require_scope(keys.SCOPE_READ)
needs_write = require_scope(keys.SCOPE_WRITE)
needs_run = require_scope(keys.SCOPE_RUN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    rule_key: str
    rule_version: int


class CheckRequest(BaseModel):
    """Either a set of citations, or a procedure Cascade already holds."""

    citations: list[Citation] = Field(default_factory=list)
    procedure_id: str | None = None


class StaleCitation(BaseModel):
    rule_key: str
    pinned_version: int
    head_version: int
    changed_at: Any = None
    changed_by: str | None = None
    what_changed: str | None = None
    rule_now: str | None = None


class CheckResponse(BaseModel):
    valid: bool
    checked: int
    stale: list[StaleCitation] = Field(default_factory=list)
    unknown_rules: list[str] = Field(default_factory=list)
    summary: str


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    goal: str = Field(..., min_length=1)
    steps: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    source_ref: str | None = None


# ---------------------------------------------------------------------------
# The primitive
# ---------------------------------------------------------------------------


def _describe_change(old: dict | None, new: dict | None) -> str | None:
    """Say what actually moved between two versions of a rule.

    "the rule changed" tells a calling agent nothing it can act on. "hours:
    24 -> 4" tells it whether the change even matters for what it was about to
    do, which is the difference between a warning and a decision.
    """
    old = old or {}
    new = new or {}
    parts = []
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if before != after:
            parts.append(f"{key}: {before if before is not None else 'unset'} -> "
                         f"{after if after is not None else 'unset'}")
    if parts:
        return ", ".join(parts)
    return "wording changed" if old == new else None


@router.post("/check", response_model=CheckResponse)
async def check_memory(
    body: CheckRequest,
    principal: keys.KeyPrincipal = Depends(needs_read),
):
    """Is a remembered procedure still valid under current policy?

    This is the whole product in one call. The caller supplies the rule versions
    its procedure was written against; the answer is derived from the same join
    the engine's own freshness gate uses, so an external agent and Cascade
    itself can never disagree about whether something is stale.
    """
    if _stub_mode():
        return CheckResponse(
            valid=True, checked=len(body.citations),
            summary="Stub mode: nothing to compare against.",
        )

    from app import db as db_module
    from app.db import q

    citations = [(c.rule_key, c.rule_version) for c in body.citations]

    # A procedure Cascade already holds carries its own provenance, so the
    # caller does not have to know its citations to ask about it.
    if body.procedure_id and not citations:
        rows = await q(
            "SELECT rule_key, rule_version FROM playbook_deps WHERE playbook_id = %s",
            (body.procedure_id,),
        )
        if not rows:
            raise HTTPException(
                404,
                f"No procedure {body.procedure_id!r}, or it has no recorded provenance.",
            )
        citations = [(r["rule_key"], r["rule_version"]) for r in rows]

    if not citations:
        raise HTTPException(
            422, "Send either 'citations' or a 'procedure_id' that has provenance."
        )

    heads = await q(
        """
        SELECT rule_key, version, body, params, valid_from, changed_by
        FROM rules
        WHERE valid_to IS NULL AND rule_key = ANY(%s)
        """,
        ([key for key, _ in citations],),
    )
    head_by_key = {r["rule_key"]: r for r in heads}

    stale: list[StaleCitation] = []
    unknown: list[str] = []

    for rule_key, pinned in citations:
        head = head_by_key.get(rule_key)
        if head is None:
            # A rule that no longer exists is not fresh. Reporting it as valid
            # because there is nothing to compare against would be the worst
            # possible failure mode for a safety check.
            unknown.append(rule_key)
            continue
        if head["version"] == pinned:
            continue

        pinned_rows = await q(
            "SELECT params FROM rules WHERE rule_key = %s AND version = %s",
            (rule_key, pinned),
        )
        # The pinned version can be genuinely absent — a demo reset rolls policy
        # back, and a caller may still be holding a citation to a version that
        # no longer exists. Saying "hours: unset -> 24" there invents a change
        # that never happened; the honest answer is that the old side is gone.
        what_changed = (
            _describe_change(pinned_rows[0]["params"], head.get("params"))
            if pinned_rows
            else f"v{pinned} no longer exists; head is v{head['version']}"
        )
        stale.append(
            StaleCitation(
                rule_key=rule_key,
                pinned_version=pinned,
                head_version=head["version"],
                changed_at=head.get("valid_from"),
                changed_by=head.get("changed_by"),
                what_changed=what_changed,
                rule_now=head.get("body"),
            )
        )

    valid = not stale and not unknown
    if valid:
        summary = (
            f"Still valid. All {len(citations)} cited rule(s) are at the version "
            "this procedure was written against."
        )
    elif stale:
        first = stale[0]
        summary = (
            f"Not valid. {first.rule_key} moved from v{first.pinned_version} to "
            f"v{first.head_version}"
            + (f" ({first.what_changed})" if first.what_changed else "")
            + (
                f", and {len(stale) - 1} other rule(s) also changed"
                if len(stale) > 1
                else ""
            )
            + ". Re-derive the procedure before acting on it."
        )
    else:
        summary = (
            "Not valid. These cited rules no longer exist: " + ", ".join(unknown)
        )

    await keys.log_activity(
        principal,
        "check",
        {
            "citations": [{"rule_key": k, "rule_version": v} for k, v in citations],
            "stale": [s.rule_key for s in stale],
        },
        "valid" if valid else "stale",
        db_module,
    )

    return CheckResponse(
        valid=valid,
        checked=len(citations),
        stale=stale,
        unknown_rules=unknown,
        summary=summary,
    )


@router.get("/rules")
async def list_policy(
    domain: str = "incident",
    principal: keys.KeyPrincipal = Depends(needs_read),
):
    """The policy an agent may cite, with the versions to pin against."""
    if _stub_mode():
        return {"domain": domain, "rules": []}

    from app.db import q

    rows = await q(
        """
        SELECT rule_key, version, body, params, enforcement
        FROM rules
        WHERE domain = %s AND valid_to IS NULL
        ORDER BY rule_key
        """,
        (domain,),
    )
    return {
        "domain": domain,
        "rules": [
            {
                "rule_key": r["rule_key"],
                "version": r["version"],
                "body": r["body"],
                "params": r["params"],
                "enforcement": r.get("enforcement") or "advisory",
                "cite_as": {"rule_key": r["rule_key"], "rule_version": r["version"]},
            }
            for r in rows
        ],
    }


@router.get("/procedures")
async def find_procedures(
    q_: str | None = None,
    limit: int = 10,
    principal: keys.KeyPrincipal = Depends(needs_read),
):
    """What Cascade already knows, with freshness attached."""
    if _stub_mode():
        return {"procedures": []}

    from app.db import q

    if q_:
        # Deliberately not `contracts.retrieve`. That answers a different
        # question — "is there one playbook good enough for the executor to
        # replay" — so it returns a single candidate above a threshold, and it
        # drops procedures with no executable steps. Every imported runbook has
        # none, which would make them permanently unfindable through the very
        # API that exists to govern them.
        #
        # Same two-phase shape though: a pure ANN pass with no predicate at all
        # (D3 — one scalar predicate here costs the vector index), then a PK
        # read over the ids it returned.
        from app.core.llm import EmbedClient
        from app.core.retrieval import normalize_for_embedding, to_vector_literal

        embedding = await EmbedClient().embed(normalize_for_embedding(q_, None))
        literal = to_vector_literal(embedding)
        nearest = await q(
            """
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            (literal, literal, max(limit, 10)),
        )
        ids = [
            str(r["playbook_id"]) for r in nearest if r.get("dist") is not None
        ][:limit]
        if not ids:
            return {"procedures": [], "query": q_}
        rows = await q(
            """
            SELECT playbook_id, name, version, status_cache, confidence, spec, origin
            FROM playbooks WHERE playbook_id = ANY(%s)
            """,
            (ids,),
        )
        # Preserve nearest-first ordering; ANY() does not.
        order = {pid: n for n, pid in enumerate(ids)}
        rows = sorted(rows, key=lambda r: order.get(str(r["playbook_id"]), 999))
    else:
        rows = await q(
            """
            SELECT playbook_id, name, version, status_cache, confidence, spec, origin
            FROM playbooks
            ORDER BY confidence DESC
            LIMIT %s
            """,
            (limit,),
        )

    out = []
    for row in rows:
        deps = await q(
            """
            SELECT d.rule_key, d.rule_version, r.version AS head_version
            FROM playbook_deps d
            LEFT JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
            WHERE d.playbook_id = %s
            """,
            (str(row["playbook_id"]),),
        )
        stale = [
            d["rule_key"]
            for d in deps
            if d["head_version"] is not None and d["rule_version"] != d["head_version"]
        ]
        out.append(
            {
                "procedure_id": str(row["playbook_id"]),
                "name": row["name"],
                "version": row["version"],
                "status": row["status_cache"],
                "confidence": float(row["confidence"]),
                "origin": row.get("origin"),
                "goal": (row["spec"] or {}).get("goal"),
                "steps": [
                    s.get("tool") or s.get("description")
                    for s in (row["spec"] or {}).get("steps", [])
                ],
                "citations": [
                    {"rule_key": d["rule_key"], "rule_version": d["rule_version"]}
                    for d in deps
                ],
                "valid": not stale,
                "stale_rules": stale,
            }
        )
    return {"procedures": out, "query": q_}


@router.post("/procedures", status_code=201)
async def register_procedure(
    body: RegisterRequest,
    principal: keys.KeyPrincipal = Depends(needs_write),
):
    """Hand Cascade a procedure to govern.

    The caller keeps executing it however it likes; what it gains is that the
    citations are now watched, so the next `/check` can tell it the thing it
    remembers has expired.
    """
    if _stub_mode():
        return {"procedure_id": "00000000-0000-0000-0000-000000000001"}

    from app import db as db_module
    from app.core.procedures import register

    result = await register(
        name=body.name,
        goal=body.goal,
        steps=body.steps,
        citations=[(c.rule_key, c.rule_version) for c in body.citations],
        origin="imported",
        source_ref=body.source_ref or f"agent:{principal.name}",
        actor=f"key:{principal.name}",
        db=db_module,
    )
    await keys.log_activity(
        principal, "register", {"name": body.name}, "ok", db_module
    )
    return result


@router.post("/runs", status_code=201)
async def start_run(
    body: dict,
    principal: keys.KeyPrincipal = Depends(needs_run),
):
    """Hand a whole incident over and let Cascade solve it.

    The heavyweight mode, and the one that couples the caller to Cascade's
    tools. Offered because it is the obvious thing to reach for, but `/check`
    is the one that works regardless of what the caller's stack looks like.
    """
    text = (body or {}).get("input") or ""
    if not text.strip():
        raise HTTPException(422, "Send {\"input\": \"Remediate INC-1001\"}.")

    from app import db as db_module
    from app.routers.tasks import CreateTaskRequest, create_task

    result = await create_task(CreateTaskRequest(input=text))
    await keys.log_activity(
        principal, "run", {"input": text, "task_id": str(result.task_id)},
        "ok", db_module,
    )
    return {
        "task_id": str(result.task_id),
        "status": result.status,
        "watch": f"/api/tasks/{result.task_id}/explain",
    }
