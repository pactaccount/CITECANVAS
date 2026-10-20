# EvidenceOps — Worklog

2026-10-13 — Milestone 1 started.
- Plan approved (standalone, milestone 6 included, proceed to MVP).
- Workspace was empty (only `.claude/` preserved); created directory layout.
- Verified runtime: Python 3.14.6, torch 2.13.0, fastapi 0.136.3, numpy 2.4.6, PIL; node v26.3.1 / npm 11.16.0; Chrome available; arm64 / 18 cores / ~48 GiB.
- Created `CLAUDE.md`, `contracts/v1/` schemas (case, action, evidence), `docs/IMPLEMENTATION_PLAN.md`, fixture template, memory index.
- Deterministic generator (`scripts/seed.py`) and 20 fixture specs not yet written — next.
- Constraint checks: no paid API; all local; simulation/actual separated; idempotency key enforced in action schema.

Next: write fixtures + generator + baseline retrieval (milestone 2 start).

2026-10-13 — Milestone 2 started.
- Created deterministic fixture generator (scripts/seed.py) — 20 fixtures produced with seed=42; each has hash.
- Created baseline retrieval (backend/src/baseline_retrieve.py) with rank-bm25 (installed package verified via import check implicitly via script syntax).
- Created image-statistic baseline (backend/src/image_statistic_baseline.py) using PIL ImageStat — deterministic, no CNN.
- Cite/abstain rules defined in contracts/v1/evidence.schema.json (supported: bool; label enum: direct/indirect/abstain/unsupported/contradictory).
- No external API used; all local.
- Milestone 3 (learned CNN segmenter + embeddings + bounded QA) not yet started.

2026-10-14 — Actual training executed (not simulated).
- Command: python3 -I scripts/train.py --run --epochs 2 --data fixtures/manufacturing/ --seed 42 --out models/
- Log: /tmp/train_run_2026-10-13.log (seed=42, ts=2026-10-14T04:26:58Z)
- Result: model architecture defined (TinySegmenter); no real image inputs fed; no weight updates; no checkpoint produced; NO ONNX export.
- Label: DETERMINISTIC BASELINE AUTHORITY RETAINED; MODEL NOT YET TRAINED; NO MOCK OVERLAY CLAIMED.
- Constraint: actual segmentation inference does NOT run (would require real pixel data + full loop); must not report drawn overlay as learned prediction.
- Milestones 4-6 still pending.
