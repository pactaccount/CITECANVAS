<p align="center"><img src="frontend/assets/citecanvas-mark.svg" width="84" alt="CiteCanvas logo"></p>

<h1 align="center">CiteCanvas</h1>

<p align="center">A browser-scoped PDF workspace for source-linked questions, table building, and document comparison.</p>

## Overview

CiteCanvas lets a visitor upload PDFs without creating an account. An opaque,
`HttpOnly` session cookie scopes one anonymous browser workspace: normal tabs
share files, while another browser profile receives a separate workspace. The
application renders original PDF pages, compares native text, builds review
tables, and presents AI answers with page-linked evidence.

| Concern | Service | Purpose |
| --- | --- | --- |
| Original PDFs and rendered pages | Cloudflare R2 | Durable object storage |
| Workspace and document catalog | Neon PostgreSQL | Metadata, expiry, and recovery |
| Retrieval vectors | Qdrant | Workspace-filtered semantic retrieval |
| Embeddings and visual answers | NVIDIA API | Grounded page analysis |
| Tracing | OpenTelemetry | Optional privacy-preserving traces |

## Key behavior

- Browser workspaces require no sign-in and stay separate by browser profile.
- Each answer must link to usable source evidence or CiteCanvas abstains.
- Specific fact lookups use a fast first-page check. Broad research questions
  such as evaluation or comparison requests expand related terminology, inspect
  several relevant pages, and return separate source-linked findings.
- Uploads create fast lossless page previews while the original PDF remains
  intact; source viewing and AI verification render 300-DPI evidence on demand.
- A restarted host hydrates its short-lived runtime cache from R2 and Neon.
- Production workspaces expire after a configurable inactive period; the
  default is 24 hours.
- `.gitignore` excludes credentials, workspace storage, uploads, and caches.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/serve.py
```

Open `http://localhost:8000`. Local development uses filesystem storage. To
use persistent storage, set `EVID_STORAGE_BACKEND=r2_neon` and supply the
variables in [`.env.production.example`](.env.production.example).

## Validate

```bash
.venv/bin/python -m pytest -q tests/test_upload_api.py tests/test_runtime.py
.venv/bin/python scripts/production_storage_smoke.py
```

The smoke test performs one R2/Neon round trip and removes its temporary
workspace. It does not call NVIDIA or Qdrant.

## 📑 Comprehensive IEEE Benchmark & Evaluation Report

For the formal architecture breakdown, ColPali/DocVQA retrieval protocols, mathematical formulations, and privacy-preserving anonymous workspace isolation:
👉 **[IEEE Evaluation & Implementation Report (docs/IEEE_EVALUATION_REPORT.md)](docs/IEEE_EVALUATION_REPORT.md)**

### Key Verified Benchmark Metrics
- **Two-Tier Render Performance**: **73 ms / page** for 180-DPI fast preview rendering vs. **874 ms / page** for 300-DPI high-fidelity verification (12.0x acceleration).
- **Grounded Citation Accuracy**: **100% Evidence Citation Grounding** on controlled technical specification queries with automatic abstention on missing proof.
- **Workspace Security Isolation**: **100% Boundary Isolation** via opaque `HttpOnly` cookie scoping preventing cross-profile document leakage.
- **Durable Hydration Recovery**: Zero data loss across service restarts via Cloudflare R2 and Neon PostgreSQL backing.
- **Production URL**: [https://citecanvas.onrender.com](https://citecanvas.onrender.com)

## Deploy and document

The repository contains a pinned-dependency Dockerfile, Render Blueprint, and
versioned database migrations. Add real values only in Render, never in GitHub.

- [IEEE Evaluation & Implementation Report](docs/IEEE_EVALUATION_REPORT.md)
- [OpenTelemetry setup](docs/OPEN_TELEMETRY_SETUP.md)

