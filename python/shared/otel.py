"""OpenTelemetry setup for Python AI engine.

Initializes tracing and metrics with OTLP export.
Instruments FastAPI and requests libraries automatically.

Env vars:
  OTEL_EXPORTER_OTLP_ENDPOINT  — collector URL (default: http://localhost:4318)
  OTEL_SERVICE_NAME             — service name (default: chatrag-python)
  OTEL_ENABLED                  — set to "false" to disable (default: true)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def init_otel() -> None:
    """Initialize OpenTelemetry tracing + metrics. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return

    enabled = os.getenv("OTEL_ENABLED", "true").lower() not in ("false", "0", "no")
    if not enabled:
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        _initialized = True
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        service_name = os.getenv("OTEL_SERVICE_NAME", "chatrag-python")

        resource = Resource.create({"service.name": service_name})

        # Tracing
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        metric_exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=15_000
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # Auto-instrument FastAPI (applied when app is created)
        FastAPIInstrumentor().instrument()

        logger.info(f"✅ OpenTelemetry initialized — endpoint={endpoint} service={service_name}")
        _initialized = True

    except Exception as e:
        logger.warning(f"⚠️ OpenTelemetry init failed (non-fatal): {e}")
        _initialized = True


# ── Tracer & Meter accessors ─────────────────────────────────────────────────

def get_tracer(name: str = "chatrag.python"):
    """Get an OTel tracer (returns no-op if OTel not initialized)."""
    from opentelemetry import trace
    return trace.get_tracer(name)


def get_meter(name: str = "chatrag.python"):
    """Get an OTel meter (returns no-op if OTel not initialized)."""
    from opentelemetry import metrics
    return metrics.get_meter(name)
