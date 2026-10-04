"""Re-score the saved forecasting models on the saved dataset without retraining and
rewrite backend/models/metrics.json (adds any new metrics, keeps training times).

Usage from the project root:  venv\Scripts\python scripts\evaluate_models.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    from forecasting_engine import MODELS_DIR, load_metrics
    from ml_training import compute_metrics, load_dataset_csv, predict_saved
    t0 = time.time()
    old = load_metrics()
    ds = load_dataset_csv()
    print(f"[evaluate] loaded {len(ds['meta'])} rows in {time.time() - t0:.0f} s")
    res = predict_saved(ds)
    timing = {mid: m.get("trainSeconds", 0.0) for mid, m in old.get("models", {}).items()}
    metrics = compute_metrics(ds, res["preds"], timing, res["importances"], res["gruStatus"])
    if old.get("generatedAt"):
        metrics["trainedAt"] = old.get("trainedAt", old["generatedAt"])
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    for mid, m in metrics["models"].items():
        if "chronological" in m:
            c = m["chronological"]
            print(f"{mid:12s} " + "  ".join(f"+{h}m within1C {c[h]['within1Pct']:.1f}% MAE {c[h]['mae']:.2f}" for h in ("5", "15", "30")))
    print(f"[evaluate] done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
