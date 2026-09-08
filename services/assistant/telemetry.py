"""Bounded in-process spans, with optional standard OTLP export."""

from collections import deque
import os
import threading

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
    SimpleSpanProcessor,
)

_spans = deque(maxlen=200)
_lock = threading.Lock()
_configured = False


class RecentSpanExporter(SpanExporter):
    def export(self, spans):
        with _lock:
            for span in spans:
                _spans.append(
                    {
                        "name": span.name,
                        "trace_id": format(span.context.trace_id, "032x"),
                        "duration_ms": round((span.end_time - span.start_time) / 1_000_000),
                        "attributes": dict(span.attributes or {}),
                    }
                )
        return SpanExportResult.SUCCESS


def configure():
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "practice-assistant"}))
    provider.add_span_processor(SimpleSpanProcessor(RecentSpanExporter()))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True


def recent_spans():
    with _lock:
        return list(_spans)
