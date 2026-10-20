<p align="center"><img src="frontend/assets/citecanvas-mark.svg" width="72" alt="CiteCanvas logo"></p>

<h1 align="center">CiteCanvas</h1>

<p align="center">A browser-scoped PDF workspace for source-linked questions, table building, and document comparison.</p>

## What it does

- Keeps each browser's PDF workspace separate without requiring sign-in.
- Shows original pages alongside source-linked AI answers.
- Builds reviewable tables and compares native PDF text.
- Uses R2, Neon, Qdrant, and NVIDIA in the production configuration.

## Deployment

The repository includes a Dockerfile, Render Blueprint, database migrations,
and a safe `.env.production.example`. Put real credentials only in Render.

See [OpenTelemetry setup](docs/OPEN_TELEMETRY_SETUP.md) for optional tracing.
