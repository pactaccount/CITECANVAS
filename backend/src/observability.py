"""Privacy-preserving OpenTelemetry tracing for Evid's server-side pipeline.

Telemetry is opt-in: no exporter is initialised unless an OTLP endpoint is set.
Spans contain service operations, counts, durations, and errors only. They never
include PDF text, questions, answers, filenames, workspace tokens, or secrets.
"""

import os
from contextlib import contextmanager

_configured = False


def configure_observability():
    """Configure OTLP/HTTP tracing from standard OpenTelemetry variables."""
    global _configured
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if _configured or not endpoint:
        return bool(endpoint)
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "citecanvas"),
        SERVICE_VERSION: os.getenv("EVID_RELEASE", "unversioned"),
        "deployment.environment": os.getenv("EVID_ENVIRONMENT", "local"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True
    return True


@contextmanager
def span(name, attributes=None):
    """Create a safe span, recording exceptions without leaking user content."""
    if not _configured:
        yield None
        return
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    tracer = trace.get_tracer("evid.pipeline")
    with tracer.start_as_current_span(name) as active:
        for key, value in (attributes or {}).items():
            if value is not None:
                active.set_attribute(key, value)
        try:
            yield active
        except Exception as error:
            active.record_exception(error)
            active.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise
