"""PII-conscious request logging and optional OpenTelemetry tracing."""

from contextlib import contextmanager, nullcontext
import json
import logging
import time
import os
from collections import Counter
from threading import Lock
from typing import Any, Iterator

from .integrations import get_audit_sink


logger = logging.getLogger("smriti.audit")
_metrics = Counter()
_metrics_lock = Lock()
_redis_metrics = None
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


def record_metric(name: str, value: int = 1, **labels: str) -> None:
    """Record low-cardinality metrics, using Redis when configured for production."""
    key = name + "{" + ",".join(f"{k}={labels[k]}" for k in sorted(labels)) + "}"
    if os.getenv("METRICS_BACKEND", "memory").lower() == "redis":
        try:
            global _redis_metrics
            if _redis_metrics is None:
                import redis

                url = os.getenv("REDIS_URL")
                if not url:
                    raise RuntimeError("REDIS_URL is required for Redis metrics")
                _redis_metrics = redis.Redis.from_url(url, decode_responses=True)
            _redis_metrics.hincrby("smriti:metrics", key, value)
            return
        except Exception as exc:
            logger.warning("metrics_backend_error=%s", exc)
    with _metrics_lock:
        _metrics[key] += value


def prometheus_metrics() -> str:
    snapshot = None
    if os.getenv("METRICS_BACKEND", "memory").lower() == "redis":
        try:
            if _redis_metrics is not None:
                snapshot = {str(key): int(value) for key, value in _redis_metrics.hgetall("smriti:metrics").items()}
        except Exception as exc:
            logger.warning("metrics_backend_error=%s", exc)
    if snapshot is None:
        with _metrics_lock:
            snapshot = dict(_metrics)
    lines = ["# TYPE smriti_events_total counter"]
    for key, value in sorted(snapshot.items()):
        event, raw_labels = key.split("{", 1)
        labels = raw_labels[:-1]
        pairs = [f'event="{event}"']
        for item in labels.split(",") if labels else []:
            label, label_value = item.split("=", 1)
            escaped = label_value.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))
            pairs.append(f'{label}="{escaped}"')
        lines.append(f"smriti_events_total{{{','.join(pairs)}}} {value}")
    return "\n".join(lines) + "\n"


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
