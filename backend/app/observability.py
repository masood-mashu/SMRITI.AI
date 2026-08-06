"""PII-conscious request logging and optional OpenTelemetry tracing."""

from contextlib import contextmanager, nullcontext
import json
import logging
import time
import os
from typing import Any, Iterator

from .integrations import get_audit_sink


logger = logging.getLogger("smriti.audit")
_tracer = None
try:
    from opentelemetry import trace
    if os.getenv("OTEL_ENABLED", "false").lower() == "true":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint:
            raise RuntimeError("OTEL_EXPORTER_OTLP_ENDPOINT is required when OTEL_ENABLED=true")
        provider = TracerProvider(
            resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "smriti-api")})
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer("smriti")
except (ImportError, RuntimeError):
    pass


def audit_log(event: str, **fields: Any) -> None:
    """Emit structured metadata only; callers must not pass report contents."""
    logger.info(json.dumps({"event": event, **fields}, default=str, sort_keys=True))
    try:
        sink = get_audit_sink()
        if sink is not None:
            sink.write(event, fields)
    except Exception as exc:
        logger.warning("audit_sink_error=%s", exc)


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[Any]:
    scope = _tracer.start_as_current_span(name) if _tracer else nullcontext()
    with scope as span:
        if span is not None:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        started = time.perf_counter()
        try:
            yield span
        finally:
            audit_log("span_complete", span=name, duration_ms=round((time.perf_counter() - started) * 1000, 2))
