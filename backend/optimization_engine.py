"""
Counterfactual decision engine.

Each candidate action is applied to a cloned twin and simulated 30 minutes ahead
with the conditions that are active now (workload, events, weather held constant:
the twin does not know the future). For every branch we record the peak rack inlet
temperature, facility energy and the workload disruption it causes.

    safe      = peak inlet over the horizon <= inlet limit
    cost J    = w_energy * energy change vs no action (%)
              + w_temperature * 10 * max(0, peak - (limit - margin))
              + w_disruption * disruption
    disruption: 0.05 per utilization point migrated, 2 per kW of power capped.
The recommended action is the safe action with the lowest J. If no action is safe,
the action with the lowest peak is recommended and marked as the best available.

The predictive tuner (every 5 minutes) uses the same clones to pick the supply-air
setpoint and CRAH airflow with the lowest facility energy whose forecast peak inlet
stays at least 2.0 K below the limit.
"""

from typing import Any, Dict, List, Optional

import model_params as P

ACTIONS: Dict[str, Dict[str, str]] = {
    "none": {"title": "No action", "description": "Keep current cooling and workload settings."},
    "airflow_boost": {"title": "Boost CRAH airflow", "description": "Raise CRAH airflow by 20 percentage points of design (cube-law fan energy)."},
    "setpoint_drop": {"title": "Lower supply air setpoint", "description": "Lower the supply-air setpoint by 2 C (chiller works harder, lower COP)."},
    "workload_migration": {"title": "Migrate workload", "description": "Move up to 25 utilization points from the hottest rack to the coolest racks with headroom."},
    "power_cap": {"title": "Cap rack power", "description": "Cap the hottest rack at 85 % of its current power for 15 minutes."},
    "combined": {"title": "Combined response", "description": "Airflow +10 points, setpoint -1 C and migrate 15 utilization points."},
}
ACTION_ORDER = ["none", "airflow_boost", "setpoint_drop", "workload_migration", "power_cap", "combined"]
POWER_CAP_DURATION_S = 900


def plan_action(action_id: str, twin, hot_code: str, protected_ids: set) -> Dict[str, Any]:
    plan: Dict[str, Any] = {"actionId": action_id, "setpoint": None, "crah": None, "migrations": [], "cap": None}
    sp, cr = twin.supply_setpoint, twin.crah_fraction
    if action_id == "airflow_boost":
        plan["crah"] = min(P.CRAH_FRACTION_MAX, cr + 0.2)
    elif action_id == "setpoint_drop":
        plan["setpoint"] = max(P.SETPOINT_MIN_C, sp - 2.0)
    elif action_id == "combined":
        plan["crah"] = min(P.CRAH_FRACTION_MAX, cr + 0.1)
        plan["setpoint"] = max(P.SETPOINT_MIN_C, sp - 1.0)
    if action_id in ("workload_migration", "combined"):
        plan["migrations"] = _plan_migration(twin, hot_code, protected_ids, 25.0 if action_id == "workload_migration" else 15.0)
    if action_id == "power_cap":
        hot = next((r for r in twin.racks if r["code"] == hot_code), None)
        if hot is not None and hot["powerKw"] > 0:
            plan["cap"] = (hot["id"], round(hot["powerKw"] * 0.85, 3))
    return plan


def _plan_migration(twin, hot_code: str, protected_ids: set, points: float) -> List[tuple]:
    hot = next((r for r in twin.racks if r["code"] == hot_code), None)
    if hot is None or hot["id"] in protected_ids:
        return []
    movable = min(points, max(0.0, hot["util"] - 10.0))
    if movable <= 0:
        return []
    targets = sorted((r for r in twin.racks if r["id"] != hot["id"] and r["id"] not in protected_ids and not r["off"]),
                     key=lambda r: r["inletTemp"])
    moves = []
    for r in targets[:3]:
        room = max(0.0, 85.0 - r["util"])
        take = min(room, movable)
        if take >= 1.0:
            moves.append((hot["id"], r["id"], round(take, 2)))
            movable -= take
        if movable < 1.0:
            break
    return moves


def apply_plan_to_twin(twin, plan: Dict[str, Any]):
    """Apply a plan directly to a twin (used for cloned branches with frozen workload)."""
    if plan.get("setpoint") is not None:
        twin.supply_setpoint = plan["setpoint"]
    if plan.get("crah") is not None:
        twin.crah_fraction = plan["crah"]
    by_id = {r["id"]: r for r in twin.racks}
    for src, dst, pts in plan.get("migrations", []):
        by_id[src]["util"] = max(0.0, by_id[src]["util"] - pts)
        by_id[dst]["util"] = min(100.0, by_id[dst]["util"] + pts)
    if plan.get("cap"):
        rid, cap = plan["cap"]
        by_id[rid]["powerCapKw"] = cap


def disruption_score(twin, plan: Dict[str, Any]) -> float:
    score = 0.05 * sum(p for _, _, p in plan.get("migrations", []))
    if plan.get("cap"):
        rid, cap = plan["cap"]
        rack = next(r for r in twin.racks if r["id"] == rid)
        score += 2.0 * max(0.0, rack["powerKw"] - cap)
    return round(score, 3)


def simulate_branch(twin, plan: Optional[Dict[str, Any]], horizon_s: float = P.BRANCH_HORIZON_S,
                    dt: float = P.BRANCH_DT_S) -> Dict[str, Any]:
    clone = twin.clone()
    if plan:
        apply_plan_to_twin(clone, plan)
    limit = clone.inlet_limit
    peak = clone.max_inlet()
    kwh = cool_kwh = 0.0
    secs_above = 0.0
    trajectory = []
    steps = int(horizon_s / dt)
    for k in range(steps):
        out = clone.step(dt)
        kwh += out["facilityKw"] * dt / 3600.0
        cool_kwh += out["coolingKw"] * dt / 3600.0
        m = out["maxInlet"]
        peak = max(peak, m)
        if m > limit:
            secs_above += dt
        if k % 12 == 11:
            trajectory.append(round(m, 2))
    return {"peakInlet": round(peak, 2), "energyKwh": round(kwh, 3), "coolingKwh": round(cool_kwh, 3),
            "minutesAboveLimit": round(secs_above / 60.0, 1), "trajectory": trajectory}


def score_branch(result: Dict[str, Any], baseline_kwh: float, limit: float, weights: Dict[str, float],
                 disruption: float) -> Dict[str, Any]:
    energy_pct = (result["energyKwh"] - baseline_kwh) / baseline_kwh * 100.0 if baseline_kwh > 0 else 0.0
    temp_term = 10.0 * max(0.0, result["peakInlet"] - (limit - P.PREDICTIVE_SAFETY_MARGIN_K))
    j = (weights.get("energy", 1.0) * energy_pct + weights.get("temperature", 1.0) * temp_term
         + weights.get("disruption", 1.0) * disruption)
    return {**result, "energyChangePercent": round(energy_pct, 2), "disruption": disruption,
            "safe": bool(result["peakInlet"] <= limit), "costScore": round(float(j), 3)}


def choose_recommended(candidates: List[Dict[str, Any]]) -> Optional[str]:
    done = [c for c in candidates if c.get("result")]
    if not done:
        return None
    safe = [c for c in done if c["result"]["safe"]]
    if safe:
        return min(safe, key=lambda c: (c["result"]["costScore"], ACTION_ORDER.index(c["actionId"])))["actionId"]
    return min(done, key=lambda c: (c["result"]["peakInlet"], ACTION_ORDER.index(c["actionId"])))["actionId"]


def explain_choice(candidates: List[Dict[str, Any]], chosen: str) -> str:
    done = {c["actionId"]: c["result"] for c in candidates if c.get("result")}
    if chosen not in done:
        return "Chosen before the evaluation finished."
    r = done[chosen]
    safe = [a for a, v in done.items() if v["safe"]]
    title = ACTIONS[chosen]["title"]
    if not r["safe"]:
        return (f"No option kept the inlet below the limit within 30 minutes. {title} gave the lowest forecast peak "
                f"({r['peakInlet']:.1f} C).")
    others = [a for a in safe if a != chosen]
    text = (f"{title} keeps the forecast peak at {r['peakInlet']:.1f} C (safe) with an energy change of "
            f"{r['energyChangePercent']:+.1f} % and the lowest cost score ({r['costScore']:.2f})")
    if others:
        best_other = min(others, key=lambda a: done[a]["costScore"])
        text += f"; the next best safe option, {ACTIONS[best_other]['title']}, scored {done[best_other]['costScore']:.2f}"
    unsafe = [ACTIONS[a]["title"] for a, v in done.items() if not v["safe"]]
    if unsafe:
        text += f". Unsafe options: {', '.join(unsafe)}"
    return text + "."


def tune_cooling(twin, limit: float) -> Dict[str, Any]:
    """Pick setpoint and CRAH airflow with the lowest energy that keeps a 2.0 K margin."""
    sp0, cr0 = twin.supply_setpoint, twin.crah_fraction
    best = None
    fallback = None
    for dsp in (-1.0, 0.0, 0.5, 1.0):
        sp = min(P.SETPOINT_MAX_C, max(P.SETPOINT_MIN_C, sp0 + dsp))
        for dcr in (-0.05, 0.0, 0.05):
            cr = min(P.CRAH_FRACTION_MAX, max(P.CRAH_FRACTION_MIN, cr0 + dcr))
            res = simulate_branch(twin, {"setpoint": sp, "crah": cr, "migrations": [], "cap": None},
                                  horizon_s=P.TUNER_HORIZON_S, dt=P.BRANCH_DT_S)
            cand = (sp, cr, res)
            if res["peakInlet"] <= limit - P.PREDICTIVE_SAFETY_MARGIN_K:
                if best is None or res["energyKwh"] < best[2]["energyKwh"] - 1e-9:
                    best = cand
            if fallback is None or res["peakInlet"] < fallback[2]["peakInlet"] - 1e-9:
                fallback = cand
    sp, cr, res = best if best is not None else fallback
    return {"setpoint": round(sp, 2), "crah": round(cr, 3), "peakInlet": res["peakInlet"],
            "energyKwh": res["energyKwh"], "withinMargin": best is not None}
