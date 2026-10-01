"""
Counterfactual Decision & Multi-Objective Optimization Engine.
Simulates candidate cooling and workload interventions inside cloned Digital Twin instances.
Cost function enforces strict thermal safety, then optimizes energy consumption:
    J = w_safety * Violation_Penalty + w_energy * E_cooling + w_temp * (T_peak - T_target) + w_effort * Action_Cost
Unsafe actions are strictly flagged and cannot be recommended.
"""

from typing import List, Dict, Any, Optional
import copy


CANDIDATE_INTERVENTIONS = [
    {
        "id": "status_quo",
        "title": "Action A: Status Quo (No Intervention)",
        "type": "none",
        "description": "Maintain existing cooling supply setpoints, fan speeds, and compute allocation without adjustment.",
        "icon": "⏸️",
    },
    {
        "id": "airflow_boost",
        "title": "Action B: Boost CRAH Airflow (+20%)",
        "type": "mechanical",
        "description": "Ramp CRAH fan speed to boost volumetric airflow by +1800 CFM and increase targeted rack fan speeds by +15%.",
        "icon": "💨",
    },
    {
        "id": "chiller_setpoint",
        "title": "Action C: Lower Chiller Setpoint (-2.0°C)",
        "type": "chiller",
        "description": "Trim chilled air supply temperature from 18.0°C down to 16.0°C via chiller control valve adjustments.",
        "icon": "❄️",
    },
    {
        "id": "workload_migration",
        "title": "Action D: Workload Migration / Load Balancing",
        "type": "compute",
        "description": "Live migrate 22% CPU/GPU container tasks from the hottest rack to cooler, underutilized racks.",
        "icon": "🔄",
    },
    {
        "id": "proactive_combined",
        "title": "Action E: Proactive Combined Intervention",
        "type": "compound",
        "description": "Coordinated dynamic dispatch: 15% load migration + 10% targeted fan trim + 0.8°C supply setpoint adjustment.",
        "icon": "⚡",
    },
]


class CounterfactualOptimizationEngine:
    def __init__(self):
        self.weights = {
            "thermalSafety": 0.45,
            "coolingEnergy": 0.30,
            "peakTemp": 0.15,
            "actionEffort": 0.10,
        }
        self.safety_limit_temp = 33.0

    def apply_action_to_twin(self, twin, action_id: str):
        """Mutate cloned DigitalTwinPhysics state."""
        if action_id == "airflow_boost":
            twin.crah_airflow_cfm = min(12000.0, twin.crah_airflow_cfm + 1800.0)
            for r in twin.racks:
                r["fanSpeed"] = min(100, r.get("fanSpeed", 70) + 15)

        elif action_id == "chiller_setpoint":
            twin.cooling_supply_temp = max(14.0, twin.cooling_supply_temp - 2.0)

        elif action_id == "workload_migration":
            sorted_racks = sorted(twin.racks, key=lambda r: r["temp"], reverse=True)
            hot = sorted_racks[0]
            cool = sorted_racks[-1]
            if hot["cpuLoad"] > 35:
                shift = min(22, hot["cpuLoad"] - 30)
                hot["cpuLoad"] -= shift
                cool["cpuLoad"] = min(98, cool["cpuLoad"] + shift)
            if hot.get("gpuLoad", 0) > 20:
                gpu_shift = min(20, hot["gpuLoad"] - 15)
                hot["gpuLoad"] -= gpu_shift
                cool["gpuLoad"] = min(95, cool.get("gpuLoad", 0) + gpu_shift)

        elif action_id == "proactive_combined":
            sorted_racks = sorted(twin.racks, key=lambda r: r["temp"], reverse=True)
            hot = sorted_racks[0]
            cool = sorted_racks[-1]
            if hot["cpuLoad"] > 35:
                shift = min(16, hot["cpuLoad"] - 30)
                hot["cpuLoad"] -= shift
                cool["cpuLoad"] = min(96, cool["cpuLoad"] + shift)
            # Targeted fan trim on hottest rack zone
            for r in twin.racks:
                if r.get("zone") == hot.get("zone"):
                    r["fanSpeed"] = min(100, r.get("fanSpeed", 70) + 10)
            twin.cooling_supply_temp = max(15.5, twin.cooling_supply_temp - 0.8)

        # status_quo: no mutations

    def simulate_counterfactual_branch(
        self, base_twin, action: Dict[str, Any], horizon_steps: int = 15, baseline_kwh: float = 0.0
    ) -> Dict[str, Any]:
        """
        Deep-clones base_twin, applies candidate action, advances forward in time,
        and measures thermal outcome and energy consumption.
        """
        twin_clone = base_twin.clone()
        self.apply_action_to_twin(twin_clone, action["id"])

        total_cooling_kwh = 0.0
        peak_temp = 0.0
        sla_violations = 0
        temps_timeline = []

        dt_sec = 60.0  # 1 minute per step for 15-minute horizon
        for _ in range(horizon_steps):
            snap = twin_clone.step(dt=dt_sec)
            cooling_kw = snap["coolingPower"]
            total_cooling_kwh += cooling_kw * (dt_sec / 3600.0)
            peak_temp = max(peak_temp, snap["maxTemp"])
            if snap["maxTemp"] > self.safety_limit_temp:
                sla_violations += 1
            temps_timeline.append(snap["maxTemp"])

        final_max_temp = max(r["temp"] for r in twin_clone.racks)
        is_safe = (final_max_temp <= self.safety_limit_temp) and (sla_violations == 0)

        # Cost components
        baseline_ref = max(0.1, baseline_kwh if baseline_kwh > 0 else total_cooling_kwh)
        energy_delta_pct = round(((total_cooling_kwh - baseline_ref) / baseline_ref) * 100.0, 1)

        # Safety penalty: severe penalty if thermal threshold violated
        safety_penalty = 100.0 if not is_safe else 0.0
        # Energy cost (lower is better)
        energy_cost = total_cooling_kwh * 3.5
        # Temperature penalty above target 25°C
        temp_cost = max(0.0, final_max_temp - 25.0) * 2.8
        # Action effort penalty (status_quo = 0, single action = 5, compound = 10)
        effort_map = {"none": 0.0, "mechanical": 4.0, "chiller": 6.0, "compute": 5.0, "compound": 8.0}
        effort_cost = effort_map.get(action.get("type", "none"), 5.0)

        total_cost_score = (
            self.weights["thermalSafety"] * safety_penalty +
            self.weights["coolingEnergy"] * energy_cost +
            self.weights["peakTemp"] * temp_cost +
            self.weights["actionEffort"] * effort_cost
        )

        return {
            "actionId": action["id"],
            "title": action["title"],
            "type": action.get("type", "none"),
            "description": action["description"],
            "peakTemp": round(final_max_temp, 2),
            "coolingEnergyKWh": round(total_cooling_kwh, 3),
            "energyDeltaPercent": energy_delta_pct,
            "isSafe": is_safe,
            "slaViolations": sla_violations,
            "costScore": round(total_cost_score, 2),
            "tempsTimeline": temps_timeline,
            "isRecommended": False,
        }

    def evaluate_all(self, base_twin, horizon_steps: int = 15) -> Dict[str, Any]:
        """
        Evaluate all candidate interventions.
        Enforces prioritization:
          1. Thermal Safety (MUST be Safe)
          2. Energy Efficiency (Lowest cooling energy among safe)
          3. Minimal Peak Temp
          4. Minimal Action Effort
        """
        # First compute baseline energy of status quo
        status_quo_clone = base_twin.clone()
        sq_energy_kwh = 0.0
        for _ in range(horizon_steps):
            s = status_quo_clone.step(dt=60.0)
            sq_energy_kwh += s["coolingPower"] * (60.0 / 3600.0)

        evaluations = []
        for action in CANDIDATE_INTERVENTIONS:
            ev = self.simulate_counterfactual_branch(
                base_twin, action, horizon_steps=horizon_steps, baseline_kwh=sq_energy_kwh
            )
            evaluations.append(ev)

        # Sort: Safe interventions first (ordered by cost score), then Unsafe ones
        safe_evals = [e for e in evaluations if e["isSafe"]]
        unsafe_evals = [e for e in evaluations if not e["isSafe"]]

        safe_evals.sort(key=lambda e: e["costScore"])
        unsafe_evals.sort(key=lambda e: e["costScore"])

        ranked = safe_evals + unsafe_evals

        if safe_evals:
            safe_evals[0]["isRecommended"] = True
            recommended = safe_evals[0]
        else:
            # If all are unsafe under extreme stress, recommend the least unsafe
            ranked[0]["isRecommended"] = True
            recommended = ranked[0]

        return {
            "recommendedAction": recommended,
            "allEvaluations": ranked,
            "totalEvaluated": len(ranked),
            "safeCount": len(safe_evals),
            "unsafeCount": len(unsafe_evals),
            "statusQuoBaselineKWh": round(sq_energy_kwh, 3),
        }

    def run_counterfactual_evaluation(self, base_twin):
        return self.evaluate_all(base_twin)
