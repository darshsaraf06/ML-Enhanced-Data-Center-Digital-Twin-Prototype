"""
Dataset generation, model training and evaluation for rack inlet forecasting.

Dataset: produced by running the physics twin headless across climates, rack counts,
scales, control policies, events, operator-style disturbances and seeds. Every 30
simulated seconds each rack contributes one row of features (forecasting_engine.FEATURES)
plus its actual inlet temperature 5, 10, 15, 30 and 60 minutes later.

Splits:
  chronological  - in each training run the first 65 % of time trains the models
                   (rows whose target time is also inside that window), the last 35 %
                   is the test set.
  held-out scenario - complete runs containing events never seen in training
                   (flood, cyclone).

Usage: python scripts/train_models.py  (writes backend/data and backend/models)
"""

import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

import model_params as P
from forecasting_engine import FEATURE_NAMES, FEATURES, HORIZONS, MODEL_INFO, MODELS_DIR, SEQ_LEN

DATA_DIR = Path(__file__).parent / "data"
HELD_OUT_EVENTS = ["flood", "cyclone"]
TRAIN_EVENTS = ["cooling_failure", "power_loss", "heatwave", "workload_spike", "wildfire_smoke",
                "earthquake", "containment_breach", "fan_degradation", "rack_overload"]
CLIMATE_IDS = ["temperate", "coastal_monsoon", "hot_desert", "nordic_cold", "extreme_heat"]
POLICIES = ["fixed", "reactive", "random", "random", "predictive"]
RUN_DURATION_S = 4 * 3600
SAMPLE_S = P.FORECAST_INTERVAL_S
CHRONO_FRACTION = 0.65
LIMIT = P.DEFAULT_INLET_LIMIT_C

try:
    import torch
    import torch.nn as nn

    class GRUForecaster(nn.Module):
        def __init__(self, n_features: int, n_out: int, hidden: int = 48):
            super().__init__()
            self.gru = nn.GRU(n_features, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, n_out))

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1, :])
    TORCH_OK = True
except Exception:   # pragma: no cover - torch optional
    TORCH_OK = False
    GRUForecaster = None


# ── dataset ───────────────────────────────────────────────────────────────────
def run_specs(n_train: int = 40, n_held: int = 8, seed0: int = 1000) -> List[Dict[str, Any]]:
    rng = np.random.default_rng(seed0)
    specs = []
    for k in range(n_train + n_held):
        held = k >= n_train
        pool = HELD_OUT_EVENTS if held else TRAIN_EVENTS
        n_ev = int(rng.integers(2, 5))
        events = [pool[int(rng.integers(0, len(pool)))] for _ in range(n_ev)]
        if held:
            extra = [TRAIN_EVENTS[int(rng.integers(0, len(TRAIN_EVENTS)))]]
            events = events + extra
        specs.append({
            "runId": k + 1,
            "split": "heldout_scenario" if held else "train_run",
            "config": {
                "numRacks": int(rng.choice([6, 8, 8, 10, 12])),
                "scale": str(rng.choice(["small", "medium", "medium", "large"])),
                "climate": CLIMATE_IDS[k % len(CLIMATE_IDS)],
                "events": events,
                "durationS": RUN_DURATION_S,
                "seed": int(seed0 + 17 * k),
                "workloadLevel": float(rng.uniform(0.85, 1.25)),
            },
            "policy": POLICIES[k % len(POLICIES)],
            "disturbances": _random_commands(rng, RUN_DURATION_S),
        })
    return specs


def _random_commands(rng, duration: int) -> List[Dict[str, Any]]:
    cmds = []
    for _ in range(int(rng.integers(2, 6))):
        t = int(rng.uniform(600, duration - 900))
        rid = int(rng.integers(1, 7))
        kind = int(rng.integers(0, 3))
        if kind == 0:
            cmd = {"type": "rack", "rackId": rid, "util": float(rng.uniform(80, 100))}
        elif kind == 1:
            cmd = {"type": "rack", "rackId": rid, "disturbance": {"kind": "heat_pulse", "magnitude": float(rng.uniform(1, 4)),
                                                                  "durationMin": float(rng.uniform(5, 20))}}
        else:
            cmd = {"type": "rack", "rackId": rid, "disturbance": {"kind": "inlet_offset", "magnitude": float(rng.uniform(1, 4)),
                                                                  "durationMin": float(rng.uniform(5, 15))}}
        cmds.append({"t": t, "cmd": cmd, "who": "Dataset generator"})
    return sorted(cmds, key=lambda c: c["t"])


def simulate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    from simulation_engine import SimulationRun
    run = SimulationRun(spec["config"], policy=spec["policy"], forecaster=None, record=False,
                        replay_commands=spec["disturbances"])
    run.feature_log = []
    run.run_to_end()
    times = np.array([t for t, _ in run.feature_log])
    X = np.stack([x for _, x in run.feature_log])            # (T, racks, F)
    return {"spec": spec, "times": times, "X": X,
            "codes": [r["code"] for r in run.twin.racks], "events": run.schedule.to_list()}


def build_dataset(n_train: int = 40, n_held: int = 8, workers: int = 6, log=print) -> Dict[str, Any]:
    specs = run_specs(n_train, n_held)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(simulate_spec, specs))
    log(f"[dataset] simulated {len(results)} runs in {time.time() - t0:.1f} s")
    from numpy.lib.stride_tricks import sliding_window_view
    steps = {h: h * 60 // SAMPLE_S for h in HORIZONS}
    w15 = steps[15]
    Xs, Ys, Ss, meta = [], [], [], []
    for res in results:
        X, times, spec = res["X"], res["times"], res["spec"]
        T, R, F = X.shape
        cutoff = CHRONO_FRACTION * RUN_DURATION_S
        if spec["split"] == "heldout_scenario":
            split = np.array(["heldout_scenario"] * T)
        else:
            split = np.where(times < cutoff, "train", "test_chronological")
        for r in range(R):
            series = X[:, r, :]
            inlet = series[:, 0]
            Y = np.full((T, len(HORIZONS)), np.nan, dtype=np.float32)
            for k, h in enumerate(HORIZONS):
                Y[:T - steps[h], k] = inlet[steps[h]:]
            padded = np.concatenate([inlet[1:], np.full(w15, np.nan)])
            fut = np.nanmax(sliding_window_view(padded, w15)[:T], axis=1) if T > 1 else np.full(T, np.nan)
            fut[T - 1] = np.nan
            seq_src = np.concatenate([np.repeat(series[:1], SEQ_LEN - 1, axis=0), series])
            Xs.append(series)
            Ys.append(Y)
            Ss.append(sliding_window_view(seq_src, (SEQ_LEN, F))[:, 0])
            code = res["codes"][r]
            for i in range(T):
                meta.append({"runId": spec["runId"], "t": int(times[i]), "rack": code, "split": str(split[i]),
                             "climate": spec["config"]["climate"], "policy": spec["policy"],
                             "events": "+".join(sorted(set(spec["config"]["events"]))),
                             "futureMax15": float(fut[i])})
    rows_X, rows_Y, seqs = np.concatenate(Xs), np.concatenate(Ys), np.concatenate(Ss)
    ds = {"X": rows_X.astype(np.float32), "Y": rows_Y.astype(np.float32),
          "seq": seqs.astype(np.float32), "meta": meta, "runs": results, "specs": specs}
    log(f"[dataset] {len(meta)} rows")
    return ds


# ── training ──────────────────────────────────────────────────────────────────
def _masks(ds, h_idx: int):
    meta = ds["meta"]
    y = ds["Y"][:, h_idx]
    have = ~np.isnan(y)
    split = np.array([m["split"] for m in meta])
    t = np.array([m["t"] for m in meta])
    cutoff = CHRONO_FRACTION * RUN_DURATION_S
    h = HORIZONS[h_idx]
    train = have & (split == "train") & (t + h * 60 <= cutoff)
    test_c = have & (split == "test_chronological")
    test_h = have & (split == "heldout_scenario")
    return train, test_c, test_h


def _metrics(y_true, y_pred, y_persist) -> Dict[str, float]:
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    p_rmse = float(np.sqrt(np.mean((y_persist - y_true) ** 2)))
    p_mae = float(np.mean(np.abs(y_persist - y_true)))
    abs_err = np.abs(err)
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4),
            "within05Pct": round(100.0 * float(np.mean(abs_err <= 0.5)), 2),
            "within1Pct": round(100.0 * float(np.mean(abs_err <= 1.0)), 2),
            "skillRmse": round(1.0 - rmse / p_rmse, 4) if p_rmse > 0 else None,
            "skillMae": round(1.0 - mae / p_mae, 4) if p_mae > 0 else None,
            "n": int(len(y_true))}


def train_all(ds: Dict[str, Any], log=print) -> Dict[str, Any]:
    import joblib
    import xgboost as xgb
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    MODELS_DIR.mkdir(exist_ok=True)
    X, Y = ds["X"], ds["Y"]
    cur = X[:, 0]
    preds = {m: {} for m in ["persistence", "linear", "rf", "xgboost", "gru"]}
    models = {"linear": {}, "rf": {}, "xgboost": {}}
    importances = {"rf": np.zeros(X.shape[1]), "xgboost": np.zeros(X.shape[1])}
    timing = {}
    for k, h in enumerate(HORIZONS):
        tr, _, _ = _masks(ds, k)
        target = Y[tr, k] - cur[tr]
        t0 = time.time()
        lin = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X[tr], target)
        timing.setdefault("linear", 0.0)
        timing["linear"] += time.time() - t0
        t0 = time.time()
        rf = RandomForestRegressor(n_estimators=60, max_depth=14, min_samples_leaf=5, max_samples=0.5,
                                   n_jobs=-1, random_state=42).fit(X[tr], target)
        timing.setdefault("rf", 0.0)
        timing["rf"] += time.time() - t0
        t0 = time.time()
        xg = xgb.XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.9, tree_method="hist", random_state=42, n_jobs=4,
                              verbosity=0).fit(X[tr], target)
        timing.setdefault("xgboost", 0.0)
        timing["xgboost"] += time.time() - t0
        models["linear"][h], models["rf"][h], models["xgboost"][h] = lin, rf, xg
        importances["rf"] += rf.feature_importances_
        importances["xgboost"] += xg.feature_importances_
        log(f"[train] horizon {h} min: {int(tr.sum())} training rows")
        for mid, mdl in (("linear", lin), ("rf", rf), ("xgboost", xg)):
            preds[mid][h] = cur + mdl.predict(X)
        preds["persistence"][h] = cur.copy()
    for mid in ("linear", "rf", "xgboost"):
        for est in models[mid].values():
            if hasattr(est, "n_jobs"):
                est.n_jobs = 1
        joblib.dump(models[mid], MODELS_DIR / f"{mid}.joblib", compress=3)

    gru_status = "unavailable: PyTorch is not installed"
    if TORCH_OK:
        t0 = time.time()
        gru_pred, gru_status = _train_gru(ds, log)
        timing["gru"] = time.time() - t0
        if gru_pred is not None:
            for k, h in enumerate(HORIZONS):
                preds["gru"][h] = cur + gru_pred[:, k]
    if not preds["gru"]:
        preds.pop("gru")
    imp_norm = {mid: importances[mid] / max(1e-9, importances[mid].sum()) for mid in ("rf", "xgboost")}
    return compute_metrics(ds, preds, timing, imp_norm, gru_status)


def compute_metrics(ds: Dict[str, Any], preds: Dict[str, Dict[int, np.ndarray]], timing: Dict[str, float],
                    importances: Dict[str, np.ndarray], gru_status: str = "trained") -> Dict[str, Any]:
    """Score every model on the chronological and held-out-scenario test sets and write metrics.json."""
    X, Y = ds["X"], ds["Y"]
    cur = X[:, 0]
    out_models = {}
    for mid, by_h in preds.items():
        row = {"id": mid, **MODEL_INFO[mid], "chronological": {}, "heldoutScenario": {},
               "trainSeconds": round(timing.get(mid, 0.0), 1)}
        for k, h in enumerate(HORIZONS):
            _, tc, th = _masks(ds, k)
            row["chronological"][str(h)] = _metrics(Y[tc, k], by_h[h][tc], cur[tc])
            row["heldoutScenario"][str(h)] = _metrics(Y[th, k], by_h[h][th], cur[th])
        row["hotspot"] = {
            "chronological": _hotspot_metrics(ds, by_h, "test_chronological"),
            "heldoutScenario": _hotspot_metrics(ds, by_h, "heldout_scenario"),
        }
        out_models[mid] = row
    if "gru" not in out_models:
        out_models["gru"] = {"id": "gru", **MODEL_INFO["gru"], "unavailable": gru_status}
    for mid in ("rf", "xgboost"):
        if mid not in importances or mid not in out_models:
            continue
        imp = importances[mid]
        out_models[mid]["featureImportance"] = sorted(
            [{"feature": FEATURE_NAMES[i], "label": FEATURES[i][1], "importance": round(float(imp[i]), 4)}
             for i in range(len(FEATURE_NAMES))], key=lambda d: -d["importance"])
    split = [m["split"] for m in ds["meta"]]
    metrics = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "horizonsMin": HORIZONS, "limitC": LIMIT,
        "rows": {"total": len(split), "train": split.count("train"),
                 "testChronological": split.count("test_chronological"),
                 "heldoutScenario": split.count("heldout_scenario")},
        "heldOutEvents": HELD_OUT_EVENTS,
        "models": out_models,
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def _train_gru(ds, log):
    torch.manual_seed(42)
    X = ds["seq"]
    Y = ds["Y"]
    cur = ds["X"][:, 0]
    split = np.array([m["split"] for m in ds["meta"]])
    t = np.array([m["t"] for m in ds["meta"]])
    cutoff = CHRONO_FRACTION * RUN_DURATION_S
    tr = (split == "train") & (t + max(HORIZONS) * 60 <= cutoff) & ~np.isnan(Y).any(axis=1)
    mean = X[tr].reshape(-1, X.shape[2]).mean(axis=0)
    std = X[tr].reshape(-1, X.shape[2]).std(axis=0) + 1e-6
    Xn = ((X - mean) / std).astype(np.float32)
    target = (Y - cur[:, None]).astype(np.float32)
    model = GRUForecaster(X.shape[2], len(HORIZONS), 48)
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    xt = torch.from_numpy(Xn[tr])
    yt = torch.from_numpy(target[tr])
    n = len(xt)
    for epoch in range(20):
        perm = torch.randperm(n)
        total = 0.0
        for b in range(0, n, 512):
            idx = perm[b:b + 512]
            opt.zero_grad()
            loss = nn.functional.smooth_l1_loss(model(xt[idx]), yt[idx])
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
        log(f"[gru] epoch {epoch + 1}: loss {total / n:.4f}")
    model.eval()
    with torch.no_grad():
        pred = np.concatenate([model(torch.from_numpy(Xn[b:b + 4096])).numpy() for b in range(0, len(Xn), 4096)])
    torch.save({"state": model.state_dict(), "hidden": 48, "mean": mean.tolist(), "std": std.tolist()},
               MODELS_DIR / "gru.pt")
    return pred, "trained"


def _hotspot_metrics(ds, by_h, split_name: str) -> Dict[str, Any]:
    """Early-warning skill. Only rows where the rack is not already above the limit count.
    Warning = any forecast up to 15 min above the limit.
    Truth = the actual inlet goes above the limit at some point in the next 15 minutes."""
    meta = ds["meta"]
    X = ds["X"]
    idx = [i for i, m in enumerate(meta) if m["split"] == split_name and not math.isnan(m["futureMax15"])]
    if not idx:
        return {}
    idx = np.array(idx)
    cur = X[idx, 0]
    fc = np.stack([by_h[h][idx] for h in HORIZONS if h <= P.ALERT_HORIZON_MIN], axis=1)
    pred_all = (fc > LIMIT).any(axis=1)
    truth_all = np.array([meta[i]["futureMax15"] > LIMIT for i in idx])
    below = cur <= LIMIT
    pred, truth = pred_all & below, truth_all & below
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    tn = int((~pred & ~truth & below).sum())
    accuracy = (tp + tn) / int(below.sum()) if int(below.sum()) else None
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    # warning lead time per over-limit episode
    leads = []
    missed = 0
    by_series: Dict[tuple, List[int]] = {}
    for j, i in enumerate(idx):
        by_series.setdefault((meta[i]["runId"], meta[i]["rack"]), []).append(j)
    for key, js in by_series.items():
        js.sort(key=lambda j: meta[idx[j]]["t"])
        prev_above = False
        for pos, j in enumerate(js):
            above = cur[j] > LIMIT
            if above and not prev_above:
                onset = meta[idx[j]]["t"]
                k = pos - 1
                first = None
                while k >= 0 and pred_all[js[k]] and onset - meta[idx[js[k]]]["t"] <= 1800:
                    first = meta[idx[js[k]]]["t"]
                    k -= 1
                if first is None:
                    missed += 1
                else:
                    leads.append((onset - first) / 60.0)
            prev_above = above
    return {"precision": None if precision is None else round(precision, 4),
            "rowsEvaluated": int(below.sum()),
            "accuracyPct": None if accuracy is None else round(100.0 * accuracy, 2),
            "recall": None if recall is None else round(recall, 4),
            "f1": None if f1 is None else round(f1, 4),
            "positives": int(truth.sum()), "rows": int(len(idx)),
            "falseAlarms": fp, "missed": fn,
            "episodes": len(leads) + missed, "episodesWarned": len(leads),
            "meanLeadMin": round(float(np.mean(leads)), 2) if leads else None,
            "medianLeadMin": round(float(np.median(leads)), 2) if leads else None}


# ── dataset export ────────────────────────────────────────────────────────────
DATASET_COLUMNS = (
    [("run_id", "Simulation run number"), ("split", "train, test_chronological or heldout_scenario"),
     ("climate", "Climate profile of the run"), ("policy", "Cooling control policy used"),
     ("events", "Events scheduled in the run"), ("time_s", "Simulated time (s)"), ("rack", "Rack code")]
    + [(name, label) for name, label in FEATURES]
    + [(f"inlet_t+{h}min", f"Actual inlet temperature {h} minutes later (C), target") for h in HORIZONS]
)


def export_dataset(ds: Dict[str, Any]) -> Dict[str, Any]:
    import csv
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "dataset.csv"
    X, Y, meta = ds["X"], ds["Y"], ds["meta"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c for c, _ in DATASET_COLUMNS])
        for i, m in enumerate(meta):
            w.writerow([m["runId"], m["split"], m["climate"], m["policy"], m["events"], m["t"], m["rack"]]
                       + [f"{v:.7g}" for v in X[i]] + ["" if math.isnan(v) else f"{v:.7g}" for v in Y[i]])
    stats = []
    for j, (name, label) in enumerate(FEATURES):
        col = X[:, j]
        stats.append({"column": name, "mean": round(float(col.mean()), 3), "std": round(float(col.std()), 3),
                      "min": round(float(col.min()), 3), "max": round(float(col.max()), 3)})
    preview = []
    for i in range(0, min(len(meta), 4000), 200):
        m = meta[i]
        preview.append({"run_id": m["runId"], "split": m["split"], "climate": m["climate"], "time_s": m["t"],
                        "rack": m["rack"], **{FEATURE_NAMES[j]: round(float(X[i, j]), 3) for j in range(6)},
                        **{f"inlet_t+{h}min": (None if math.isnan(Y[i, k]) else round(float(Y[i, k]), 2))
                           for k, h in enumerate(HORIZONS)}})
    runs = []
    for res in ds["runs"]:
        s = res["spec"]
        runs.append({"runId": s["runId"], "split": s["split"], "climate": s["config"]["climate"],
                     "policy": s["policy"], "racks": s["config"]["numRacks"], "scale": s["config"]["scale"],
                     "seed": s["config"]["seed"], "events": [e["name"] for e in res["events"]],
                     "operatorDisturbances": len(s["disturbances"])})
    split = [m["split"] for m in meta]
    hot_rows = int(sum(1 for i in range(len(meta)) if X[i, 0] > LIMIT))
    summary = {
        "rows": len(meta), "columns": [{"name": c, "description": d} for c, d in DATASET_COLUMNS],
        "runs": runs, "runCount": len(runs), "runDurationS": RUN_DURATION_S, "samplingIntervalS": SAMPLE_S,
        "simulatedHours": round(len(runs) * RUN_DURATION_S / 3600.0, 1),
        "split": {"train": split.count("train"), "testChronological": split.count("test_chronological"),
                  "heldoutScenario": split.count("heldout_scenario"), "chronoFraction": CHRONO_FRACTION},
        "heldOutEvents": HELD_OUT_EVENTS, "rowsAboveLimit": hot_rows,
        "stats": stats, "preview": preview, "fileBytes": path.stat().st_size,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (DATA_DIR / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# ── re-evaluation from the saved dataset and models ─────────────────────────
def load_dataset_csv(path: Path = None) -> Dict[str, Any]:
    """Rebuild the in-memory dataset (features, targets, sequences, split) from dataset.csv."""
    import csv
    path = path or DATA_DIR / "dataset.csv"
    n_f = len(FEATURE_NAMES)
    rows = []
    with path.open(encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        f0 = header.index(FEATURE_NAMES[0])
        y0 = header.index(f"inlet_t+{HORIZONS[0]}min")
        for row in r:
            rows.append(row)
    meta, Xl, Yl = [], [], []
    for row in rows:
        meta.append({"runId": int(row[0]), "split": row[1], "climate": row[2], "policy": row[3], "events": row[4],
                     "t": int(row[5]), "rack": row[6]})
        Xl.append([float(v) for v in row[f0:f0 + n_f]])
        Yl.append([float(v) if v != "" else math.nan for v in row[y0:y0 + len(HORIZONS)]])
    X = np.array(Xl, dtype=np.float32)
    Y = np.array(Yl, dtype=np.float32)
    seq = np.zeros((len(meta), SEQ_LEN, n_f), dtype=np.float32)
    groups: Dict[tuple, List[int]] = {}
    for i, m in enumerate(meta):
        groups.setdefault((m["runId"], m["rack"]), []).append(i)
    w15 = 15 * 60 // SAMPLE_S
    for idx in groups.values():
        idx.sort(key=lambda i: meta[i]["t"])
        series = X[idx]
        inlet = series[:, 0]
        for pos, i in enumerate(idx):
            lo = max(0, pos - SEQ_LEN + 1)
            s = series[lo:pos + 1]
            if len(s) < SEQ_LEN:
                s = np.concatenate([np.repeat(s[:1], SEQ_LEN - len(s), axis=0), s])
            seq[i] = s
            fut = inlet[pos + 1:pos + 1 + w15]
            meta[i]["futureMax15"] = float(fut.max()) if len(fut) else math.nan
    return {"X": X, "Y": Y, "seq": seq, "meta": meta}


def predict_saved(ds: Dict[str, Any]) -> Dict[str, Any]:
    """Predictions of every saved model for every dataset row (absolute inlet temperature)."""
    import joblib
    X = ds["X"]
    cur = X[:, 0]
    preds = {"persistence": {h: cur.copy() for h in HORIZONS}}
    importances = {}
    for mid in ("linear", "rf", "xgboost"):
        path = MODELS_DIR / f"{mid}.joblib"
        if not path.exists():
            continue
        models = joblib.load(path)
        preds[mid] = {}
        imp = np.zeros(X.shape[1])
        for h in HORIZONS:
            est = models[h]
            if hasattr(est, "n_jobs"):
                est.n_jobs = -1
            preds[mid][h] = cur + est.predict(X)
            if hasattr(est, "feature_importances_"):
                imp += est.feature_importances_
        if imp.sum() > 0:
            importances[mid] = imp / imp.sum()
    gru_status = "unavailable: model file not found"
    if TORCH_OK and (MODELS_DIR / "gru.pt").exists():
        from forecasting_engine import GRUWrapper
        g = GRUWrapper(MODELS_DIR / "gru.pt")
        out = np.concatenate([g.predict(ds["seq"][b:b + 8192]) for b in range(0, len(cur), 8192)])
        preds["gru"] = {h: cur + out[:, k] for k, h in enumerate(HORIZONS)}
        gru_status = "trained"
    return {"preds": preds, "importances": importances, "gruStatus": gru_status}
