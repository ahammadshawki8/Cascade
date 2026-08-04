"""Local dev launcher.

Windows only needs this. psycopg's async mode refuses to run on the
ProactorEventLoop that asyncio picks by default on Windows, and as of Python
3.14 `set_event_loop_policy` is deprecated and no longer influences the loop
uvicorn builds for itself. So the loop is constructed explicitly here.

Production is unaffected — the Dockerfile runs uvicorn directly on Linux,
where the default selector loop already works.

    python run_local.py [--port 8000] [--reload]
"""

from __future__ import annotations

import argparse
import asyncio
import selectors
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cascade API locally")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    config = uvicorn.Config(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        asyncio.run(
            server.serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
