"""Run the multi-seed benchmark (fixed vs reactive vs predictive twin) and write
backend/data/benchmark.json, which the About page displays.

Usage from the project root:  venv\Scripts\python scripts\run_benchmark.py [--seeds 10] [--model xgboost]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    from benchmark_runner import METRICS, run_benchmark
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--duration", type=int, default=3600)
    ap.add_argument("--model", default="xgboost")
    args = ap.parse_args()
    workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    res = run_benchmark(seeds=args.seeds, duration_s=args.duration, model=args.model, workers=workers)
    for sc in res["scenarios"]:
        print(f"\n{sc['name']}")
        for pol in res["policies"]:
            p = sc["policies"][pol]
            print(f"  {pol:10s} " + "  ".join(
                f"{k}={p[k]['mean']}+-{p[k]['std']}" for k, _, _ in METRICS if k in ("totalKwh", "waterL", "minutesAboveLimit", "hotspotEvents", "leadTimeMin")))


if __name__ == "__main__":
    main()
