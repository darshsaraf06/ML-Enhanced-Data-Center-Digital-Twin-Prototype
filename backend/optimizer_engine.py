"""
Counterfactual Decision & Multi-Objective Optimization Engine.
Evaluates candidate cooling/workload interventions inside cloned physics engines.
Cost function: J = w1*E_cooling + w2*T_peak + w3*H_risk + w4*SLA_violations
"""

from typing import List
from physics_engine import ThermalPhysicsEngine


_CANDIDATE_ACTIONS = [
    {
        "id": "status_quo",
        "title": "Action A: Status Quo",
        "description": "Maintain current fixed cooling and workload settings. No changes applied.",
    },
    {
        "id": "airflow_boost",
        "title": "Action B: Boost CRAH Fans",
        "description": "Increase cooling fan speed by +15% across Zone B CRAH units.",
    },
    {
        "id": "chiller_boost",
        "title": "Action C: Lower Supply Temp",
        "description": "Reduce CRAH air supply temperature by -2.2 °C via chiller set-point change.",
    },
    {
        "id": "workload_migration",
        "title": "Action D: Workload Migration",
        "description": "Redistribute 18% CPU load from the hottest rack to the coolest available rack.",
    },
    {
        "id": "proactive_combined",
        "title": "Action E: Proactive ML Optimal",
        "description": "Dynamic load balancing + targeted fan boost + minor supply temp reduction.",
    },
]


class CounterfactualOptimizerEngine:
    def __init__(self):
        self.weights = {
            "coolingEnergy": 0.35,
            "peakTemp":      0.30,
            "hotspotRisk":   0.20,
            "slaViolations": 0.15,
        }

    # ------------------------------------------------------------------
    def _apply_action(self, clone: ThermalPhysicsEngine, action_id: str):
        """Mutate a cloned physics engine according to the candidate action."""
        if action_id == "airflow_boost":
            clone.crah_airflow_cfm += 1800
            clone.crah_fan_power_kw += 8.5
            for r in clone.racks:
                r["fanSpeed"] = min(100, r["fanSpeed"] + 15)

        elif action_id == "chiller_boost":
            clone.cooling_supply_temp = max(14.0, clone.cooling_supply_temp - 2.2)

        elif action_id == "workload_migration":
            sorted_racks = sorted(clone.racks, key=lambda r: r["temp"], reverse=True)
            hot, cool = sorted_racks[0], sorted_racks[-1]
            if hot["cpuLoad"] > 40:
                shift = min(20, hot["cpuLoad"] - 30)
                hot["cpuLoad"] -= shift
                cool["cpuLoad"] = min(100, cool["cpuLoad"] + shift)

        elif action_id == "proactive_combined":
            sorted_racks = sorted(clone.racks, key=lambda r: r["temp"], reverse=True)
            hot, cool = sorted_racks[0], sorted_racks[-1]
            if hot["cpuLoad"] > 40:
                shift = min(18, hot["cpuLoad"] - 30)
                hot["cpuLoad"] -= shift
                cool["cpuLoad"] = min(100, cool["cpuLoad"] + shift)
            for r in clone.racks:
                if r["zone"] == hot["zone"]:
                    r["fanSpeed"] = min(100, r["fanSpeed"] + 8)
            clone.cooling_supply_temp = max(16.5, clone.cooling_supply_temp - 0.8)
        # status_quo: no changes

    # ------------------------------------------------------------------
    def evaluate_action(
        self, action: dict, base_physics: ThermalPhysicsEngine, horizon_steps: int = 15, baseline_kwh: float = 0.0
    ) -> dict:
        """Clone the physics engine, apply an action, simulate N steps, compute cost."""
        twin = base_physics.clone()
        self._apply_action(twin, action["id"])

        total_cooling_kwh = 0.0
        peak_temp = 0.0
        sla_violations = 0

        for _ in range(horizon_steps):
            snap = twin.step(60.0)   # 60 s per simulated tick
            total_cooling_kwh += snap["coolingPower"] * (60.0 / 3600.0)
            peak_temp = max(peak_temp, snap["maxTemp"])
            if snap["maxTemp"] > 33.0:
                sla_violations += 1

        final_max_temp = max(r["temp"] for r in twin.racks)
        hotspot_risk = (
            min(100.0, (final_max_temp - 32.0) * 40.0)
            if final_max_temp >= 33.0
            else max(0.0, (final_max_temp - 30.0) * 15.0)
        )

        energy_cost = total_cooling_kwh * 2.5
        temp_cost   = max(0.0, final_max_temp - 25.0) * 3.0
        risk_cost   = hotspot_risk * 0.8
        sla_cost    = sla_violations * 15.0

        total_cost = (
            self.weights["coolingEnergy"] * energy_cost +
            self.weights["peakTemp"]      * temp_cost +
            self.weights["hotspotRisk"]   * risk_cost +
            self.weights["slaViolations"] * sla_cost
        )

        # baseline_kwh is passed in or computed
        baseline_kwh = baseline_kwh if baseline_kwh > 0 else max(0.1, total_cooling_kwh)
        energy_delta = round(((total_cooling_kwh - baseline_kwh) / baseline_kwh) * 100.0, 1)

        return {
            "id":               action["id"],
            "title":            action["title"],
            "description":      action["description"],
            "peakTemp":         round(final_max_temp, 1),
            "energyDeltaPercent": energy_delta,
            "hotspotRiskPercent": round(hotspot_risk),
            "slaViolationsCount": sla_violations,
            "totalCostScore":   round(total_cost, 2),
        }

    # ------------------------------------------------------------------
    def run_counterfactual_evaluation(self, base_physics: ThermalPhysicsEngine) -> dict:
        """Evaluate all candidate actions and return sorted results (lowest cost first)."""
        import time

        # Compute status_quo baseline energy first
        status_quo_eval = self.evaluate_action(_CANDIDATE_ACTIONS[0], base_physics, baseline_kwh=0.0)
        baseline_energy = 0.0
        # Re-run status_quo to get raw cooling kWh
        twin_sq = base_physics.clone()
        sq_kwh = 0.0
        for _ in range(15):
            sq_snap = twin_sq.step(60.0)
            sq_kwh += sq_snap["coolingPower"] * (60.0 / 3600.0)

        evaluations = [
            self.evaluate_action(action, base_physics, baseline_kwh=sq_kwh)
            for action in _CANDIDATE_ACTIONS
        ]
        evaluations.sort(key=lambda e: e["totalCostScore"])
        return {
            "timestamp":      time.strftime("%H:%M:%S"),
            "bestAction":     evaluations[0],
            "allEvaluations": evaluations,
            "weights":        self.weights,
        }
