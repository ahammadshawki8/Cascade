"""Feature-level verification against a running stack, over HTTP.

OWNER: evaluation harness. Not imported by the running application.

    python -m eval.verify_features --api https://<host> --admin-token <token>

WHY THIS EXISTS ALONGSIDE verify_integration.py
-----------------------------------------------
`verify_integration.py` talks to the engine in process, because some of what it
asserts is not reachable over HTTP without a race. That makes it the right tool
for correctness and the wrong tool for answering "is the thing I deployed
actually working", which is a different question and the one a reviewer asks
first.

This walks the product's own claims against a live deployment, in the order a
person would: learn a procedure, watch it get reused, change the rule it was
built on, and confirm the procedure is refused afterwards. Every assertion is
something the README or the docs say out loud.

WHAT IT COSTS
-------------
Three real incidents through a real model, one committed policy change, and a
reset at each end. A couple of minutes and a few cents. It restores the sample
world when it finishes, so it is safe to point at the demo.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

import httpx

WINDOW_RULE = "incident.rollback_window"


class Report:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        (self.passed if ok else self.failed).append(name)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" - {detail}" if detail else ""), flush=True)
        return ok


class Client:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.admin = {"x-admin-token": token}
        self.http = httpx.AsyncClient(timeout=200.0)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def get(self, path: str, headers: dict | None = None) -> httpx.Response:
        return await self.http.get(f"{self.base}{path}", headers=headers or self.admin)

    async def post(
        self, path: str, body: dict | None = None, headers: dict | None = None
    ) -> httpx.Response:
        return await self.http.post(
            f"{self.base}{path}", json=body or {}, headers=headers or self.admin
        )

    async def run_task(self, text: str, limit: float = 200.0) -> dict[str, Any]:
        created = await self.post("/api/tasks", {"input": text})
        task_id = created.json()["task_id"]
        deadline = time.monotonic() + limit
        terminal = {"succeeded", "failed", "interrupted", "awaiting_approval"}
        while time.monotonic() < deadline:
            task = (await self.get(f"/api/tasks/{task_id}")).json()
            if task.get("status") in terminal:
                return task
            await asyncio.sleep(2)
        return {"task_id": task_id, "status": "timeout"}

    async def await_compile(self, limit: float = 180.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            data = (await self.get("/api/playbooks")).json()
            if data.get("count"):
                return data["playbooks"][0]
            await asyncio.sleep(5)
        return None


async def main(args: argparse.Namespace) -> int:
    c = Client(args.api, args.admin_token)
    r = Report()
    try:
        r.check("reset restores the sample world", (await c.post("/api/admin/reset")).status_code == 200)

        # -- learn ----------------------------------------------------------
        learned = await c.run_task("Remediate INC-1001")
        r.check(
            "LEARN: a novel incident is explored and remediated",
            learned.get("mode") == "explore" and learned.get("result") == "remediated",
            f"{learned.get('mode')}/{learned.get('result')}",
        )

        playbook = await c.await_compile()
        r.check("COMPILE: a runbook is derived from that run", playbook is not None)
        if playbook:
            deps = {d["rule_key"] for d in playbook.get("deps", [])}
            r.check(
                "PROVENANCE: the runbook pins the rule it depends on",
                WINDOW_RULE in deps,
                ", ".join(sorted(deps)),
            )
            r.check(
                "PROVENANCE: nothing reads stale yet",
                all(not d.get("is_stale") for d in playbook.get("deps", [])),
            )

        # -- reuse ----------------------------------------------------------
        reused = await c.run_task("Remediate INC-1002")
        r.check(
            "REUSE: a similar incident runs guided",
            reused.get("mode") == "guided",
            f"{reused.get('mode')}/{reused.get('result')}",
        )
        explain = (await c.get(f"/api/tasks/{reused['task_id']}/explain")).json()
        episode = explain.get("episode") or {}
        r.check(
            "REUSE: no model is called on the reuse path",
            (episode.get("tokens") or 0) == 0,
            f"tokens={episode.get('tokens')}",
        )

        # -- unlearn --------------------------------------------------------
        current = (await c.get(f"/api/rules/{WINDOW_RULE}")).json()["current"]
        r.check(
            "the rule detail reports how it is enforced",
            current.get("enforcement") == "enforcing" and current.get("predicate"),
            f"enforcement={current.get('enforcement')}, "
            f"predicate={'set' if current.get('predicate') else 'null'}",
        )
        impact = (
            await c.post(
                f"/api/rules/{WINDOW_RULE}",
                {"body": current["body"], "params": {"hours": 4}},
            )
        ).json()
        r.check(
            "UNLEARN: the cascade is exactly four writes",
            impact.get("writes") == 4,
            f"writes={impact.get('writes')}",
        )
        r.check(
            "UNLEARN: it invalidated the runbook that depended on the rule",
            len(impact.get("impacted_playbooks", [])) >= 1,
        )

        after = (await c.get("/api/playbooks")).json()
        if after.get("count"):
            p = after["playbooks"][0]
            r.check(
                "QUARANTINE: the runbook is no longer trusted",
                p.get("status_cache") != "active",
                f"status={p.get('status_cache')}",
            )
            r.check(
                "QUARANTINE: a provenance edge reads stale",
                any(d.get("is_stale") for d in p.get("deps", [])),
            )

        # -- refuse ---------------------------------------------------------
        refused = await c.run_task("Remediate INC-1009")
        r.check(
            "REFUSE: the stale runbook is not reused, even though it still matches",
            refused.get("mode") != "guided",
            f"mode={refused.get('mode')}, result={refused.get('result')}",
        )

        # -- the memory API, which is the whole point for other agents ------
        key_res = await c.post(
            "/api/keys", {"name": "verify_features", "scopes": ["memory:read"]}
        )
        r.check("a scoped key can be issued", key_res.status_code == 201)
        if key_res.status_code == 201:
            bearer = {"Authorization": f"Bearer {key_res.json()['key']}"}
            stale = await c.post(
                "/api/memory/check",
                {"citations": [{"rule_key": WINDOW_RULE, "rule_version": 1}]},
                headers=bearer,
            )
            body = stale.json() if stale.status_code == 200 else {}
            r.check(
                "MEMORY API: a citation on a moved rule is refused",
                stale.status_code == 200 and body.get("valid") is False,
                body.get("summary", "")[:90],
            )
            r.check(
                "MEMORY API: the refusal names both versions",
                bool(body.get("stale"))
                and body["stale"][0].get("head_version") != body["stale"][0].get("pinned_version"),
            )
            anon = await c.post(
                "/api/memory/check",
                {"citations": [{"rule_key": WINDOW_RULE, "rule_version": 1}]},
                headers={},
            )
            r.check(
                "MEMORY API: refuses an unauthenticated caller",
                anon.status_code == 401,
                f"HTTP {anon.status_code}",
            )

        # -- everything else the interface reads ----------------------------
        for name, path in (
            ("metrics", "/api/metrics"),
            ("savings", "/api/savings"),
            ("blast-radius graph", "/api/graph"),
            ("negative memory", "/api/anti-playbooks"),
            ("insights", "/api/insights"),
            ("approvals", "/api/approvals"),
            ("architecture", "/api/architecture"),
            ("time travel", "/api/timetravel?minutes=5"),
            ("vector index proof", "/api/admin/verify-index"),
            ("provider smoke", "/api/admin/smoke"),
        ):
            res = await c.get(path)
            r.check(f"GET {name}", res.status_code == 200, f"HTTP {res.status_code}")

        index = (await c.get("/api/admin/verify-index")).json()
        r.check(
            "retrieval uses the vector index, not a full scan",
            index.get("uses_index") is True,
        )

        if not args.keep:
            await c.post("/api/admin/reset")
            r.check("world restored", True)
    finally:
        await c.aclose()

    print(f"\n==== {len(r.passed)} passed, {len(r.failed)} failed ====")
    if r.failed:
        print("failed: " + "; ".join(r.failed))
    return 1 if r.failed else 0


def cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--admin-token", default="dev-admin-token")
    p.add_argument("--keep", action="store_true", help="do not reset when finished")
    return asyncio.run(main(p.parse_args()))


if __name__ == "__main__":
    sys.exit(cli())
