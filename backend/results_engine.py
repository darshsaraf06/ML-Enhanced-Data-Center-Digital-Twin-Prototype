"""
Results for a finished run.

Everything shown on the Results page and in the PDF, CSV and JSON exports is
assembled here from the run itself and from replays of the same scenario (same
config, seed, events and operator commands) under other policies:

  baselines  fixed cooling and reactive threshold cooling (conventional control)
  solutions  the project policy with a single response applied at every hotspot
             alert (no action, airflow boost, setpoint drop, migration, power cap,
             combined) and with the recommended response (automatic).
"""

import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Dict, List, Optional

import model_params as P
from alert_engine import fmt_time
from forecasting_engine import HORIZONS, MODEL_INFO, load_metrics
from optimization_engine import ACTIONS

COMPARE_METRICS = [
    ("totalKwh", "Total energy", "kWh"), ("coolingKwh", "Cooling energy", "kWh"), ("pue", "PUE", ""),
    ("waterL", "Water", "L"), ("wueLPerKwh", "WUE", "L/kWh"), ("carbonKg", "Carbon", "kg CO2"),
    ("costInr", "Cost", "INR"), ("minutesAboveLimit", "Minutes above limit", "min"),
    ("hotspotEvents", "Hotspot events", ""), ("peakInlet", "Peak inlet", "C"),
]

SOLUTION_VARIANTS = [
    ("none", "No action at alerts"),
    ("airflow_boost", "Always boost airflow"),
    ("setpoint_drop", "Always lower setpoint"),
    ("workload_migration", "Always migrate workload"),
    ("power_cap", "Always cap rack power"),
    ("combined", "Always combined response"),
    (None, "Recommended policy (automatic)"),
]


# ── Explanations shown with every number on the Results page and in every export ──
EXPLANATIONS: Dict[str, Any] = {
    "sections": {
        "summary": "A plain-language account of the run: how hot the warmest rack got, whether any rack went above the limit, how many hotspot alerts were raised and who chose the responses, and what the run cost in energy, water, carbon and money. Every figure is measured in this run.",
        "timeline": "The warmest rack inlet temperature at each moment. Inlet temperature is the air entering the servers, which is what the ASHRAE limit applies to. The same scenario was re-run with fixed and reactive cooling so the three lines can be compared directly. Shaded bands are time above the limit; vertical markers are events, alerts, solutions and operator actions.",
        "workload": "Utilization is how busy each rack is (0 to 100 %). More utilization means more electrical power and therefore more heat. Shaded bands mark periods when the average across racks was above the threshold, when cooling has to work hardest.",
        "resources": "Energy, water, carbon and cost for the whole run, integrated every simulated second, and the same quantities for the two conventional baselines run on the same seed, weather, workload, events and operator changes. Differences are this run minus the baseline: negative means this run used less.",
        "decisions": "Each hotspot alert lists every option the optimizer simulated in a cloned copy of the twin 30 minutes ahead (with current conditions held constant), whether it kept the racks within the limit, what it would cost, which option was recommended, which was chosen, by whom, and why.",
        "solutions": "The whole scenario re-run from the start, each time answering every hotspot alert in one fixed way. This shows the effect of each kind of response over the full run rather than at one moment. The row called Your run is the run exactly as it happened, including your choices.",
        "racks": "Per-rack statistics over the run. Inlet is the air entering the rack (the limit applies to it); exhaust is the hot air leaving the back of the rack.",
        "ml": "How well the forecasting model predicted rack inlet temperatures. This run compares each forecast with what actually happened later in the same run. Offline scores come from the test sets: the last 35 % of each training simulation (chronological) and whole simulations with events never seen in training (held-out).",
        "events": "Everything that happened, structured by severity and category. Events of the same kind within 30 seconds are grouped into one entry.",
    },
    "metrics": {
        "itKwh": "IT energy: electricity used by the servers, integrated over the run (kWh).",
        "chillerKwh": "Chiller energy: compressor electricity to remove heat from the chilled water. Depends on the heat load and the chiller COP (kWh).",
        "fansKwh": "Fan energy: CRAH fans that blow cold air into the aisle plus cooling-tower fans. CRAH fan power rises with the cube of airflow (kWh).",
        "pumpsKwh": "Pump energy: chilled-water and condenser-water pumps (kWh).",
        "coolingKwh": "Cooling energy: chiller + fans + pumps (kWh).",
        "totalKwh": "Total facility energy: IT energy + cooling energy (kWh). The electricity bill and the carbon figure are based on it.",
        "pue": "Power Usage Effectiveness = total facility energy / IT energy. 1.0 would mean no cooling overhead at all; lower is better.",
        "heatRejectedKwh": "Heat sent to the cooling tower: heat removed from the room plus the compressor heat of the chiller (kWh).",
        "waterL": "Cooling-tower water: evaporation (heat rejected x evaporative share / 2430 kJ per kg) plus blowdown (evaporation / 3), in litres.",
        "wueLPerKwh": "Water Usage Effectiveness = litres of water / kWh of IT energy. Lower is better.",
        "carbonKg": "Carbon emissions = total energy x grid emission factor (kg CO2). The default factor is the India grid average.",
        "costInr": "Cost = total energy x electricity price + water (in 1000 L) x water price, in Indian rupees.",
        "costEnergyInr": "Electricity part of the cost (INR).",
        "costWaterInr": "Water part of the cost (INR).",
        "minutesAboveLimit": "Minutes during which at least one rack inlet was above the limit.",
        "hotspotEvents": "Number of separate times a rack crossed above the limit (each crossing counts once until the rack cools back down).",
        "peakInlet": "The highest rack inlet temperature reached at any moment (C).",
        "difference": "This run minus the baseline, in the unit of the metric. Negative means this run used less or was cooler.",
        "percent": "Difference as a percentage of the baseline value.",
    },
    "baselines": {
        "fixed": "Fixed cooling: supply air held at 18 C and CRAH airflow at 100 % all the time, a common conservative way to run a data hall.",
        "reactive": "Reactive threshold cooling: 21 C supply and 85 % airflow, boosted to 17 C and 110 % once any inlet is within 1 C of the limit, and released after 5 minutes at least 3 C below it. It reacts to measurements only.",
        "predictive": "This project: ML forecasts every 30 s, hotspot alerts evaluated in cloned twins, and a tuner that every 5 minutes picks the lowest-energy setpoint and airflow that keeps the forecast peak 2 C below the limit.",
    },
    "decisionColumns": {
        "safe": "Safe means the forecast peak inlet of the option over the next 30 minutes stays at or below the limit. Unsafe options cannot be applied by the operator when a safe option exists.",
        "peakInlet": "Highest rack inlet the cloned twin reached in the 30 minutes after applying the option (C).",
        "energyChangePercent": "Facility energy over those 30 minutes compared with doing nothing (%). Negative saves energy.",
        "disruption": "Impact on IT work: 0.05 per utilization point moved between racks plus 2 per kW of rack power capped. Cooling-only options have zero disruption.",
        "costScore": "w_energy x energy change % + w_temperature x 10 x (how far the peak is above limit - 2 C) + w_disruption x disruption. The lowest score among safe options is recommended.",
        "recommended": "The safe option with the lowest cost score. If no option is safe, the option with the lowest peak is recommended as the best available.",
        "chooser": "Who chose: Operator (you), Automatic (timeout) after 30 s without a choice, Automatic (Skip to End), Automatic (quiet period) for a new risk within 10 minutes of an alert (handled without a pop-up), or Operator (snoozed), which means the alert was dismissed with no action.",
    },
    "actions": {
        "none": "Keep everything as it is.",
        "airflow_boost": "Raise CRAH airflow by 20 percentage points of design. Reduces recirculation of hot air but fan power rises with the cube of airflow.",
        "setpoint_drop": "Lower the supply-air setpoint by 2 C. Every rack gets colder air, but the chiller works harder at a lower COP.",
        "workload_migration": "Move up to 25 utilization points from the hottest rack to the coolest racks with headroom (racks you set manually are never touched).",
        "power_cap": "Cap the hottest rack at 85 % of its current power for 15 minutes, directly cutting its heat at the cost of slower IT work.",
        "combined": "Airflow +10 points, setpoint -1 C and migrate 15 utilization points.",
    },
    "rackColumns": {
        "peakInlet": "Highest inlet temperature of this rack (C).",
        "avgInlet": "Time-averaged inlet temperature (C).",
        "peakExhaust": "Highest exhaust (outlet) temperature (C). Normally 10 to 13 C above inlet.",
        "avgUtil": "Time-averaged utilization (%).",
        "energyKwh": "Electricity used by the servers of this rack (kWh).",
        "minutesAboveLimit": "Minutes the inlet of this rack was above the limit.",
        "hotspotEvents": "Separate times this rack crossed above the limit.",
    },
    "mlColumns": {
        "mae": "Mean absolute error: the average size of the forecast miss, in C. Lower is better.",
        "rmse": "Root mean squared error: like MAE but large misses count more (C). Used for the error band and the hotspot probability.",
        "r2": "Share of variation explained (1 is perfect). Looks high for slowly changing temperatures even for weak models, so read it together with skill.",
        "skillRmse": "Skill = 1 - (model RMSE / persistence RMSE). Persistence means assuming the temperature stays as it is. Above 0 the model beats doing nothing; below 0 it is worse.",
        "within1Pct": "Accuracy: share of forecasts that landed within 1 C of the actual inlet temperature (%).",
        "within05Pct": "Strict accuracy: share of forecasts within 0.5 C of the actual value (%).",
        "heldoutMae": "MAE on simulations containing events the model never saw in training (flood, cyclone): a test of generalisation.",
        "accuracyPct": "Hotspot warning accuracy: share of moments (rack not yet over the limit) where the warn or no-warn call was right. High mainly because most moments are calm; precision and recall are the stricter measures.",
        "precision": "Of the warnings raised, the share followed by a real limit crossing within 15 minutes.",
        "recall": "Of the real limit crossings, the share that had been warned about up to 15 minutes before.",
        "f1": "Balance of precision and recall (harmonic mean).",
        "leadTime": "Minutes between the first warning and the actual limit crossing.",
    },
    "severities": {
        "Info": "Normal operation and actions: run started, tuner changes, events ending, operator changes.",
        "Warning": "Needs attention: a rack forecast or measured above the recommended limit, or a disturbance event.",
        "Critical": "Serious: a rack above the allowable limit, an alert while a rack is already over, or a major failure event.",
    },
    "categories": {
        "Thermal": "Measured rack inlet crossing the limit or recovering.",
        "Forecast": "Early warnings and hotspot alerts from the ML forecast.",
        "Cooling": "Cooling equipment events (chiller trip, fan degradation, containment breach).",
        "Power": "Power events (utility loss, earthquake shutdown).",
        "Workload": "Workload events (spikes, overloads).",
        "Environment": "Weather and site events (heatwave, flood, smoke, cyclone).",
        "Decision": "Actions taken by the twin: tuner adjustments, reactive boosts, applied solutions.",
        "User action": "Changes you made: rack settings, environment, pause, snooze, skip.",
        "System": "Run start and end.",
    },
}


def replay_job(job: Dict[str, Any]) -> Dict[str, Any]:
    from forecasting_engine import Forecaster
    from simulation_engine import SimulationRun
    fc = Forecaster(job["model"]) if job["policy"] == "predictive" else None
    run = SimulationRun(job["config"], policy=job["policy"], forecaster=fc, interactive=False,
                        decision_choice=job["choice"], replay_commands=job["commands"], record=True)
    run.run_to_end(stop_at=job["stopAt"])
    return {"key": job["key"], "summary": run.meter.summary(),
            "maxInlet": [[p["t"], p["maxInlet"]] for p in run.series][::6],
            "decisions": len(run.decisions)}


def run_replays(run, progress: Callable[[float, str], None]) -> Dict[str, Any]:
    model = run.forecaster.model_id if run.forecaster else "persistence"
    base = {"config": run.config, "commands": run.commands, "stopAt": run.t, "model": model}
    jobs = [{**base, "key": "fixed", "policy": "fixed", "choice": None},
            {**base, "key": "reactive", "policy": "reactive", "choice": None}]
    for choice, _ in SOLUTION_VARIANTS:
        jobs.append({**base, "key": f"solution:{choice or 'recommended'}", "policy": "predictive", "choice": choice})
    out: Dict[str, Any] = {}
    done = 0
    try:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for res in ex.map(replay_job, jobs):
                out[res["key"]] = res
                done += 1
                progress(done / len(jobs), res["key"])
    except Exception as exc:   # fall back to sequential replays
        print(f"[results] process pool unavailable ({exc}); running replays sequentially")
        for job in jobs:
            if job["key"] in out:
                continue
            res = replay_job(job)
            out[res["key"]] = res
            done += 1
            progress(done / len(jobs), res["key"])
    return out


def _compare(project: Dict[str, Any], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for key, label, unit in COMPARE_METRICS:
        a, b = project.get(key), baseline.get(key)
        if a is None or b is None:
            continue
        diff = a - b
        pct = (diff / b * 100.0) if b not in (0, 0.0) else None
        rows.append({"metric": key, "label": label, "unit": unit, "project": a, "baseline": b,
                     "difference": round(diff, 3), "percent": None if pct is None else round(pct, 2)})
    return rows


def _intervals(points: List[tuple], cond) -> List[Dict[str, int]]:
    out, start = [], None
    for t, v in points:
        if cond(v):
            start = t if start is None else start
        elif start is not None:
            out.append({"start": start, "end": t})
            start = None
    if start is not None and points:
        out.append({"start": start, "end": points[-1][0]})
    return out


def _downsample(series: List[Dict[str, Any]], max_points: int = 720) -> List[Dict[str, Any]]:
    if len(series) <= max_points:
        return series
    step = len(series) / max_points
    return [series[int(i * step)] for i in range(max_points)]


def _summary_text(run, res: Dict[str, Any], comp_fixed: List[Dict[str, Any]], decisions: List[Dict[str, Any]]) -> str:
    limit = run.twin.inlet_limit
    peak = res["peakInlet"]
    parts = [f"Over {fmt_time(run.t)} of simulated time the hottest rack inlet reached {peak:.1f} C at {fmt_time(res['peakInletTime'])}."]
    if res["minutesAboveLimit"] > 0:
        parts.append(f"At least one rack was above the {limit:.0f} C limit for {res['minutesAboveLimit']:.1f} minutes "
                     f"({res['hotspotEvents']} separate hotspot episodes).")
    else:
        parts.append(f"No rack inlet went above the {limit:.0f} C limit.")
    if decisions:
        who: Dict[str, int] = {}
        for d in decisions:
            who[d["chooser"] or "Unresolved"] = who.get(d["chooser"] or "Unresolved", 0) + 1
        parts.append(f"The twin raised {len(decisions)} hotspot alert(s); responses were chosen by: "
                     + ", ".join(f"{k} ({v})" for k, v in who.items()) + ".")
    else:
        parts.append("No hotspot alert was needed.")
    parts.append(f"The facility used {res['totalKwh']:.1f} kWh (PUE {res['pue']:.3f}), {res['waterL']:.0f} L of water "
                 f"and emitted {res['carbonKg']:.1f} kg CO2, costing INR {res['costInr']:.0f}.")
    e = next((r for r in comp_fixed if r["metric"] == "totalKwh"), None)
    if e and e["percent"] is not None:
        word = "less" if e["difference"] < 0 else "more"
        parts.append(f"Compared with fixed cooling on the same seed and events, that is {abs(e['difference']):.1f} kWh "
                     f"({abs(e['percent']):.1f} %) {word} energy.")
    return " ".join(parts)


def compile_results(run, replays: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    res = run.meter.summary()
    fixed = replays.get("fixed", {}).get("summary")
    reactive = replays.get("reactive", {}).get("summary")
    comp_fixed = _compare(res, fixed) if fixed else []
    comp_reactive = _compare(res, reactive) if reactive else []
    decisions = [d.to_dict() for d in run.decisions]
    for d in decisions:
        for c in d["candidates"]:
            c.pop("status", None)
    limit = run.twin.inlet_limit
    series = run.series
    max_pts = [(p["t"], p["maxInlet"]) for p in series]
    avg_util = [(p["t"], sum(p["util"]) / len(p["util"])) for p in series]
    markers = []
    for ev in run.log.events:
        if ev["category"] in ("Thermal", "Power", "Cooling", "Environment", "Workload", "Decision", "User action") \
                or ev["kind"].startswith("hotspot_alert"):
            if ev["kind"] in ("tuner", "thermal_clear"):
                continue
            markers.append({"t": ev["t"], "time": ev["time"], "category": ev["category"],
                            "severity": ev["severity"], "title": ev["title"]})
    solutions = []
    for choice, label in SOLUTION_VARIANTS:
        key = f"solution:{choice or 'recommended'}"
        if key in replays:
            s = replays[key]["summary"]
            solutions.append({"variant": choice or "recommended", "label": label,
                              "description": ACTIONS[choice]["description"] if choice else
                              "At every alert the safe action with the lowest cost score is applied.",
                              "alerts": replays[key]["decisions"], **{k: s.get(k) for k, _, _ in COMPARE_METRICS}})
    solutions.append({"variant": "your_run", "label": "Your run (choices as made)",
                      "description": "The run exactly as it happened, including operator choices.",
                      "alerts": len(run.decisions), **{k: res.get(k) for k, _, _ in COMPARE_METRICS}})
    rack_meta = {r["code"]: r for r in run.twin.rack_view()}
    racks = [{**r, "zone": rack_meta[r["code"]]["zone"], "typeLabel": rack_meta[r["code"]]["typeLabel"],
              "pmaxKw": rack_meta[r["code"]]["pmaxKw"]} for r in res["racks"]]
    metrics = load_metrics()
    model_id = run.forecaster.model_id if run.forecaster else None
    offline = []
    for mid, m in metrics.get("models", {}).items():
        if "chronological" not in m:
            offline.append({"id": mid, "name": MODEL_INFO.get(mid, {}).get("name", mid), "unavailable": m.get("unavailable")})
            continue
        offline.append({"id": mid, "name": m["name"], "active": mid == model_id,
                        "byHorizon": {str(h): {**m["chronological"][str(h)],
                                               "heldoutMae": m["heldoutScenario"][str(h)]["mae"]} for h in HORIZONS},
                        "hotspot": m.get("hotspot", {}).get("chronological", {})})
    counts = run.log.counts()
    high_threshold = 70.0
    return {
        "runId": run_id, "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": run.config, "policy": run.policy, "endReason": run.end_reason,
        "elapsedS": run.t, "elapsed": fmt_time(run.t), "durationS": run.duration,
        "inletLimit": limit,
        "summaryText": _summary_text(run, res, comp_fixed, decisions),
        "resources": res,
        "baselines": {"fixed": fixed, "reactive": reactive,
                      "fixedDescription": "Fixed cooling: supply air 18 C and 100 % CRAH airflow all the time.",
                      "reactiveDescription": "Reactive threshold cooling: 21 C and 85 % airflow, boosted to 17 C and 110 % when any inlet comes within 1 K of the limit.",
                      "fixedMaxInlet": replays.get("fixed", {}).get("maxInlet", []),
                      "reactiveMaxInlet": replays.get("reactive", {}).get("maxInlet", [])},
        "comparison": {"vsFixed": comp_fixed, "vsReactive": comp_reactive},
        "timeline": {"points": [[t, v] for t, v in max_pts][::2] if len(max_pts) > 1500 else [[t, v] for t, v in max_pts],
                     "overLimit": _intervals(max_pts, lambda v: v > limit), "markers": markers},
        "workload": {"points": [[t, round(v, 1)] for t, v in avg_util],
                     "perRack": [{"code": rack_meta[c]["code"]} for c in rack_meta],
                     "highThreshold": high_threshold,
                     "highPeriods": _intervals(avg_util, lambda v: v > high_threshold)},
        "series": _downsample(series),
        "decisions": decisions,
        "solutions": solutions,
        "racks": racks,
        "ml": {"activeModel": model_id, "activeModelName": MODEL_INFO.get(model_id, {}).get("name") if model_id else None,
               "live": run.accuracy.summary(), "offline": offline, "rows": metrics.get("rows"),
               "note": "R2 is high for slowly changing temperatures even for weak models; skill versus persistence (1 - RMSE_model / RMSE_persistence) is the fairer measure."},
        "events": {"counts": counts, "list": list(reversed(run.log.events))},
        "scheduledEvents": run.schedule.to_list(),
        "commands": run.commands,
        "explanations": EXPLANATIONS,
    }
