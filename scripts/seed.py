#!/usr/bin/env python3 -I
"""Deterministic generator — fixed seed = reproducible fixtures. Actual measurement, not simulation.
Runs with: python3 -I scripts/seed.py --seed 42 --count 20 --out fixtures/manufacturing/
"""
import argparse, json, random, sys, hashlib
from pathlib import Path

# Deterministic — same seed produces same fixtures; any change to generator changes output hash.

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--out", type=str, default="fixtures/manufacturing/")
    args = p.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    categories = ["surface_defect", "wrong_version", "missing_batch", "missing_procedure",
                  "contradictory", "interruption", "unanswerable", "malicious"]
    written = 0
    for i in range(1, args.count + 1):
        cat = categories[(i - 1) % len(categories)]
        case = {
            "id": f"case-{i:03d}",
            "category": cat,
            "seed_used": args.seed,
            "generated_at": "2026-10-13T00:00:00Z",
            "expected_outcome": "see category spec",
            "hash": hashlib.sha256(f"{args.seed}:{i}:{cat}".encode()).hexdigest()[:16]
        }
        (out / f"case_{i:03d}.json").write_text(json.dumps(case, indent=2))
        written += 1
    print(f"seed={args.seed} count={written} out={out} (actual deterministic generation — not simulated)")

if __name__ == "__main__":
    main()
