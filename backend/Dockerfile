# Fargate rejects arm64 images — always build with --platform linux/amd64
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# curl is needed by the container healthcheck below and by the ECS task
# definition's healthCheck command.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first so app edits don't invalidate the pip cache.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app/ ./app/
COPY worker/ ./worker/
COPY migrations/ ./migrations/
# The MCP server is served to agents from GET /api/mcp/server.mjs, so a judge
# with no clone can still connect their editor. Optional: the endpoint reports
# a clear 404 rather than failing if the build context did not include it.
COPY mcp/ ./mcp/

# /api/admin/reset reads 002_seed.sql off disk, so migrations must ship in the
# image — without them the demo reset 500s in production but works locally.

# Drop privileges. Nothing here needs root at runtime, and a container that
# runs as root is a finding in any production review.
RUN useradd --create-home --uid 10001 cascade \
    && chown -R cascade:cascade /app
USER cascade

EXPOSE 8000

# Belt and braces with the ECS task definition's own healthCheck: this one also
# covers docker-compose and any plain `docker run`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# One worker: the InterruptBus and the SSE broadcaster are in-process
# singletons (D4). Multiple workers would each hold a different subset of
# subscribers, so a step event could reach one browser and not another.
# Scale out with ECS task count, not with uvicorn workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
