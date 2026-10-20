# EvidenceOps — Implementation Plan (derived from embedded requirements)

Status: Milestone 1 in progress. Plan approved standalone; milestone 6 included deferred.

## Milestones (status)
1. Contracts and fixtures — **IN PROGRESS** (schemas created; fixtures next)
2. Functional baseline — not started
3. Real learned components — not started
4. Workflow reliability — not started
5. Product and evidence — not started
6. Research/domain extensions — deferred (second domain fixtures + adapter study fixtures prepared when milestone 5 complete)

## Shared engineering (derived from prompt — no separate file copied)
- Contracts first, fixtures second, baseline third, model last.
- All answers expose citation / abstain / unsupported label.
- Idempotency enforced at service layer (same key = same effect, never double).
- Deterministic validators (image-statistic thresholds, BM25 ranking, schema checks) are authoritative; model suggestions only advisory.
- Simulation outputs labeled `simulated: true`; actual model inference labeled with seed/input/model/data hashes.
- Public browser build works without hosted backend; IndexedDB mirrors flow.
- No paid API, proprietary SDK, or hosted GPU required.

## Fixture design (20+ scenarios to build)
- Manufacturing defect (surface scratch, wrong batch, missing procedure version)
- Wrong-version procedure retrieval
- Missing-evidence (image present, batch missing, procedure missing)
- Malicious / contradictory document (fake procedure version number, conflicting batch record)
- Interruption (upload starts, server stops, resume from crash)
- Unanswerable / contradictory evidence slice (defect visible but procedure explicitly excludes component type)

## Dependency discipline (locked, small CPU profiles)
- Python: torch 2.13.0 (installed), torchvision, numpy 2.4.6, fastapi, pydantic, sqlite
- ML: rank-bm25 (BM25), sentence-transformers (embeddings), scikit-learn (baseline stats)
- Browser: ONNX Runtime Web for inference; no external inference service
- Frontend: Vite + TypeScript + React (standard); static bundle verified before mark complete
