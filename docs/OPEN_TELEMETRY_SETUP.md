# OpenTelemetry setup

Evid emits privacy-preserving OpenTelemetry **traces** when an OTLP endpoint is
configured. It records operation names, durations, error types, page/source
counts, and provider status. It does not export PDFs, extracted text,
questions, answers, filenames, browser workspace tokens, API keys, or database
connection strings.

## Choose a destination

OpenTelemetry is the open standard and instrumentation layer. It needs a
collector and a trace viewer behind it.

1. **Open-source stack:** run an OpenTelemetry Collector and an open-source
   backend such as SigNoz or Jaeger. This keeps the complete telemetry stack
   self-hosted, but needs a separate always-on host and storage.
2. **Managed OTLP endpoint:** use an OpenTelemetry-compatible hosted backend.
   This avoids operating a collector. It is not fully self-hosted, but Evid
   remains portable because it sends standard OTLP traces.

For a fast Render deployment, choose a managed OTLP endpoint first. A self-
hosted collector can be substituted later without changing Evid code.

## Connect Render

After the destination gives you an OTLP/HTTP endpoint and, if required, a
header value, add these in the Render service environment settings:

```text
OTEL_SERVICE_NAME=evid
EVID_ENVIRONMENT=production
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://YOUR-OTLP-ENDPOINT
OTEL_EXPORTER_OTLP_HEADERS=YOUR-PROVIDER-HEADER-EXACTLY-AS-GIVEN
OTEL_EXPORTER_OTLP_TIMEOUT=1000
```

Use the base endpoint with `OTEL_EXPORTER_OTLP_ENDPOINT`; the OTLP exporter
adds `/v1/traces`. If a provider supplies a full traces URL instead, use
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and leave the base endpoint unset.

Do not put these values in GitHub or local source files. The repository only
contains their names in `.env.production.example` and `render.yaml`.

## Verify

1. Deploy the Render service.
2. Upload a small PDF and run one question.
3. In the trace viewer, find service `evid`.
4. Confirm traces named `evid.upload.process`, `evid.r2.put`,
   `evid.workflow.ask`, and `evid.nvidia.embeddings` appear.

If no endpoint is configured, tracing remains off and does not affect local
development or hosted requests.
