"""Generate the training dataset with the physics twin, train every forecasting model
and write backend/data/dataset.csv, backend/data/dataset_summary.json,
backend/models/*.joblib, backend/models/gru.pt and backend/models/metrics.json.

Run from the project root:  venv\Scripts\python scripts\train_models.py
Add --evaluate-only to rebuild the dataset and re-score the saved models without retraining.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from ml_training import build_dataset, export_dataset, train_all
    t0 = time.time()
    workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    ds = build_dataset(workers=workers)
    summary = export_dataset(ds)
    print(f"[dataset] {summary['rows']} rows, {summary['runCount']} runs, {summary['rowsAboveLimit']} rows above the limit")
    if "--evaluate-only" in sys.argv:
        # Same seeds give the same dataset; score the saved models on it without retraining.
        import json
        from forecasting_engine import MODELS_DIR, load_metrics
        from ml_training import compute_metrics, predict_saved
        old = load_metrics()
        res = predict_saved(ds)
        timing = {mid: m.get("trainSeconds", 0.0) for mid, m in old.get("models", {}).items()}
        metrics = compute_metrics(ds, res["preds"], timing, res["importances"], res["gruStatus"])
        metrics["trainedAt"] = old.get("trainedAt", old.get("generatedAt"))
        (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    else:
        metrics = train_all(ds)
    for mid, m in metrics["models"].items():
        if "chronological" not in m:
            print(f"{mid}: {m.get('unavailable')}")
            continue
        c = m["chronological"]
        print(f"{mid:12s} " + "  ".join(f"+{h}m MAE {c[str(h)]['mae']:.3f} skill {c[str(h)]['skillRmse']}" for h in metrics["horizonsMin"]))
    print(f"[done] {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
