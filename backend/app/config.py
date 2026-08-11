"""Environment configuration — mirrors CASCADE_BUILD_SPEC.md §2.1.3.

OWNER: Ashfaq (Track A).
Adding a variable here means adding it to .env.example AND spec §2.1.3 in the
same PR, then pinging the other person (WORKFLOW.md §1).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core -------------------------------------------------------------
    aws_region: str = "us-east-1"
    database_url: str = "postgresql://root@localhost:26257/cascade?sslmode=disable"

    # Day-0 stub toggle (WORKFLOW.md §2). true => contracts.py returns canned
    # data so the shell can be built before the engine exists.
    cascade_stub_mode: bool = False

    # --- Bedrock (model IDs, spec §2 + DEVIATIONS #13) --------------------
    # On-demand Bedrock invocation requires an INFERENCE PROFILE id, which
    # carries a us. or global. region prefix. A bare "anthropic.<model>" id
    # is provisioned-throughput only and fails with AccessDeniedException
    # reading "not available for this account", which is easy to misread as a
    # model-access problem. Verified live against account 897545289507.
    bedrock_agent_model_id: str = "us.anthropic.claude-sonnet-4-6"              # agent + compiler
    bedrock_fast_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # precondition, extraction, recheck
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"                # 1024-d, normalize=true

    # --- Alternate LLM providers (spec deviation #11) ---------------------
    # Bedrock stays the primary path. These exist so the full learn/reuse/
    # unlearn loop is runnable on free-tier keys during development; whenever
    # one of them serves a request, llm_status() reports "degraded" and the UI
    # shows it. Chat falls back groq -> openrouter; embeddings use HuggingFace.
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    hf_api_key: str = ""
    # Must be 1024-d to match playbooks.embedding VECTOR(1024) and the index.
    hf_embed_model: str = "BAAI/bge-large-en-v1.5"

    # --- AWS resources ----------------------------------------------------
    episodes_bucket: str = "cascade-episodes-local"
    cascade_queue_url: str = ""
    sns_bus_topic_arn: str = ""
    enable_sns_fanout: bool = False

    # --- Secrets / auth ---------------------------------------------------
    # Three roles (T3.1): viewer reads, operator runs and approves, admin
    # changes policy. Tokens may carry a `name:` prefix so audit_log.actor
    # records who acted rather than a shared literal.
    admin_token: str = "dev-admin-token"
    operator_token: str = "dev-operator-token"
    viewer_token: str = "dev-viewer-token"
    internal_sse_secret: str = "dev-internal-secret"
    webhook_secret: str = "dev-webhook-secret"

    # --- Observability (T3.3) ---------------------------------------------
    # OTLP endpoint for traces. Empty disables tracing entirely, so the app
    # never blocks on a collector that isn't there.
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "cascade-api"
    otel_console_export: bool = False

    # --- Retention (T3.4) -------------------------------------------------
    # Row-level TTL, applied by migration 004. Both tables are append-only and
    # would otherwise grow without bound.
    audit_log_retention_days: int = 90
    episode_retention_days: int = 30

    # --- Worker -> API bridge --------------------------------------------
    api_base_url: str = "http://localhost:8000"

    # Run the outbox worker inside the API process. Local dev has no SQS or
    # Lambda, so without this the learn loop stops at "compile event queued".
    # Deployments leave it false — Lambda owns the queue there.
    run_worker_in_process: bool = False
    local_worker_interval_seconds: float = 2.0

    # --- Budgets (spec §5.4) ---------------------------------------------
    max_steps_per_task: int = 15
    max_wall_clock_seconds: int = 60
    max_tokens_per_task: int = 25_000
    max_concurrent_tasks: int = 5

    # --- Retrieval tuning (D3; re-tune on Day 6, record the final value) --
    retrieval_l2_threshold: float = 0.85   # L2 on unit vectors, NOT cosine
    dedup_l2_threshold: float = 0.40

    # --- Autonomy gating (T1.1, D2) ---------------------------------------
    # Tier-1 (production-critical) services always require human sign-off for
    # irreversible actions; that gate is not configurable.
    #
    # This is an optional *second* gate on runbook confidence. Set to 0.6 to
    # make a new runbook earn autonomy over three supervised successes
    # (0.30 -> 0.45 -> 0.60). Off by default because it stops every first reuse.
    autonomy_min_confidence: float = 0.0

    # --- Savings accounting (T1.4) ----------------------------------------
    # Blended USD per 1M tokens, used to price measured token savings.
    usd_per_mtok: float = 1.60

    # --- Feature flags ----------------------------------------------------
    # Off by default: spec edge case #15 guarantees the mock world has zero
    # external dependencies, so a live outbound call can never hang the demo.
    enable_outbound_webhook: bool = False


settings = Settings()
