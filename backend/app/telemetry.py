"""OpenTelemetry tracing (T3.3).

One trace per task, spanning API -> engine -> tools -> database, so a slow or
failed run can be read end to end instead of reconstructed from log lines.

Three properties this is built around:

  * **Optional.** With no OTLP endpoint configured, every function here becomes
    a no-op. A missing collector must never stall a request, and the demo has
    to run on a laptop with no observability stack at all.

  * **Never fatal.** Instrumentation failures are swallowed. Telemetry that can
    break the thing it observes is worse than no telemetry.

  * **No payloads.** Spans carry ids, tool names, modes and outcomes — not
    incident bodies, rule text or model output. Traces get shipped to third
    parties; they are not a place to leak operational data.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

_tracer: Any = None
_enabled = False


def init_tracing() -> bool:
    """Wire up the OTLP exporter. Returns whether tracing is live."""
    global _tracer, _enabled

    from app.config import settings

    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint and not settings.otel_console_export:
        log.info("tracing disabled (no OTEL_EXPORTER_OTLP_ENDPOINT)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.info(
            "tracing requested but opentelemetry-sdk is not installed; "
            "install the 'otel' extra to enable it"
        )
        return False

    try:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )

        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )

        if settings.otel_console_export:
            from opentelemetry.sdk.trace.export import (
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )

            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("cascade")
        _enabled = True
        log.info("tracing enabled -> %s", endpoint or "console")
        return True
    except Exception as exc:
        log.warning("tracing setup failed, continuing without it: %s", exc)
        return False


def shutdown_tracing() -> None:
    """Flush pending spans on shutdown."""
    if not _enabled:
        return
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except Exception:
        pass


@contextmanager
def span(name: str, **attributes: Any):
    """Start a span, or do nothing at all when tracing is off.

    Attribute values are coerced to primitives — the OTel SDK rejects
    arbitrary objects, and a rejected attribute would raise inside a `with`
    block wrapping real work.
    """
    if not _enabled or _tracer is None:
        yield None
        return

    try:
        with _tracer.start_as_current_span(name) as current:
            for key, value in attributes.items():
                if value is None:
                    continue
                if not isinstance(value, (str, bool, int, float)):
                    value = str(value)
                current.set_attribute(key, value)
            yield current
    except Exception as exc:
        log.debug("span %s failed: %s", name, exc)
        yield None


def record_exception(current: Any, exc: BaseException) -> None:
    if current is None:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        current.record_exception(exc)
        current.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:
        pass


def instrument_app(app: Any) -> None:
    """Auto-instrument FastAPI so every request is a root span."""
    if not _enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        log.info("FastAPI auto-instrumentation enabled")
    except ImportError:
        log.debug("fastapi instrumentation not installed")
    except Exception as exc:
        log.warning("fastapi instrumentation failed: %s", exc)


def is_enabled() -> bool:
    return _enabled
