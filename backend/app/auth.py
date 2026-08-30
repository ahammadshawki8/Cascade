"""Role-based access control (T3.1).

Three roles, ordered by privilege:

    viewer    read everything
    operator  run tasks, approve or reject gated actions
    admin     change policy, re-learn, reset the world

Tokens are mapped to (role, identity) so that `audit_log.actor` records *who*
did something rather than the string "admin" forever. That matters: the whole
point of keeping the audit trail across a demo reset is being able to answer
"who changed this policy", and a shared literal cannot answer it.

This is deliberately token-based rather than OIDC. A hackathon judge should be
able to run the thing without standing up an identity provider, and the
authorisation model — roles, a dependency per endpoint, an attributed actor —
is the part that would survive swapping the front half for real SSO. The
`Principal` seam is where that swap would happen.

Backwards compatible: `x-admin-token` with the configured `admin_token` still
grants admin, which is what every existing client and script sends.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException

from app.config import settings

log = logging.getLogger(__name__)

VIEWER = "viewer"
OPERATOR = "operator"
ADMIN = "admin"

_RANK = {VIEWER: 0, OPERATOR: 1, ADMIN: 2}


@dataclass(frozen=True)
class Principal:
    """Who is making this request, and what they may do."""

    identity: str
    role: str

    def can(self, required: str) -> bool:
        return _RANK.get(self.role, -1) >= _RANK[required]


# Unauthenticated callers are viewers. Every read endpoint is public in the
# demo; nothing that writes accepts this principal.
ANONYMOUS = Principal(identity="anonymous", role=VIEWER)


def _match(token: str, expected: str) -> bool:
    """Constant-time compare — a token check must not leak length or prefix."""
    if not expected:
        return False
    return hmac.compare_digest(token, expected)


def resolve_principal(token: str | None) -> Principal:
    """Map a bearer token to a principal.

    Tokens carry an optional `name:` prefix so several people can share a role
    while staying individually attributable in the audit log:

        x-admin-token: ashfaq:s3cr3t
    """
    if not token:
        return ANONYMOUS

    identity = None
    secret = token
    if ":" in token:
        identity, secret = token.split(":", 1)

    if _match(secret, settings.admin_token):
        return Principal(identity=identity or "admin", role=ADMIN)
    if _match(secret, settings.operator_token):
        return Principal(identity=identity or "operator", role=OPERATOR)
    if _match(secret, settings.viewer_token):
        return Principal(identity=identity or "viewer", role=VIEWER)

    raise HTTPException(403, "invalid token")


def _principal_from_headers(
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Accept either `x-admin-token` (legacy) or `Authorization: Bearer`."""
    token = x_admin_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    return resolve_principal(token)


def require(role: str):
    """FastAPI dependency enforcing a minimum role.

        @router.post("/rules/{key}")
        async def change(principal: Principal = Depends(require(ADMIN))):
            ...
    """

    def dependency(
        x_admin_token: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ) -> Principal:
        principal = _principal_from_headers(x_admin_token, authorization)
        if not principal.can(role):
            raise HTTPException(
                403,
                f"role '{principal.role}' cannot perform this action; "
                f"'{role}' or higher is required",
            )
        return principal

    return dependency


def optional_principal(
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Identify the caller without requiring privilege.

    Used on endpoints that are readable by anyone but still want to attribute
    the action when a token happens to be present.
    """
    try:
        return _principal_from_headers(x_admin_token, authorization)
    except HTTPException:
        return ANONYMOUS
