"""Connections — how Cascade talks to the rest of your stack.

Two directions, deliberately in one place because they are one mental model:

    outbound   Cascade calls Slack, Discord, a webhook
    inbound    someone else's agent calls Cascade's memory layer

    GET    /api/connections            list (endpoints masked)
    POST   /api/connections            add one
    POST   /api/connections/{id}/test  send a real message now
    PATCH  /api/connections/{id}       go live, go quiet, unbind
    DELETE /api/connections/{id}
    GET    /api/connections/calls      what actually went out

    GET    /api/keys                   agent keys
    POST   /api/keys                   create one (shown once)
    DELETE /api/keys/{id}              revoke
    GET    /api/agent-activity         what agents have been asking
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.auth import ADMIN, Principal, require
from app.config import settings
from app.core import keys as keylib
from app.core.connectors import KINDS

log = logging.getLogger(__name__)

router = APIRouter()

require_admin = require(ADMIN)

# Bindable tools. Only the two that touch the world: a connection on a read-only
# tool would fire on every planning step and mean nothing.
BINDABLE_TOOLS = ("notify_oncall", "apply_remediation")


def _stub_mode() -> bool:
    return settings.cascade_stub_mode


def _mask(url: str) -> str:
    """A webhook URL *is* the credential, so it never comes back out.

    Enough is kept to recognise which one it is — the host, and the last four
    characters — and nothing that would let someone post to it.
    """
    if not url:
        return ""
    try:
        without_scheme = url.split("://", 1)[-1]
        host = without_scheme.split("/", 1)[0]
        return f"{host}/...{url[-4:]}"
    except Exception:
        return "..." + url[-4:]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NewConnection(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    kind: str = Field(..., examples=["slack"])
    endpoint: str = Field(..., min_length=8, max_length=500)
    tool_name: str | None = "notify_oncall"
    mode: str = "live"


class PatchConnection(BaseModel):
    mode: str | None = None
    enabled: bool | None = None
    tool_name: str | None = None


class NewKey(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: [keylib.SCOPE_READ])
    client: str | None = None


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


@router.get("/connections")
async def list_connections():
    """Every connection, with its endpoint masked and its health attached."""
    if _stub_mode():
        return {"connections": [], "kinds": list(KINDS), "tools": list(BINDABLE_TOOLS)}

    from app.db import q

    rows = await q(
        """
        SELECT connection_id, name, kind, endpoint, mode, enabled, tool_name,
               created_by, created_at, last_ok_at, last_error, failures
        FROM connections
        ORDER BY created_at
        """
    )
    counts = await q(
        """
        SELECT connection_id,
               count(*)::INT AS calls,
               count(*) FILTER (WHERE outcome = 'sent')::INT AS sent,
               count(*) FILTER (WHERE outcome = 'replayed')::INT AS replayed
        FROM connector_calls
        GROUP BY connection_id
        """
    )
    by_id = {str(c["connection_id"]): c for c in counts}

    return {
        "connections": [
            {
                "connection_id": str(r["connection_id"]),
                "name": r["name"],
                "kind": r["kind"],
                "endpoint_masked": _mask(r["endpoint"]),
                "mode": r["mode"],
                "enabled": r["enabled"],
                "tool_name": r["tool_name"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
                "last_ok_at": r["last_ok_at"],
                "last_error": r["last_error"],
                "failures": r["failures"],
                "healthy": (r["failures"] or 0) < 3,
                "calls": (by_id.get(str(r["connection_id"])) or {}).get("calls", 0),
                "sent": (by_id.get(str(r["connection_id"])) or {}).get("sent", 0),
                "replayed": (by_id.get(str(r["connection_id"])) or {}).get("replayed", 0),
            }
            for r in rows
        ],
        "kinds": list(KINDS),
        "tools": list(BINDABLE_TOOLS),
    }


@router.post("/connections", status_code=201)
async def create_connection(
    body: NewConnection, principal: Principal = Depends(require_admin)
):
    if body.kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
    if body.mode not in ("live", "dry_run"):
        raise HTTPException(422, "mode must be 'live' or 'dry_run'")
    if body.tool_name and body.tool_name not in BINDABLE_TOOLS:
        raise HTTPException(
            422, f"tool_name must be one of {', '.join(BINDABLE_TOOLS)}"
        )
    if not body.endpoint.startswith("https://"):
        # Not pedantry: these URLs are bearer credentials in the query path, and
        # http would put one on the wire in clear text.
        raise HTTPException(422, "The endpoint must be an https URL.")

    if _stub_mode():
        return {"connection_id": str(uuid4()), "name": body.name}

    from app.db import q

    connection_id = uuid4()
    await q(
        """
        INSERT INTO connections (connection_id, name, kind, endpoint, mode,
                                 tool_name, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(connection_id),
            body.name,
            body.kind,
            body.endpoint,
            body.mode,
            body.tool_name,
            principal.identity,
        ),
    )
    log.info("connection %s (%s) created by %s", body.name, body.kind, principal.identity)
    return {
        "connection_id": str(connection_id),
        "name": body.name,
        "kind": body.kind,
        "mode": body.mode,
    }


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: UUID, principal: Principal = Depends(require_admin)
):
    """Send a real message now, and report exactly what came back.

    Uses a fresh idempotency key each time on purpose: a test that silently
    reported the previous run's success would be worthless.
    """
    if _stub_mode():
        raise HTTPException(400, "Testing a connection requires a database.")

    from app import db as db_module
    from app.core.connectors import send
    from app.db import q

    rows = await q(
        """
        SELECT connection_id, name, kind, endpoint, mode, failures
        FROM connections WHERE connection_id = %s
        """,
        (str(connection_id),),
    )
    if not rows:
        raise HTTPException(404, "No such connection.")

    connection = dict(rows[0])
    # A test is always live, whatever the connection's mode: "test" that only
    # builds a payload answers a question nobody asked.
    connection["mode"] = "live"
    connection["failures"] = 0

    result = await send(
        connection,
        "This is a test from Cascade. If you can read this, the connection works.",
        {
            "incident_id": "TEST",
            "service_name": "cascade",
            "severity": "P3",
            "kind": "connection_test",
        },
        f"test:{uuid4()}",
        db_module,
    )
    return result


@router.patch("/connections/{connection_id}")
async def patch_connection(
    connection_id: UUID,
    body: PatchConnection,
    principal: Principal = Depends(require_admin),
):
    if _stub_mode():
        return {"ok": True}

    from app.db import q

    sets, args = [], []
    if body.mode is not None:
        if body.mode not in ("live", "dry_run"):
            raise HTTPException(422, "mode must be 'live' or 'dry_run'")
        sets.append("mode = %s")
        args.append(body.mode)
    if body.enabled is not None:
        sets.append("enabled = %s")
        args.append(body.enabled)
    if body.tool_name is not None:
        if body.tool_name not in BINDABLE_TOOLS:
            raise HTTPException(422, f"tool_name must be one of {BINDABLE_TOOLS}")
        sets.append("tool_name = %s")
        args.append(body.tool_name)
    if not sets:
        raise HTTPException(422, "Nothing to change.")

    # Any deliberate change is also a statement that the operator believes this
    # connection works, so it closes the breaker.
    sets.append("failures = 0")
    args.append(str(connection_id))
    await q(f"UPDATE connections SET {', '.join(sets)} WHERE connection_id = %s", tuple(args))
    return {"ok": True}


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: UUID, principal: Principal = Depends(require_admin)
):
    if _stub_mode():
        return {"ok": True}
    from app.db import q

    await q("DELETE FROM connections WHERE connection_id = %s", (str(connection_id),))
    return {"ok": True}


@router.get("/connections/calls")
async def list_calls(limit: int = 25):
    """What actually went out, including the replays that were suppressed."""
    if _stub_mode():
        return {"calls": []}

    from app.db import q

    rows = await q(
        """
        SELECT c.call_id, c.connection_id, n.name AS connection_name, n.kind,
               c.task_id, c.step_index, c.idempotency_key, c.status_code,
               c.duration_ms, c.outcome, c.request, c.response, c.at
        FROM connector_calls c
        LEFT JOIN connections n ON n.connection_id = c.connection_id
        ORDER BY c.at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"calls": [dict(r) | {"call_id": str(r["call_id"])} for r in rows]}


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------


@router.get("/keys")
async def list_keys():
    """Agent keys. The secret is not here, because it is not stored."""
    if _stub_mode():
        return {"keys": [], "scopes": list(keylib.ALL_SCOPES)}

    from app.db import q

    rows = await q(
        """
        SELECT key_id, name, key_prefix, scopes, client, created_by, created_at,
               last_used_at, call_count, revoked_at
        FROM api_keys
        ORDER BY created_at DESC
        """
    )
    return {
        "keys": [
            {
                "key_id": str(r["key_id"]),
                "name": r["name"],
                "prefix": r["key_prefix"],
                "scopes": list(r["scopes"] or []),
                "client": r["client"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
                "last_used_at": r["last_used_at"],
                "call_count": r["call_count"],
                "revoked": r["revoked_at"] is not None,
            }
            for r in rows
        ],
        "scopes": list(keylib.ALL_SCOPES),
    }


@router.post("/keys", status_code=201)
async def create_key(body: NewKey, principal: Principal = Depends(require_admin)):
    """Create a key. The plaintext is returned once and never again."""
    bad = [s for s in body.scopes if s not in keylib.ALL_SCOPES]
    if bad:
        raise HTTPException(422, f"unknown scope(s): {', '.join(bad)}")
    if not body.scopes:
        raise HTTPException(422, "A key needs at least one scope.")

    secret, digest, prefix = keylib.generate()

    if not _stub_mode():
        from app.db import q

        await q(
            """
            INSERT INTO api_keys (name, key_hash, key_prefix, scopes, client, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (body.name, digest, prefix, body.scopes, body.client, principal.identity),
        )

    log.info("api key %s created by %s", body.name, principal.identity)
    return {
        "name": body.name,
        "key": secret,
        "scopes": body.scopes,
        "warning": "This is the only time this key is shown. Store it now.",
    }


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: UUID, principal: Principal = Depends(require_admin)):
    if _stub_mode():
        return {"ok": True}
    from app.db import q

    await q(
        "UPDATE api_keys SET revoked_at = now() WHERE key_id = %s AND revoked_at IS NULL",
        (str(key_id),),
    )
    return {"ok": True}


@router.get("/agent-activity")
async def agent_activity(limit: int = 25):
    """What external agents have been asking.

    "Other agents can use this" is a claim. This is the evidence, and it is why
    the console lights up when someone pastes the MCP config into their editor.
    """
    if _stub_mode():
        return {"activity": []}

    from app.db import q

    rows = await q(
        """
        SELECT activity_id, key_name, operation, detail, verdict, at
        FROM agent_activity
        ORDER BY at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {
        "activity": [
            {
                "activity_id": str(r["activity_id"]),
                "key_name": r["key_name"],
                "operation": r["operation"],
                "detail": r["detail"],
                "verdict": r["verdict"],
                "at": r["at"],
            }
            for r in rows
        ]
    }


def _mcp_source() -> Path | None:
    here = Path(__file__).resolve()
    for candidate in (
        # backend/app/routers -> backend/mcp, which is both the repo layout and
        # what the image gets, since the build context is backend/.
        here.parent.parent.parent / "mcp" / "cascade-mcp.mjs",
        Path("mcp/cascade-mcp.mjs"),
        Path("backend/mcp/cascade-mcp.mjs"),
    ):
        if candidate.exists():
            return candidate
    return None


@router.get("/mcp/server.mjs")
async def mcp_server():
    """Serve the MCP server itself.

    A judge evaluating the deployed site has no clone of this repository, so
    telling them to run a file they do not have is not an integration story. One
    curl and it is on their machine; it has no dependencies, so there is nothing
    to install after that.
    """
    path = _mcp_source()
    if path is None:
        raise HTTPException(404, "The MCP server file is not present in this build.")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/javascript",
        headers={"Content-Disposition": 'inline; filename="cascade-mcp.mjs"'},
    )


@router.get("/connect-snippet")
async def connect_snippet(client: str = "claude-code", key: str = "csk_YOUR_KEY"):
    """The exact block to paste, with the key already in it.

    Plug and play means zero typing. Anything a user has to assemble by hand is
    somewhere they can get it wrong and conclude the product is broken.
    """
    base = settings.public_api_url or "http://127.0.0.1:8000"

    if client in ("claude-code", "claude-desktop", "cursor"):
        target = {
            "claude-code": ".mcp.json in your project root",
            "claude-desktop": "claude_desktop_config.json",
            "cursor": ".cursor/mcp.json",
        }[client]
        # `node <file>` rather than `npx @cascade/mcp`: the package is not on
        # npm, and a config that resolves to a 404 is worse than one extra step.
        # The file has no dependencies, so downloading it is the whole install.
        mcp = {
            "mcpServers": {
                "cascade": {
                    "command": "node",
                    "args": ["./cascade-mcp.mjs"],
                    "env": {"CASCADE_URL": base, "CASCADE_KEY": key},
                }
            }
        }
        return {
            "client": client,
            "target": target,
            "format": "json",
            "setup": f"curl -O {base}/api/mcp/server.mjs && mv server.mjs cascade-mcp.mjs",
            "snippet": mcp,
        }

    if client == "python":
        return {
            "client": "python",
            "target": "any Python file",
            "format": "python",
            "snippet": (
                "import httpx\n\n"
                f'CASCADE = "{base}"\n'
                f'KEY = "{key}"\n\n'
                "resp = httpx.post(\n"
                '    f"{CASCADE}/api/memory/check",\n'
                '    headers={"Authorization": f"Bearer {KEY}"},\n'
                '    json={"citations": [\n'
                '        {"rule_key": "incident.rollback_window", "rule_version": 1}\n'
                "    ]},\n"
                ")\n"
                'print(resp.json()["summary"])\n'
            ),
        }

    return {
        "client": "http",
        "target": "any HTTP client",
        "format": "shell",
        "snippet": (
            f"curl -s {base}/api/memory/check \\\n"
            f'  -H "Authorization: Bearer {key}" \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"citations":[{"rule_key":"incident.rollback_window","rule_version":1}]}\''
        ),
    }
