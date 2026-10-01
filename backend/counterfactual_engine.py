"""
Counterfactual What-If Simulator Engine.
Provides interactive forward counterfactual simulation allowing operators
to adjust workload, cooling setpoints, airflow, ambient conditions, and active racks,
then simulates the exact physics trajectory to compare BEFORE vs AFTER metrics.
"""

from typing import Dict, Any, Optional
import copy


class CounterfactualWhatIfEngine:
    def __init__(self):
        pass

    def run_what_if_simulation(
        self,
        base_twin,
        workload_pct: Optional[float] = None,
        power_multiplier: Optional[float] = 1.0,
        cooling_setpoint: Optional[float] = None,
        airflow_cfm: Optional[float] = None,
        ambient_temp: Optional[float] = None,
        active_racks_count: Optional[int] = None,
        simulation_horizon_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Simulates two parallel branches:
          Branch 1 (BEFORE): Current base_twin running unadjusted for horizon
          Branch 2 (AFTER): Cloned twin with operator's counterfactual what-if parameters
        """
        dt_sec = 60.0
        steps = max(5, simulation_horizon_minutes)

        # ── 1. Simulate BEFORE Branch ──────────────────────────────────────────
        twin_before = base_twin.clone()
        before_cooling_kwh = 0.0
        before_it_kwh = 0.0
        before_peak_temp = max(r["temp"] for r in twin_before.racks)
        before_violations = 0
        before_history = []

        for _ in range(steps):
            snap = twin_before.step(dt=dt_sec)
            before_it_kwh += snap["totalITPower"] * (dt_sec / 3600.0)
            before_cooling_kwh += snap["coolingPower"] * (dt_sec / 3600.0)
            before_peak_temp = max(before_peak_temp, snap["maxTemp"])
            if snap["maxTemp"] > twin_before.safety_threshold_temp:
                before_violations += 1
            before_history.append(snap["maxTemp"])

        before_total_kwh = before_it_kwh + before_cooling_kwh
        before_risk = (
            min(100, int((before_peak_temp - 30.0) * 16)) if before_peak_temp > 30.0 else 0
        )

        # ── 2. Apply What-If parameters to AFTER Branch ────────────────────────
        twin_after = base_twin.clone()

        if ambient_temp is not None:
            twin_after.ambient_temp = float(ambient_temp)
        if cooling_setpoint is not None:
            twin_after.cooling_supply_temp = float(cooling_setpoint)
        if airflow_cfm is not None:
            twin_after.crah_airflow_cfm = float(airflow_cfm)

        # Workload & Active Racks adjustments
        total_racks = len(twin_after.racks)
        active_limit = active_racks_count if active_racks_count and 1 <= active_racks_count <= total_racks else total_racks

        for i, rack in enumerate(twin_after.racks):
            if i >= active_limit:
                # Standby / sleep rack
                rack["cpuLoad"] = 5
                rack["gpuLoad"] = 0
                rack["fanSpeed"] = 30
            else:
                if workload_pct is not None:
                    rack["cpuLoad"] = max(10, min(100, int(workload_pct)))
                if power_multiplier and power_multiplier > 0:
                    rack["servers"] = max(4, round(rack["servers"] * power_multiplier))

        # Simulate AFTER Branch
        after_cooling_kwh = 0.0
        after_it_kwh = 0.0
        after_peak_temp = max(r["temp"] for r in twin_after.racks)
        after_violations = 0
        after_history = []

        for _ in range(steps):
            snap = twin_after.step(dt=dt_sec)
            after_it_kwh += snap["totalITPower"] * (dt_sec / 3600.0)
            after_cooling_kwh += snap["coolingPower"] * (dt_sec / 3600.0)
            after_peak_temp = max(after_peak_temp, snap["maxTemp"])
            if snap["maxTemp"] > twin_after.safety_threshold_temp:
                after_violations += 1
            after_history.append(snap["maxTemp"])

        after_total_kwh = after_it_kwh + after_cooling_kwh
        after_risk = (
            min(100, int((after_peak_temp - 30.0) * 16)) if after_peak_temp > 30.0 else 0
        )

        # ── 3. Calculate Comparative Deltas ────────────────────────────────────
        energy_saved_kwh = round(before_total_kwh - after_total_kwh, 3)
        cooling_energy_saved_kwh = round(before_cooling_kwh - after_cooling_kwh, 3)
        energy_savings_pct = (
            round((energy_saved_kwh / before_total_kwh) * 100.0, 1) if before_total_kwh > 0 else 0.0
        )
        temp_reduction_c = round(before_peak_temp - after_peak_temp, 2)
        violations_avoided = max(0, before_violations - after_violations)

        return {
            "horizonMinutes": simulation_horizon_minutes,
            "inputsApplied": {
                "workloadPct": workload_pct,
                "powerMultiplier": power_multiplier,
                "coolingSetpoint": cooling_setpoint,
                "airflowCFM": airflow_cfm,
                "ambientTemp": ambient_temp,
                "activeRacks": active_limit,
            },
            "before": {
                "peakTemp": round(before_peak_temp, 2),
                "coolingEnergyKWh": round(before_cooling_kwh, 3),
                "totalEnergyKWh": round(before_total_kwh, 3),
                "thermalRiskPercent": before_risk,
                "thermalViolations": before_violations,
                "pue": round(before_total_kwh / before_it_kwh, 3) if before_it_kwh > 0 else 1.0,
                "tempTrajectory": before_history,
            },
            "after": {
                "peakTemp": round(after_peak_temp, 2),
                "coolingEnergyKWh": round(after_cooling_kwh, 3),
                "totalEnergyKWh": round(after_total_kwh, 3),
                "thermalRiskPercent": after_risk,
                "thermalViolations": after_violations,
                "pue": round(after_total_kwh / after_it_kwh, 3) if after_it_kwh > 0 else 1.0,
                "tempTrajectory": after_history,
            },
            "deltas": {
                "energySavedKWh": energy_saved_kwh,
                "coolingEnergySavedKWh": cooling_energy_saved_kwh,
                "energySavingsPercent": energy_savings_pct,
                "temperatureReductionC": temp_reduction_c,
                "thermalViolationsAvoided": violations_avoided,
            },
        }
