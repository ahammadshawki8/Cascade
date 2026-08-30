"""API keys — an external agent calling as itself.

The shared tokens in `auth.py` were the right call for a demo a judge has to be
able to run without standing up an identity provider, but they cannot answer
"which agent asked this" and they cannot be revoked one at a time. Once other
people's agents call the memory layer, both of those stop being acceptable.

A key is shown exactly once, at creation. Only its SHA-256 lives in the
database, so a dump of `api_keys` grants nobody anything.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass

log = logging.getLogger(__name__)

PREFIX = "csk_"

# Scopes, narrowest first. Deliberately three: an agent that only wants to know
# whether its memory is still valid should not be holding a credential that can
# start remediations.
SCOPE_READ = "memory:read"
SCOPE_WRITE = "memory:write"
SCOPE_RUN = "runs:write"
ALL_SCOPES = (SCOPE_READ, SCOPE_WRITE, SCOPE_RUN)


@dataclass(frozen=True)
class KeyPrincipal:
    """An authenticated API key."""

    key_id: str
    name: str
    scopes: tuple[str, ...]

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def generate() -> tuple[str, str, str]:
    """Return (plaintext, sha256_hex, display_prefix)."""
    secret = PREFIX + secrets.token_urlsafe(32)
    return secret, hashlib.sha256(secret.encode()).hexdigest(), secret[:12]


def fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


async def resolve(secret: str, db) -> KeyPrincipal | None:
    """Look up a presented key. Returns None for unknown or revoked keys.

    Compares by hash rather than scanning, so the lookup is an index probe and
    cannot be turned into a timing oracle by an attacker feeding prefixes.
    """
    if not secret or not secret.startswith(PREFIX):
        return None

    rows = await db.q(
        """
        SELECT key_id, name, scopes
        FROM api_keys
        WHERE key_hash = %s AND revoked_at IS NULL
        """,
        (fingerprint(secret),),
    )
    if not rows:
        return None

    row = rows[0]
    return KeyPrincipal(
        key_id=str(row["key_id"]),
        name=row["name"],
        scopes=tuple(row["scopes"] or ()),
    )


async def record_use(principal: KeyPrincipal, db) -> None:
    """Stamp last-used. Best effort: never fail a request over telemetry."""
    try:
        await db.q(
            """
            UPDATE api_keys
            SET last_used_at = now(), call_count = call_count + 1
            WHERE key_id = %s
            """,
            (principal.key_id,),
        )
    except Exception as exc:
        log.warning("could not stamp key usage: %s", exc)


async def log_activity(
    principal: KeyPrincipal | None,
    operation: str,
    detail: dict,
    verdict: str | None,
    db,
) -> None:
    """Record what an agent asked, so the console can show it happening.

    "Other agents can use this" is a claim; a list of what they actually asked,
    with timestamps, is evidence. Best effort for the same reason as above.
    """
    try:
        await db.q(
            """
            INSERT INTO agent_activity (key_id, key_name, operation, detail, verdict)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                principal.key_id if principal else None,
                principal.name if principal else "anonymous",
                operation,
                json.dumps(detail),
                verdict,
            ),
        )
    except Exception as exc:
        log.warning("could not record agent activity: %s", exc)
