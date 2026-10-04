"""
Multi-seed benchmark: conventional cooling versus this project's predictive twin.

Every scenario is run for every seed under three policies with identical weather,
workload and events (same seed):
  fixed       18 C supply, 100 % CRAH airflow
  reactive    21 C / 85 %, boost to 17 C / 110 % when an inlet is within 1 K of the limit
  predictive  ML forecasts + counterfactual decisions + energy tuner (this project)

Reported per scenario and policy: mean and standard deviation of total energy, water,
carbon, cost, minutes above the limit, hotspot events and warning lead time, plus the
paired difference against each baseline. This file is the only source of
"better than conventional" statements in the application.

Warning lead time: for each episode where the hottest inlet crosses the limit, the
minutes between the earliest warning in the preceding 30 minutes and the crossing.
Predictive warnings are ML forecast warnings; reactive warnings are its boost trigger;
fixed cooling has no warning (lead time 0).
"""

import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
BENCH_PATH = DATA_DIR / "benchmark.json"

SCENARIOS = [
    {"id": "normal", "name": "Normal day", "climate": "temperate", "events": "none"},
    {"id": "heatwave", "name": "Heatwave", "climate": "temperate", "events": ["heatwave"]},
    {"id": "cooling_failure", "name": "Chiller trip", "climate": "temperate", "events": ["cooling_failure"]},
    {"id": "spike_humid", "name": "Workload spike, coastal monsoon", "climate": "coastal_monsoon", "events": ["workload_spike"]},
    {"id": "spike_extreme", "name": "Workload spike, extreme humid heat", "climate": "extreme_heat", "events": ["workload_spike"]},
]
POLICIES = ["fixed", "reactive", "predictive"]
METRICS = [("totalKwh", "Total energy", "kWh"), ("coolingKwh", "Cooling energy", "kWh"), ("pue", "PUE", ""),
           ("waterL", "Water", "L"), ("carbonKg", "Carbon", "kg CO2"), ("costInr", "Cost", "INR"),
           ("minutesAboveLimit", "Minutes above limit", "min"), ("hotspotEvents", "Hotspot events", ""),
           ("peakInlet", "Peak inlet", "C"), ("leadTimeMin", "Warning lead time", "min")]


def _lead_time(run) -> Dict[str, Any]:
    limit = run.twin.inlet_limit
    onsets, prev = [], False
    for p in run.series:
        above = p["maxInlet"] > limit
        if above and not prev:
            onsets.append(p["t"])
        prev = above
    warnings = []
    for e in run.log.events:
        if e["kind"] in ("forecast_breach", "reactive_boost") or e["kind"].startswith("hotspot_alert"):
            warnings.extend(item["t"] for item in e["items"])
    leads = []
    for onset in onsets:
        prior = [w for w in warnings if onset - 1800 <= w <= onset]
        leads.append((onset - min(prior)) / 60.0 if prior else 0.0)
    return {"episodes": len(onsets), "leadTimeMin": float(np.mean(leads)) if leads else None}


def bench_job(job: Dict[str, Any]) -> Dict[str, Any]:
    from forecasting_engine import Forecaster
    from simulation_engine import SimulationRun
    cfg = {"climate": job["climate"], "events": job["events"], "seed": job["seed"], "durationS": job["durationS"],
           "numRacks": 8, "scale": "medium", "mlModel": job["model"]}
    fc = Forecaster(job["model"]) if job["policy"] == "predictive" else None
    run = SimulationRun(cfg, policy=job["policy"], forecaster=fc, record=True)
    run.run_to_end()
    s = run.meter.summary()
    lt = _lead_time(run)
    return {"scenario": job["scenario"], "policy": job["policy"], "seed": job["seed"],
            **{k: s.get(k) for k, _, _ in METRICS if k != "leadTimeMin"},
            "leadTimeMin": lt["leadTimeMin"], "episodes": lt["episodes"], "alerts": len(run.decisions)}


def _stats(values: List[Optional[float]]) -> Dict[str, Any]:
    v = [x for x in values if x is not None]
    if not v:
        return {"mean": None, "std": None, "n": 0}
    return {"mean": round(float(np.mean(v)), 4), "std": round(float(np.std(v, ddof=1)) if len(v) > 1 else 0.0, 4), "n": len(v)}


def run_benchmark(seeds: int = 10, duration_s: int = 3600, model: str = "xgboost", workers: int = 3,
                  progress: Optional[Callable[[float], None]] = None, log=print) -> Dict[str, Any]:
    jobs = [{"scenario": sc["id"], "climate": sc["climate"], "events": sc["events"], "policy": pol,
             "seed": 100 + k, "durationS": duration_s, "model": model}
            for sc in SCENARIOS for k in range(seeds) for pol in POLICIES]
    t0 = time.time()
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(bench_job, jobs)):
            rows.append(r)
            if progress:
                progress((i + 1) / len(jobs))
    log(f"[benchmark] {len(rows)} runs in {time.time() - t0:.0f} s")
    scenarios = []
    for sc in SCENARIOS:
        by_pol = {pol: [r for r in rows if r["scenario"] == sc["id"] and r["policy"] == pol] for pol in POLICIES}
        entry = {**sc, "policies": {}, "savings": {}}
        for pol in POLICIES:
            entry["policies"][pol] = {k: _stats([r[k] for r in by_pol[pol]]) for k, _, _ in METRICS}
            entry["policies"][pol]["episodes"] = _stats([r["episodes"] for r in by_pol[pol]])
            entry["policies"][pol]["alerts"] = _stats([r["alerts"] for r in by_pol[pol]])
        for base in ("fixed", "reactive"):
            paired = {}
            for k, _, _ in METRICS:
                if k in ("leadTimeMin",):
                    continue
                diffs, pcts = [], []
                for seed in sorted({r["seed"] for r in by_pol["predictive"]}):
                    a = next(r[k] for r in by_pol["predictive"] if r["seed"] == seed)
                    b = next(r[k] for r in by_pol[base] if r["seed"] == seed)
                    if a is None or b is None:
                        continue
                    diffs.append(a - b)
                    if b:
                        pcts.append((a - b) / b * 100.0)
                paired[k] = {"difference": _stats(diffs), "percent": _stats(pcts) if pcts else {"mean": None, "std": None, "n": 0}}
            entry["savings"][base] = paired
        scenarios.append(entry)
    result = {"generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "seeds": seeds, "durationS": duration_s,
              "model": model, "policies": POLICIES, "metrics": [{"id": k, "label": l, "unit": u} for k, l, u in METRICS],
              "scenarios": scenarios, "runs": rows,
              "method": "Each scenario was simulated for every seed under all three policies with identical weather, "
                        "workload and events. Values are mean and sample standard deviation across seeds; savings are "
                        "paired differences (predictive minus baseline) for the same seed."}
    DATA_DIR.mkdir(exist_ok=True)
    BENCH_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def load_benchmark() -> Optional[Dict[str, Any]]:
    if BENCH_PATH.exists():
        try:
            return json.loads(BENCH_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
