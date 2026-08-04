"""LLM transport — Bedrock, OpenAI-compatible, HuggingFace (spec §2).

OWNER: Shawki (Track B).

The engine asks for three capabilities: plan-with-tools, short-completion, and
embed. This module decides *who serves them*, in a fixed preference order:

    chat   bedrock -> groq -> openrouter -> deterministic local planner
    embed  bedrock -> huggingface        -> deterministic local embedder

Bedrock stays first because the AWS story is the one we tell. The others exist
so the whole learn/reuse/unlearn loop is runnable on free-tier keys, and the
local path exists so it is runnable on none at all.

Groq and OpenRouter are both OpenAI-compatible, so they share one client and
differ only by base URL, model id and auth header. Anthropic and OpenAI
disagree about tool-call shape, so `to_openai_tools` translates the frozen
TOOL_DEFINITIONS rather than maintaining two copies.

Embedding dimension is not negotiable: the `playbooks.embedding` column is
VECTOR(1024) and the index is built for it. `BAAI/bge-large-en-v1.5` is 1024-d,
which is why it is the default HF model. Anything else is projected to fit and
flagged, because silently storing the wrong width would corrupt retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from typing import Any

log = logging.getLogger(__name__)

EMBED_DIM = 1024

_OPENAI_COMPATIBLE = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "default_chat": "llama-3.3-70b-versatile",
        "default_fast": "llama-3.1-8b-instant",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "default_chat": "meta-llama/llama-3.3-70b-instruct:free",
        "default_fast": "meta-llama/llama-3.3-70b-instruct:free",
    },
}


def _settings() -> Any:
    from app.config import settings

    return settings


def _key(env_name: str) -> str | None:
    """Read a credential from settings first, then the process environment."""
    value = getattr(_settings(), env_name.lower(), None) or os.getenv(env_name)
    return value.strip() if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------------------
# Tool-shape translation
# ---------------------------------------------------------------------------


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic tool defs -> OpenAI function defs.

    Anthropic: {name, description, input_schema}
    OpenAI:    {type: "function", function: {name, description, parameters}}
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
            },
        }
        for tool in tools
    ]


# ---------------------------------------------------------------------------
# Bedrock
# ---------------------------------------------------------------------------

_bedrock_client: Any = None
_bedrock_checked = False


def bedrock_client():
    """Cached bedrock-runtime client, or None when unusable."""
    global _bedrock_client, _bedrock_checked

    if _bedrock_checked:
        return _bedrock_client
    _bedrock_checked = True

    if os.getenv("MOCK_BEDROCK", "").lower() == "true":
        log.info("bedrock disabled by MOCK_BEDROCK=true")
        return None

    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        log.info("bedrock unavailable: %s", exc)
        return None

    try:
        session = boto3.Session()
        if session.get_credentials() is None:
            log.info("bedrock unavailable: no AWS credentials resolved")
            return None
        _bedrock_client = session.client(
            "bedrock-runtime",
            region_name=_settings().aws_region,
            config=Config(
                retries={"max_attempts": 2, "mode": "standard"},
                connect_timeout=5,
                read_timeout=40,
            ),
        )
        return _bedrock_client
    except Exception as exc:  # pragma: no cover - defensive
        log.info("bedrock unavailable: %s", exc)
        return None


async def bedrock_invoke(model_id: str, body: dict[str, Any]) -> dict[str, Any] | None:
    client = bedrock_client()
    if client is None:
        return None
    try:
        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())
    except Exception as exc:
        log.warning("bedrock %s failed: %s", model_id, exc)
        raise


# ---------------------------------------------------------------------------
# OpenAI-compatible chat (Groq, OpenRouter)
# ---------------------------------------------------------------------------


def available_openai_providers() -> list[str]:
    """Configured OpenAI-compatible providers, in preference order."""
    return [name for name, spec in _OPENAI_COMPATIBLE.items() if _key(spec["env"])]


async def openai_chat(
    provider: str,
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> dict[str, Any] | None:
    """One chat completion. Returns the raw `choices[0]` payload, or None."""
    spec = _OPENAI_COMPATIBLE.get(provider)
    if spec is None:
        return None
    api_key = _key(spec["env"])
    if not api_key:
        return None

    payload: dict[str, Any] = {
        "model": model or spec["default_chat"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {"Authorization": f"Bearer {api_key}"}
    if provider == "openrouter":
        # OpenRouter asks for attribution headers; harmless elsewhere.
        headers["HTTP-Referer"] = "https://github.com/ahammadshawki8/Cascade"
        headers["X-Title"] = "Cascade"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{spec['base_url']}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                log.warning(
                    "%s chat %s: %s", provider, response.status_code, response.text[:300]
                )
                response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("%s chat failed: %s", provider, exc)
        raise

    choices = data.get("choices") or []
    if not choices:
        return None
    return {
        "message": choices[0].get("message", {}),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": data.get("usage", {}),
        "provider": provider,
        "model": payload["model"],
    }


# ---------------------------------------------------------------------------
# HuggingFace embeddings
# ---------------------------------------------------------------------------

HF_DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"  # 1024-d, matches VECTOR(1024)


def huggingface_available() -> bool:
    return _key("HF_API_KEY") is not None


async def huggingface_embed(text: str, model: str | None = None) -> list[float] | None:
    """Feature-extraction embedding, L2-normalized to unit length.

    Normalization is mandatory, not cosmetic: decision D2 says the index is
    built for L2 and L2 ranking only equals cosine ranking on unit vectors.
    """
    api_key = _key("HF_API_KEY")
    if not api_key:
        return None

    model = model or getattr(_settings(), "hf_embed_model", None) or HF_DEFAULT_MODEL

    try:
        import httpx

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model}",
                json={"inputs": text, "options": {"wait_for_model": True}},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code >= 400:
                log.warning(
                    "huggingface embed %s: %s",
                    response.status_code,
                    response.text[:300],
                )
                response.raise_for_status()
            data = response.json()
    except Exception as exc:
        log.warning("huggingface embed failed: %s", exc)
        raise

    vector = _flatten_embedding(data)
    if not vector:
        return None
    return _fit_dimension(vector, model)


def _flatten_embedding(data: Any) -> list[float]:
    """HF returns [floats], [[floats]] or token-level [[[floats]]] by model."""
    if isinstance(data, dict):
        return []
    if not isinstance(data, list) or not data:
        return []

    if isinstance(data[0], (int, float)):
        return [float(x) for x in data]

    if isinstance(data[0], list) and data[0] and isinstance(data[0][0], (int, float)):
        return [float(x) for x in data[0]]

    # Token-level output: mean-pool across tokens.
    if isinstance(data[0], list) and data[0] and isinstance(data[0][0], list):
        tokens = data[0]
        width = len(tokens[0])
        pooled = [0.0] * width
        for token in tokens:
            for i, value in enumerate(token):
                pooled[i] += float(value)
        return [v / len(tokens) for v in pooled]

    return []


def _fit_dimension(vector: list[float], model: str) -> list[float]:
    """Coerce to EMBED_DIM and unit length.

    The column is VECTOR(1024) and the index is built for that width, so a
    mismatched model has to be reconciled rather than silently stored. Padding
    or folding is lossy — it is logged loudly so a wrong model choice is
    obvious instead of quietly degrading retrieval.
    """
    if len(vector) != EMBED_DIM:
        log.warning(
            "embedding model %s returned %d dims, expected %d — reshaping "
            "(prefer a 1024-d model such as %s)",
            model,
            len(vector),
            EMBED_DIM,
            HF_DEFAULT_MODEL,
        )
        if len(vector) < EMBED_DIM:
            vector = vector + [0.0] * (EMBED_DIM - len(vector))
        else:
            folded = [0.0] * EMBED_DIM
            for i, value in enumerate(vector):
                folded[i % EMBED_DIM] += value
            vector = folded

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        vector = [0.0] * EMBED_DIM
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


# ---------------------------------------------------------------------------
# Introspection — surfaced at /api/admin/smoke
# ---------------------------------------------------------------------------


def configured_providers() -> dict[str, Any]:
    """What is actually wired up right now."""
    return {
        "bedrock": bedrock_client() is not None,
        "groq": _key("GROQ_API_KEY") is not None,
        "openrouter": _key("OPENROUTER_API_KEY") is not None,
        "huggingface": huggingface_available(),
    }
