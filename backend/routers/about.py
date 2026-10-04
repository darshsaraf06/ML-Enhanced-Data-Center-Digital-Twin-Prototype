"""
Catalog and About-the-project API: setup options, model metrics, dataset and benchmark.
All numbers come from files produced by scripts/train_models.py and scripts/run_benchmark.py.
"""

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

import model_params as P
from benchmark_runner import SCENARIOS, load_benchmark, run_benchmark
from forecasting_engine import FEATURES, MODEL_INFO, MODEL_ORDER, Forecaster, load_metrics
from ml_training import DATA_DIR
from optimization_engine import ACTIONS, ACTION_ORDER
from scenario_engine import DEMO_SCRIPT, EVENT_LIBRARY, event_catalog
from simulation_engine import DEFAULT_CONFIG
from weather_engine import CLIMATES

router = APIRouter(prefix="/api", tags=["about"])

_bench = {"state": "idle", "progress": 0.0, "error": None}
_bench_lock = threading.Lock()


@router.get("/catalog")
async def catalog():
    metrics = load_metrics().get("models", {})
    available = Forecaster.available_models()
    models = []
    for mid in MODEL_ORDER:
        m = metrics.get(mid, {})
        c15 = m.get("chronological", {}).get("15")
        models.append({"id": mid, **MODEL_INFO[mid], "available": mid in available,
                       "mae15": c15["mae"] if c15 else None, "acc15": c15.get("within1Pct") if c15 else None,
                       "acc5": (m.get("chronological", {}).get("5") or {}).get("within1Pct"),
                       "unavailable": m.get("unavailable")})
    return {
        "defaults": DEFAULT_CONFIG,
        "climates": list(CLIMATES.values()),
        "events": event_catalog(),
        "models": models,
        "actions": [{"id": a, **ACTIONS[a]} for a in ACTION_ORDER],
        "speeds": [1, 2, 5, 10, 25],
        "limits": {"recommended": P.RECOMMENDED_INLET_LIMIT_C, "allowable": P.ALLOWABLE_INLET_LIMIT_C},
        "demo": {"script": [{"eventId": e, "name": EVENT_LIBRARY[e]["name"], "start": s} for e, s in DEMO_SCRIPT],
                 "durationS": 3600, "seed": 7, "climate": "temperate", "numRacks": 8},
        "decisionTimeoutS": P.DECISION_TIMEOUT_S,
    }


@router.get("/about/parameters")
async def parameters():
    keys = ["RHO_CP_AIR", "RECOMMENDED_INLET_LIMIT_C", "ALLOWABLE_INLET_LIMIT_C", "SERVER_TARGET_DELTA_T",
            "RACK_THERMAL_MASS_KJ_K", "COLD_AISLE_TAU_S", "RECIRC_BASE_MIDDLE", "RECIRC_BASE_END",
            "RECIRC_STARVATION_GAIN", "CRAH_DESIGN_OVERSUPPLY", "CRAH_FAN_SFP_KW_PER_M3S", "PLANT_CAPACITY_FACTOR",
            "CAPACITY_REF_WET_BULB_C", "CAPACITY_DERATE_PER_K", "SUPPLY_THERMAL_MASS_KJ_K_PER_RACK",
            "CHILLER_CARNOT_EFFICIENCY", "CHW_APPROACH_K", "TOWER_APPROACH_K", "CONDENSER_APPROACH_K",
            "FREE_COOLING_BAND_K", "LATENT_HEAT_KJ_KG", "CYCLES_OF_CONCENTRATION",
            "DEFAULT_GRID_FACTOR_KG_PER_KWH", "DEFAULT_ELECTRICITY_INR_PER_KWH", "DEFAULT_WATER_INR_PER_KL",
            "PREDICTIVE_SAFETY_MARGIN_K", "DEFAULT_SUPPLY_SETPOINT_C", "FORECAST_INTERVAL_S", "TUNER_INTERVAL_S",
            "ALERT_HORIZON_MIN", "ALERT_COOLDOWN_S", "BRANCH_HORIZON_S"]
    return {"parameters": {k: getattr(P, k) for k in keys},
            "rackTypes": P.RACK_TYPES, "policies": {"fixed": P.FIXED_POLICY, "reactive": P.REACTIVE_POLICY},
            "events": event_catalog(), "climates": list(CLIMATES.values()),
            "features": [{"name": n, "description": d} for n, d in FEATURES]}


@router.get("/about/ml")
async def ml_metrics():
    m = load_metrics()
    if not m:
        raise HTTPException(status_code=404, detail="Models have not been trained yet. Run scripts/train_models.py.")
    return m


@router.get("/about/dataset")
async def dataset_summary():
    path = DATA_DIR / "dataset_summary.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset has not been generated yet. Run scripts/train_models.py.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/about/dataset.csv")
async def dataset_csv():
    path = DATA_DIR / "dataset.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset has not been generated yet.")
    return FileResponse(path, media_type="text/csv", filename="datacenter_twin_dataset.csv")


@router.get("/about/benchmark")
async def benchmark():
    return {"status": dict(_bench), "result": load_benchmark(), "scenarios": SCENARIOS}


@router.post("/about/benchmark/run")
async def benchmark_run(seeds: int = Query(10, ge=2, le=30)):
    with _bench_lock:
        if _bench["state"] == "running":
            raise HTTPException(status_code=409, detail="A benchmark is already running")
        _bench.update({"state": "running", "progress": 0.0, "error": None})

    def work():
        try:
            def prog(f):
                _bench["progress"] = round(f * 100, 1)
            run_benchmark(seeds=seeds, progress=prog)
            _bench.update({"state": "done", "progress": 100.0})
        except Exception as exc:
            _bench.update({"state": "error", "error": str(exc)})
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "status": dict(_bench)}
