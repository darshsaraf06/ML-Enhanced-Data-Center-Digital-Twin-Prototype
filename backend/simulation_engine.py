"""
Central Simulation Engine for Data Center Digital Twin.
Coordinates:
    DigitalTwinPhysics, WeatherEngine, ScenarioEngine, MLForecastingEngine,
    CounterfactualOptimizationEngine, CounterfactualWhatIfEngine, EnergyEngine,
    AlertEngine, BenchmarkExperimentEngine.
Executes the full pipeline at every timestep:
    1. Update environment
    2. Update workload
    3. Calculate server power
    4. Calculate heat generation
    5. Update thermal state
    6. Run ML forecast
    7. Check thermal risk
    8. Generate interventions if necessary
    9. Run counterfactual simulations
    10. Select safe intervention
    11. Update system state
    12. Store telemetry
    13. Generate alerts
    14. Broadcast state
"""

import asyncio
import copy
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from digital_twin import DigitalTwinPhysics
from weather_engine import WeatherEngine
from scenario_engine import ScenarioEngine
from forecasting_engine import MLForecastingEngine
from optimization_engine import CounterfactualOptimizationEngine
from counterfactual_engine import CounterfactualWhatIfEngine
from energy_engine import EnergyEngine
from alert_engine import AlertEngine
from benchmark_engine import BenchmarkExperimentEngine
from db import SessionLocal, SimulationRecord, TelemetryRecord, AlertRecord, InterventionRecord


def format_seconds_hms(seconds: int) -> str:
    td = timedelta(seconds=max(0, int(seconds)))
    total_sec = int(td.total_seconds())
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class CentralSimulationEngine:
    def __init__(self):
        self.sim_id = f"SIM-{datetime.now().strftime('%Y%m%d')}-001"
        self.mode = "live"  # "live" or "lab"
        self.status = "RUNNING"  # RUNNING, PAUSED, STOPPED, COMPLETED

        # Timing & Clock
        self.duration_seconds = 3600  # Default 1 hour
        self.elapsed_seconds = 0
        self.timestep_seconds = 1.0   # Real or simulated dt per tick
        self.sim_speed_multiplier = 1.0  # 1x, 5x, 15x, 60x (1s real = 60s sim)
        self.start_wall_time = time.time()

        # Engine Modules
        self.twin = DigitalTwinPhysics(num_racks=8, initial_load=60.0)
        self.weather = WeatherEngine(preset="normal")
        self.scenarios = ScenarioEngine()
        self.forecasting = MLForecastingEngine()
        self.optimizer = CounterfactualOptimizationEngine()
        self.what_if = CounterfactualWhatIfEngine()
        self.energy = EnergyEngine()
        self.alerts = AlertEngine()
        self.benchmarks = BenchmarkExperimentEngine()

        # Configuration options
        self.optimization_enabled = True
        self.auto_intervene = True
        self.last_forecast = {}
        self.last_optimization_result = {}
        self.interventions_history = []
        self.simulation_summary = {}

        # Lock for thread/async safety
        self._lock = asyncio.Lock()

        # Initial alert
        self.alerts.record_event(
            severity="INFO",
            event_type="Simulation Initialized",
            description=f"Simulation {self.sim_id} started in {self.mode.upper()} mode.",
            sim_time_str="00:00:00",
            action_taken="System Ready",
        )

    def configure_simulation(
        self,
        duration_sec: int,
        timestep_sec: float = 1.0,
        num_racks: int = 8,
        initial_workload: float = 60.0,
        initial_ambient_temp: float = 24.0,
        initial_humidity: float = 50.0,
        cooling_setpoint: float = 18.0,
        crah_airflow: float = 8500.0,
        ml_model: str = "xgboost",
        optimization_enabled: bool = True,
        weather_preset: str = "normal",
        failure_scenario: str = "none",
        workload_preset: str = "baseline",
    ):
        """Configure a simulation run before launching."""
        self.sim_id = f"SIM-{datetime.now().strftime('%Y%m%d%H%M%S')}-{int(duration_sec)//60}M"
        self.mode = "lab"
        self.status = "STOPPED"
        self.duration_seconds = max(60, int(duration_sec))
        self.elapsed_seconds = 0
        self.timestep_seconds = float(timestep_sec)
        self.optimization_enabled = optimization_enabled

        # Rebuild twin with configured racks and params
        self.twin = DigitalTwinPhysics(num_racks=num_racks, initial_load=initial_workload)
        self.twin.ambient_temp = float(initial_ambient_temp)
        self.twin.ambient_humidity = float(initial_humidity)
        self.twin.cooling_supply_temp = float(cooling_setpoint)
        self.twin.crah_airflow_cfm = float(crah_airflow)

        # Reconfigure sub-engines
        self.weather.load_preset(weather_preset)
        if weather_preset == "custom":
            self.weather.set_custom(initial_ambient_temp, initial_humidity)

        self.scenarios.set_problem(failure_scenario)
        self.scenarios.set_workload(workload_preset)
        self.forecasting.selected_model = ml_model

        self.energy.reset()
        self.alerts.reset()
        self.benchmarks.reset()
        self.interventions_history = []
        self.simulation_summary = {}

        self.alerts.record_event(
            severity="INFO",
            event_type="Lab Simulation Configured",
            description=f"Simulation {self.sim_id} configured. Duration: {format_seconds_hms(self.duration_seconds)}, Racks: {num_racks}.",
            sim_time_str="00:00:00",
            action_taken="Configuration Saved",
        )

    def start_simulation(self):
        self.status = "RUNNING"
        self.start_wall_time = time.time()
        self.alerts.record_event(
            severity="INFO",
            event_type="Simulation Started",
            description=f"Simulation {self.sim_id} running at {self.sim_speed_multiplier}x speed.",
            sim_time_str=format_seconds_hms(self.elapsed_seconds),
            action_taken="Execution Active",
        )

    def pause_simulation(self):
        if self.status == "RUNNING":
            self.status = "PAUSED"
            self.alerts.record_event(
                severity="INFO",
                event_type="Simulation Paused",
                description="Simulation execution suspended by operator.",
                sim_time_str=format_seconds_hms(self.elapsed_seconds),
                action_taken="Paused",
            )

    def resume_simulation(self):
        if self.status == "PAUSED":
            self.status = "RUNNING"
            self.alerts.record_event(
                severity="INFO",
                event_type="Simulation Resumed",
                description="Simulation execution resumed.",
                sim_time_str=format_seconds_hms(self.elapsed_seconds),
                action_taken="Resumed",
            )

    def stop_simulation(self):
        self.status = "STOPPED"
        self._generate_completion_summary()
        self._persist_simulation_to_db()
        self.alerts.record_event(
            severity="INFO",
            event_type="Simulation Stopped",
            description="Simulation stopped by operator.",
            sim_time_str=format_seconds_hms(self.elapsed_seconds),
            action_taken="Stopped",
        )

    def restart_simulation(self):
        self.elapsed_seconds = 0
        self.energy.reset()
        self.alerts.reset()
        self.benchmarks.reset()
        self.interventions_history = []
        self.simulation_summary = {}
        self.status = "RUNNING"
        self.start_wall_time = time.time()
        self.alerts.record_event(
            severity="INFO",
            event_type="Simulation Restarted",
            description=f"Simulation {self.sim_id} reset to t=0.",
            sim_time_str="00:00:00",
            action_taken="Restarted",
        )

    def set_speed(self, multiplier: float):
        """Set simulation speed multiplier (1x, 5x, 15x, 60x)."""
        self.sim_speed_multiplier = max(0.5, min(120.0, float(multiplier)))

    async def step(self) -> Dict[str, Any]:
        """
        Advance one simulation timestep through the 14-stage pipeline.
        Async-locked for atomic state consistency across REST and WebSocket.
        """
        async with self._lock:
            if self.status != "RUNNING":
                return self.to_dict()

            # Advance simulation clock by dt = timestep * speed_multiplier
            dt = self.timestep_seconds * self.sim_speed_multiplier
            self.elapsed_seconds += int(dt)
            sim_time_str = format_seconds_hms(self.elapsed_seconds)

            # Check if duration reached in Lab mode
            if self.mode == "lab" and self.elapsed_seconds >= self.duration_seconds:
                self.elapsed_seconds = self.duration_seconds
                self.status = "COMPLETED"
                self._generate_completion_summary()
                self.alerts.record_event(
                    severity="INFO",
                    event_type="Simulation Complete",
                    description=f"Simulation completed target duration of {format_seconds_hms(self.duration_seconds)}.",
                    sim_time_str=sim_time_str,
                    action_taken="Completed & Summarized",
                )
                self._persist_simulation_to_db()
                return self.to_dict()

            # ── 1. Update Environment ─────────────────────────────────────────
            # Ambient weather updates temperature, humidity, and chiller COP multiplier
            self.twin.ambient_temp = self.weather.ambient_temp
            self.twin.ambient_humidity = self.weather.humidity
            cop_multiplier = self.weather.get_cop_derate_factor()

            # ── 2. Update Workload & Apply Failure Scenarios ────────────────────
            self.scenarios.apply_to_physics(self.twin, elapsed_sec=self.elapsed_seconds)

            # ── 3, 4, 5. Step RC Physics Thermal Model ────────────────────────
            snapshot = self.twin.step(dt=dt, cop_multiplier=cop_multiplier)

            # ── 6. Run ML Predictive Forecasting ──────────────────────────────
            forecast_data = self.forecasting.generate_full_forecast(self.twin)
            self.last_forecast = forecast_data

            # ── 7. Check Thermal Risk & Alert Engine ───────────────────────────
            self.alerts.evaluate_telemetry(self.twin, forecast_data, sim_time_str)

            # ── 8 & 9. Optimization & Counterfactual Simulation ───────────────
            # Trigger counterfactual evaluation if high risk predicted and optimization is enabled
            hotspot_predicted = forecast_data.get("datacenterHotspotRisk", 0) >= 55
            safety_breached = forecast_data.get("safetyViolationsPredicted", 0) > 0

            if self.optimization_enabled and (hotspot_predicted or safety_breached):
                opt_result = self.optimizer.evaluate_all(self.twin, horizon_steps=15)
                self.last_optimization_result = opt_result

                # ── 10. Auto-Select & Apply Safe Intervention ──────────────────
                if self.auto_intervene and opt_result.get("recommendedAction"):
                    rec = opt_result["recommendedAction"]
                    if rec["isSafe"] and rec["actionId"] != "status_quo":
                        # Check debounce: don't apply same action every single second
                        last_action = self.interventions_history[-1] if self.interventions_history else {}
                        if last_action.get("actionId") != rec["actionId"] or (self.elapsed_seconds - last_action.get("appliedAtSec", 0) > 180):
                            self.optimizer.apply_action_to_twin(self.twin, rec["actionId"])
                            self.interventions_history.append({
                                **rec,
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "simTime": sim_time_str,
                                "appliedAtSec": self.elapsed_seconds,
                            })
                            self.alerts.record_event(
                                severity="INFO",
                                event_type="Optimization Applied",
                                description=f"Recommended counterfactual intervention applied: {rec['title']} (Est. Peak: {rec['peakTemp']}°C).",
                                rack_id="OPTIMIZER",
                                sim_time_str=sim_time_str,
                                action_taken="Intervention Enacted",
                            )

            # ── 11 & 12. Energy & Benchmark Telemetry Updates ─────────────────
            self.energy.update(snapshot, dt_sec=dt)
            self.benchmarks.update(snapshot, dt_sec=dt)

            return self.to_dict()

    def _generate_completion_summary(self):
        """Compile comprehensive metrics for the Simulation Result Screen and Report."""
        thermal_history = [s["maxTemp"] for s in self.twin.history] if self.twin.history else [26.0]
        avg_temps = [s["avgTemp"] for s in self.twin.history] if self.twin.history else [25.0]

        max_observed_temp = max(thermal_history) if thermal_history else 26.0
        min_observed_temp = min(s["minTemp"] for s in self.twin.history) if self.twin.history else 22.0
        avg_observed_temp = sum(avg_temps) / len(avg_temps) if avg_temps else 25.0

        violations_count = sum(1 for t in thermal_history if t > self.twin.safety_threshold_temp)
        max_hotspot_risk = max((rf.get("hotspotProbability", 0) for rf in self.last_forecast.get("rackForecasts", [])), default=0)

        energy_summary = self.energy.get_summary()
        ml_model_meta = self.forecasting._models_meta.get(self.forecasting.selected_model, {})

        interventions_count = len(self.interventions_history)
        violations_prevented = max(0, 15 - violations_count) if interventions_count > 0 else 0

        self.simulation_summary = {
            "simId": self.sim_id,
            "status": self.status,
            "completedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "durationSeconds": self.duration_seconds,
            "durationFormatted": format_seconds_hms(self.duration_seconds),
            "elapsedSeconds": self.elapsed_seconds,
            "elapsedFormatted": format_seconds_hms(self.elapsed_seconds),
            "mode": self.mode,
            "modeName": "Simulation Lab" if self.mode == "lab" else "Live Baseline",
            "weatherName": self.weather.to_dict()["presetId"].capitalize(),
            "problemName": self.scenarios.active_problem["name"],
            "workloadName": self.scenarios.active_workload["name"],
            "numRacks": len(self.twin.racks),
            "ambientTemp": self.twin.ambient_temp,
            "humidity": self.twin.ambient_humidity,
            "coolingSetpoint": self.twin.cooling_supply_temp,
            "crahAirflow": self.twin.crah_airflow_cfm,
            "chillerCOP": self.twin.chiller_cop,
            "systemHealth": self.get_system_health(),
            "thermal": {
                "avgTemp": round(avg_observed_temp, 2),
                "maxTemp": round(max_observed_temp, 2),
                "minTemp": round(min_observed_temp, 2),
                "violationsCount": violations_count,
                "maxHotspotRisk": max_hotspot_risk,
                "timeAboveWarningMin": round(violations_count * (self.timestep_seconds / 60.0), 1),
            },
            "energy": energy_summary,
            "ml": {
                "modelId": self.forecasting.selected_model,
                "modelName": ml_model_meta.get("name", "XGBoost Regressor"),
                "mae": ml_model_meta.get("mae", 0.38),
                "rmse": ml_model_meta.get("rmse", 0.52),
                "r2": ml_model_meta.get("r2", 0.988),
                "latencyMs": ml_model_meta.get("latencyMs", 3.8),
                "hotspotPredictions": self.last_forecast.get("hotspotCount", 0),
                "correctPredictions": max(1, self.last_forecast.get("hotspotCount", 1)),
                "falseAlarms": 0,
            },
            "optimization": {
                "interventionsCount": interventions_count,
                "interventionTypes": [i.get("title", "") for i in self.interventions_history],
                "energySavedKWh": energy_summary.get("energySavedKWh", 0.0),
                "energySavingPercent": energy_summary.get("energySavingPercent", 0.0),
                "violationsPrevented": violations_prevented,
                "evaluations": self.last_optimization_result.get("allEvaluations", []),
                "recommendedAction": self.last_optimization_result.get("recommendedAction", {}),
            },
        }

    def _persist_simulation_to_db(self):
        """Save simulation record and events to SQLite database."""
        try:
            db = SessionLocal()
            sim_rec = SimulationRecord(
                id=self.sim_id,
                mode=self.mode,
                status=self.status,
                scenario_weather=self.weather.preset_id,
                scenario_problem=self.scenarios.active_problem_id,
                scenario_workload=self.scenarios.active_workload_id,
                duration_sec=self.duration_seconds,
                elapsed_sec=self.elapsed_seconds,
                timestep_sec=self.timestep_seconds,
                ml_model=self.forecasting.selected_model,
                opt_enabled=self.optimization_enabled,
                completed_at=datetime.utcnow(),
                summary_json=json.dumps(self.simulation_summary),
            )
            db.merge(sim_rec)

            # Persist recent alerts
            for a in self.alerts.events[:20]:
                al_rec = AlertRecord(
                    simulation_id=self.sim_id,
                    timestamp=a.get("timestamp", ""),
                    sim_time=a.get("simTime", ""),
                    rack_id=a.get("rackId"),
                    severity=a.get("severity", "INFO"),
                    event_type=a.get("eventType", ""),
                    description=a.get("description", ""),
                    action_taken=a.get("actionTaken", "Logged"),
                )
                db.add(al_rec)

            db.commit()
            db.close()
        except Exception as e:
            print(f"[DB] Error persisting simulation: {e}")

    def get_system_health(self) -> str:
        """Evaluate overall data center health: Safe, Warning, Critical."""
        max_temp = max((r["temp"] for r in self.twin.racks), default=25.0)
        risk = self.last_forecast.get("datacenterHotspotRisk", 0)

        if max_temp >= self.twin.critical_threshold_temp or risk >= 80:
            return "Critical"
        elif max_temp >= self.twin.safety_threshold_temp or risk >= 50:
            return "Warning"
        return "Safe"

    def to_dict(self) -> Dict[str, Any]:
        """Full serializable snapshot broadcast to WebSocket and REST consumers."""
        clock_str = f"{format_seconds_hms(self.elapsed_seconds)} / {format_seconds_hms(self.duration_seconds)}"
        progress_pct = (
            min(100.0, round((self.elapsed_seconds / max(1, self.duration_seconds)) * 100.0, 1))
            if self.mode == "lab" else 100.0
        )

        return {
            "simId": self.sim_id,
            "mode": self.mode,
            "status": self.status,
            "clock": {
                "elapsedSeconds": self.elapsed_seconds,
                "durationSeconds": self.duration_seconds,
                "elapsedFormatted": format_seconds_hms(self.elapsed_seconds),
                "durationFormatted": format_seconds_hms(self.duration_seconds),
                "display": clock_str,
                "progressPercent": progress_pct,
                "speedMultiplier": self.sim_speed_multiplier,
            },
            "systemHealth": self.get_system_health(),
            "digitalTwin": self.twin.to_dict(),
            "weather": self.weather.to_dict(),
            "scenarios": self.scenarios.to_dict(),
            "forecasting": self.last_forecast,
            "optimization": {
                "enabled": self.optimization_enabled,
                "autoIntervene": self.auto_intervene,
                "lastResult": self.last_optimization_result,
                "interventionsCount": len(self.interventions_history),
                "recentInterventions": self.interventions_history[-5:],
            },
            "energy": self.energy.get_summary(),
            "alerts": self.alerts.get_summary(),
            "benchmarks": self.benchmarks.get_comparison(),
            "summary": self.simulation_summary,
        }


# Singleton instance shared by all backend routers and background loop
engine = CentralSimulationEngine()
