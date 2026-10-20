# EvidenceOps — Project CLI / Build Notes

Product: EvidenceOps (P1) — Multimodal Evidence and Workflow Platform
Status: Milestone 1 (contracts/fixtures) in progress. Plan approved standalone.

## Actual build commands (verified on this host)
- Python 3.14.6 (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`)
- `uv` at `/Users/abhinav/.local/bin/uv`
- `node` v26.3.1 / `npm` 11.16.0 (for frontend build)
- `torch` 2.13.0 + `torchvision`, `fastapi` 0.136.3, `numpy` 2.4.6, `PIL` installed
- Browser: Google Chrome (`/Applications/Google Chrome.app`)
- Arch: arm64, 18 cores, ~48 GiB RAM

## Runtime modes
- `local` (default): FastAPI backend on localhost with SQLite persistence; frontend served by Vite dev or static build.
- `sandbox` (browser): IndexedDB-backed mirror of workflow flow; no hosted backend required; deterministic validators remain authoritative.
- `eval`: reproducible benchmark script (`scripts/evaluate.py`) with fixed seed; outputs artifacts with input/model/data hashes.

## Invariants (enforced by design, not by model suggestion)
- No external paid API or proprietary SDK required for MVP flow.
- Every answer claim exposes evidence or an unsupported/abstained label.
- Same idempotency key cannot cause two side effects in the reference service.
- Wrong-version / missing-evidence / malicious-document fixtures have executable expected outcomes.
- Deterministic validators (BM25, image-statistic thresholds, schema checks) override any model-generated suggestion.
- Simulation outputs (e.g., simulated tool result) labeled separately from actual model inference.

## Directory layout
```
contracts/v1/     JSON schemas (Case, Action, Evidence, ProcedureVersion)
docs/             IMPLEMENTATION_PLAN.md, WORKLOG.md, SHARED_ENGINEERING.md (derived)
fixtures/         20+ hand-checked scenarios + deterministic generator
backend/src/      FastAPI / Pydantic (retrieve, segment, draft, action, audit)
frontend/src/     React / Vite / TypeScript (workspace, case detail, review, eval)
models/           compact CNN segmenter export + embeddings + QA encoder
scripts/          train, export, evaluate, bench, serve
models/exports/   ONNX / TorchScript / JSON model cards with seed + hashes
```

## Licensing / attribution (recorded, not assumed)
- PyTorch (BSD-style), torchvision, numpy — BSD-compatible.
- FastAPI (MIT), Pydantic (MIT) — MIT.
- rank-bm25, sentence-transformers — MIT/Apache-2.
- ONNX Runtime — MIT.
- User-authored fixtures (this workspace) — unclaimed; user retains.
- No proprietary platform SDK used; no hosted GPU required.

## Commands (to be implemented by milestone)
- `scripts/seed.py` — deterministic dataset generation
- `scripts/train.py` — compact CNN segmenter + embeddings + QA encoder (CPU)
- `scripts/export.py` — ONNX / TorchScript with metadata hash
- `scripts/evaluate.py` — baseline vs model; outputs metrics + error slices
- `scripts/bench.py` — p95 latency; records environment + hash
- `scripts/serve.py` — FastAPI; `scripts/build_frontend.sh` — Vite static bundle

## Critical limits stated explicitly
- Evidence software, not clinical diagnosis / surgical control.
- Optional LLM failure must not bypass deterministic workflow checks.
- Actual segmentation inference runs; drawn mock overlays never reported as learned predictions.
