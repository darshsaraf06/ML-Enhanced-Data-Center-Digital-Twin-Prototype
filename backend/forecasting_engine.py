"""
Rack inlet temperature forecasting.

Training and live inference share one feature definition (FeatureTracker), so the
model sees exactly the same inputs in the live twin as in the dataset it was
trained on. The target is the change in rack INLET temperature over each horizon
(+5, +10, +15, +30, +60 min). Every selectable model has its own trained model per
horizon; the persistence baseline (future = current) needs no training.

Hotspot probability for a rack = max over horizons up to 15 min of
    Phi((forecast - limit) / RMSE_h)
where RMSE_h is the model's measured error on the chronological test set.
"""

import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

import model_params as P

MODELS_DIR = Path(__file__).parent / "models"
HORIZONS = P.FORECAST_HORIZONS_MIN
SEQ_LEN = 10           # GRU looks at the last 10 samples (5 minutes at 30 s spacing)

FEATURES = [
    ("inlet", "Current inlet temperature (C)"),
    ("d_inlet_60", "Inlet change over the last 60 s (K)"),
    ("d_inlet_300", "Inlet change over the last 5 min (K)"),
    ("exhaust", "Current exhaust temperature (C)"),
    ("util", "Rack utilization (%)"),
    ("d_util_300", "Utilization change over the last 5 min (points)"),
    ("power_frac", "Rack power as a share of its maximum"),
    ("power_kw", "Rack power (kW)"),
    ("airflow_ratio", "CRAH airflow divided by server airflow demand"),
    ("recirc", "Recirculation share at the rack inlet"),
    ("supply", "Supply air temperature (C)"),
    ("setpoint", "Supply air setpoint (C)"),
    ("d_supply_300", "Supply air change over the last 5 min (K)"),
    ("capacity_margin", "Spare cooling capacity as a share of design IT power"),
    ("outside", "Outside dry-bulb temperature (C)"),
    ("wet_bulb", "Outside wet-bulb temperature (C)"),
    ("zone_b", "Rack is in zone B (1) or A (0)"),
    ("row_end", "Rack is at the end of a row (1) or not (0)"),
    ("crah_fraction", "CRAH airflow command (share of design)"),
    ("inlet_gap", "Steady-state inlet the air is mixing toward, minus current inlet (K)"),
    ("supply_rate", "Current rate of change of supply air (K per minute)"),
    ("supply_over_setpoint", "Supply air minus setpoint (K)"),
    ("exhaust_rise", "Exhaust minus inlet temperature (K)"),
    ("chiller_status", "Chiller availability reported by the plant (0 to 1)"),
    ("crah_status", "CRAH airflow availability reported by the units (0 to 1)"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]

MODEL_INFO = {
    "persistence": {"name": "Persistence baseline", "description": "Assumes the temperature stays as it is now. The reference every model must beat."},
    "linear": {"name": "Linear regression", "description": "Ridge-regularised linear model on standardised features, one per horizon."},
    "rf": {"name": "Random forest", "description": "Ensemble of 60 decision trees (depth 14), one forest per horizon."},
    "xgboost": {"name": "XGBoost", "description": "Gradient boosted trees (300 rounds, depth 6), one model per horizon."},
    "gru": {"name": "GRU neural network", "description": "Recurrent network (PyTorch, CPU) reading the last 5 minutes of features and predicting all horizons at once."},
}
MODEL_ORDER = ["persistence", "linear", "rf", "xgboost", "gru"]


class FeatureTracker:
    """Keeps the short history needed to build features for every rack."""

    def __init__(self, n_racks: int):
        self.n = n_racks
        self.buf = [deque(maxlen=31) for _ in range(n_racks)]       # (inlet, util) every 10 s
        self.supply_buf = deque(maxlen=31)
        self.seq = [deque(maxlen=SEQ_LEN) for _ in range(n_racks)]  # feature vectors every 30 s

    def sample(self, twin):
        """Call every 10 simulated seconds."""
        for i, r in enumerate(twin.racks):
            self.buf[i].append((r["inletTemp"], r["util"]))
        self.supply_buf.append(twin.supply_temp)

    def _lag(self, buf, steps: int, idx: int):
        if not buf:
            return None
        k = max(0, len(buf) - 1 - steps)
        return buf[k][idx] if isinstance(buf[k], tuple) else buf[k]

    def features(self, twin) -> np.ndarray:
        o = twin.out
        margin = (o.get("capacityKw", 0.0) - o.get("loadKw", 0.0)) / max(1e-6, twin.design_it_kw)
        rows = []
        for i, r in enumerate(twin.racks):
            b = self.buf[i]
            inlet, util = r["inletTemp"], r["util"]
            in60 = self._lag(b, 6, 0)
            in300 = self._lag(b, 30, 0)
            u300 = self._lag(b, 30, 1)
            s300 = self._lag(self.supply_buf, 30, 0)
            rows.append([
                inlet,
                inlet - (in60 if in60 is not None else inlet),
                inlet - (in300 if in300 is not None else inlet),
                r["exhaustTemp"],
                util,
                util - (u300 if u300 is not None else util),
                r["powerKw"] / max(1e-6, r["pmaxKw"]),
                r["powerKw"],
                o.get("airflowRatio", 1.0),
                r["recirc"],
                twin.supply_temp,
                twin.supply_setpoint,
                twin.supply_temp - (s300 if s300 is not None else twin.supply_temp),
                margin,
                twin.outside_temp,
                twin.wet_bulb,
                1.0 if r["zone"] == "B" else 0.0,
                1.0 if r["rowPosition"] in (0, r["rowLength"] - 1) else 0.0,
                twin.crah_fraction,
                r.get("inletTarget", inlet) - inlet,
                o.get("supplyRateKPerMin", 0.0),
                twin.supply_temp - twin.supply_setpoint,
                r["exhaustTemp"] - inlet,
                o.get("chillerAvail", 1.0) * o.get("plantAvail", 1.0),
                o.get("crahAvail", 1.0),
            ])
        X = np.array(rows, dtype=np.float32)
        for i in range(self.n):
            self.seq[i].append(X[i])
        return X

    def sequences(self) -> np.ndarray:
        out = []
        for i in range(self.n):
            s = list(self.seq[i])
            while len(s) < SEQ_LEN:
                s.insert(0, s[0])
            out.append(np.stack(s))
        return np.stack(out).astype(np.float32)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class GRUWrapper:
    """Thin wrapper so the GRU can be loaded lazily and used like the other models."""

    def __init__(self, path: Path):
        import torch
        from ml_training import GRUForecaster
        blob = torch.load(path, map_location="cpu", weights_only=False)
        self.model = GRUForecaster(len(FEATURE_NAMES), len(HORIZONS), blob["hidden"])
        self.model.load_state_dict(blob["state"])
        self.model.eval()
        self.mean = np.array(blob["mean"], dtype=np.float32)
        self.std = np.array(blob["std"], dtype=np.float32)
        self.torch = torch

    def predict(self, seq: np.ndarray) -> np.ndarray:
        x = (seq - self.mean) / self.std
        with self.torch.no_grad():
            return self.model(self.torch.from_numpy(x)).numpy()


class Forecaster:
    """Loads trained models and produces per-rack inlet forecasts."""

    _cache: Dict[str, Any] = {}

    def __init__(self, model_id: str = "xgboost"):
        self.metrics = load_metrics()
        available = self.available_models()
        self.model_id = model_id if model_id in available else ("xgboost" if "xgboost" in available else "persistence")
        self.model = self._load(self.model_id)

    @staticmethod
    def available_models() -> List[str]:
        out = ["persistence"]
        for mid in ["linear", "rf", "xgboost"]:
            if (MODELS_DIR / f"{mid}.joblib").exists():
                out.append(mid)
        if (MODELS_DIR / "gru.pt").exists():
            try:
                import torch  # noqa: F401
                out.append("gru")
            except Exception:
                pass
        return [m for m in MODEL_ORDER if m in out]

    @classmethod
    def _load(cls, model_id: str):
        if model_id == "persistence":
            return None
        if model_id in cls._cache:
            return cls._cache[model_id]
        if model_id == "gru":
            obj = GRUWrapper(MODELS_DIR / "gru.pt")
        else:
            import joblib
            obj = joblib.load(MODELS_DIR / f"{model_id}.joblib")
            for est in obj.values():
                if hasattr(est, "n_jobs"):
                    est.n_jobs = 1
                if hasattr(est, "steps"):
                    pass
        cls._cache[model_id] = obj
        return obj

    def rmse(self, horizon: int) -> float:
        m = self.metrics.get("models", {}).get(self.model_id, {})
        row = m.get("chronological", {}).get(str(horizon))
        if row and row.get("rmse"):
            return max(0.05, float(row["rmse"]))
        return 0.5

    def predict(self, X: np.ndarray, seq: Optional[np.ndarray] = None) -> np.ndarray:
        """Return absolute inlet forecasts, shape (racks, horizons)."""
        current = X[:, 0:1]
        if self.model_id == "persistence":
            return np.repeat(current, len(HORIZONS), axis=1)
        if self.model_id == "gru":
            delta = self.model.predict(seq)
        else:
            delta = np.stack([self.model[h].predict(X) for h in HORIZONS], axis=1)
        return current + delta

    def risk(self, forecasts: np.ndarray, limit: float) -> List[float]:
        probs = []
        for row in forecasts:
            p = 0.0
            for k, h in enumerate(HORIZONS):
                if h > P.ALERT_HORIZON_MIN:
                    break
                p = max(p, _phi((row[k] - limit) / self.rmse(h)))
            probs.append(p * 100.0)
        return probs


def load_metrics() -> Dict[str, Any]:
    path = MODELS_DIR / "metrics.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


class LiveAccuracy:
    """Compares forecasts with what actually happened later in the same run."""

    def __init__(self, n_racks: int):
        self.pending: Dict[int, List[tuple]] = {}
        self.errors: Dict[int, List[float]] = {h: [] for h in HORIZONS}
        self.recent5: deque = deque(maxlen=20 * n_racks)   # last 20 checks of the 5 minute forecast

    def add(self, t: int, forecasts: np.ndarray):
        for k, h in enumerate(HORIZONS):
            target_t = t + h * 60
            self.pending.setdefault(target_t, []).append((k, forecasts[:, k].copy()))

    def resolve(self, t: int, actual: np.ndarray):
        items = self.pending.pop(t, None)
        if not items:
            return
        for k, pred in items:
            err = np.abs(pred - actual)
            h = HORIZONS[k]
            self.errors[h].extend(float(e) for e in err)
            if h == 5:
                self.recent5.extend(float(e) for e in err)

    def rolling_mae(self) -> Optional[float]:
        return round(float(np.mean(self.recent5)), 3) if self.recent5 else None

    def rolling_within1(self) -> Optional[float]:
        """Share (%) of recent 5 minute forecasts that landed within 1 C of what happened."""
        if not self.recent5:
            return None
        return round(100.0 * float(np.mean(np.array(self.recent5) <= 1.0)), 1)

    def summary(self) -> Dict[str, Any]:
        out = {}
        for h in HORIZONS:
            e = self.errors[h]
            arr = np.array(e)
            out[str(h)] = {"mae": round(float(np.mean(arr)), 3) if e else None,
                           "rmse": round(float(np.sqrt(np.mean(np.square(arr)))), 3) if e else None,
                           "within05Pct": round(100.0 * float(np.mean(arr <= 0.5)), 1) if e else None,
                           "within1Pct": round(100.0 * float(np.mean(arr <= 1.0)), 1) if e else None,
                           "count": len(e)}
        return out
