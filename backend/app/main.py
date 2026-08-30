"""FastAPI application factory (spec §8).

Day 0 state: lifespan + health + CORS only. Routers are added Day 1 onward:
    tasks · rules · playbooks · metrics · admin · copilot
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_pool, init_pool

# psycopg's async mode cannot drive Windows' default ProactorEventLoop, so a
# dev box would fail every connection attempt while ECS (Linux) works fine.
# Must run before uvicorn creates the loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task: asyncio.Task | None = None

    # Tracing first so startup itself is covered. No-ops without an endpoint.
    from app.telemetry import init_tracing, instrument_app, shutdown_tracing

    if init_tracing():
        instrument_app(app)

    if not settings.cascade_stub_mode:
        await init_pool()
        if settings.run_worker_in_process:
            from worker.handler import run_local_worker

            worker_task = asyncio.create_task(
                run_local_worker(settings.local_worker_interval_seconds)
            )
    else:
        log.info("stub mode — skipping db pool init")

    log.info(
        "cascade api up | stub_mode=%s | region=%s | in_process_worker=%s",
        settings.cascade_stub_mode,
        settings.aws_region,
        settings.run_worker_in_process,
    )

    yield

    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    if not settings.cascade_stub_mode:
        await close_pool()
    shutdown_tracing()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cascade",
        description=(
            "A procedural memory layer for AI agents that learns skills "
            "— and knows when to unlearn them."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # The deployed frontend is a different origin (Amplify -> CloudFront).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # demo is public read; tighten if needed
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- Routers -----------------------------------------------------------
    from app.routers import (
        admin,
        approvals,
        architecture,
        connections,
        copilot,
        events,
        intelligence,
        memory,
        metrics,
        playbooks,
        procedures,
        rules,
        tasks,
    )

    app.include_router(tasks.router,        prefix="/api", tags=["tasks"])
    app.include_router(rules.router,        prefix="/api", tags=["rules"])
    app.include_router(playbooks.router,    prefix="/api", tags=["playbooks"])
    app.include_router(metrics.router,      prefix="/api", tags=["metrics"])
    app.include_router(admin.router,        prefix="/api", tags=["admin"])
    app.include_router(copilot.router,      prefix="/api", tags=["copilot"])
    app.include_router(events.router,       prefix="/api", tags=["events"])
    app.include_router(approvals.router,    prefix="/api", tags=["approvals"])
    app.include_router(intelligence.router, prefix="/api", tags=["intelligence"])
    app.include_router(architecture.router, prefix="/api", tags=["architecture"])
    app.include_router(procedures.router,   prefix="/api", tags=["procedures"])
    app.include_router(connections.router,  prefix="/api", tags=["connections"])
    # The one surface built for callers who are not this app. Keyed separately:
    # everything else here trusts the browser session or a shared token, and
    # this trusts a per-agent credential with scopes.
    app.include_router(memory.router,       prefix="/api", tags=["memory"])

    # Internal bridge: Lambda → API SSE (no /api prefix)
    app.include_router(events.internal_router, tags=["internal"])

    return app


app = create_app()
