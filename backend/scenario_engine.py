"""
Scenario Engine for Data Center Digital Twin.
Implements the 10 failure/problem scenarios, workload profiles, and arbitrary
multi-scenario combination stress testing.
"""

from typing import Dict, List, Any, Optional
import copy


FAILURE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "none": {
        "id": "none",
        "name": "Nominal Operation (No Faults)",
        "category": "nominal",
        "severity": "INFO",
        "description": "Standard balanced operation with all CRAH units and server fans running nominally.",
        "initialConditions": "Nominal load profiles, CRAH supply at 18.0°C, 8500 CFM.",
        "trigger": "Always active.",
        "expectedEffect": "Stable temperatures within ASHRAE thermal envelope (20°C - 27°C).",
        "suggestedDurationSec": 3600,
    },
    "ai_workload_spike": {
        "id": "ai_workload_spike",
        "name": "AI Workload Spike",
        "category": "workload",
        "severity": "WARNING",
        "description": "Sudden surge in LLM prompt queries and batch inference workloads concentrated on Zone B GPU clusters.",
        "initialConditions": "Zone B GPU racks 06 and 07 spike to 96% and 98% utilization.",
        "trigger": "Immediate on scenario activation.",
        "expectedEffect": "Rapid rise in rack exhaust temp (+6.5°C in ~10 mins); predictive hotspot alert triggered.",
        "suggestedDurationSec": 1800,
    },
    "gpu_training_burst": {
        "id": "gpu_training_burst",
        "name": "GPU Training Burst",
        "category": "workload",
        "severity": "CRITICAL",
        "description": "Large sustained multi-node distributed deep learning training job across all compute racks.",
        "initialConditions": "Racks 04, 05, 06, 07 all driven to 92-100% continuous CPU/GPU TDP.",
        "trigger": "Continuous heavy matrix multiplication tensor workloads.",
        "expectedEffect": "Widespread thermal stress across multiple racks simultaneously; CRAH capacity pushed to near 100%.",
        "suggestedDurationSec": 3600,
    },
    "cooling_failure": {
        "id": "cooling_failure",
        "name": "Cooling Failure (Chiller Trip)",
        "category": "cooling",
        "severity": "CRITICAL",
        "description": "Chiller loop compressor failure causing CRAH supply air temperature to rise from 18°C to 24.5°C.",
        "initialConditions": "Cooling supply air temperature climbs to 24.5°C; fan airflow drops by 35%.",
        "trigger": "Mechanical compressor trip.",
        "expectedEffect": "Inlet air temperatures exceed ASHRAE recommended threshold within 8 minutes; widespread SLA breach.",
        "suggestedDurationSec": 1800,
    },
    "fan_degradation": {
        "id": "fan_degradation",
        "name": "Fan Degradation",
        "category": "mechanical",
        "severity": "WARNING",
        "description": "Bearing wear and variable frequency drive degradation reducing effective CRAH airflow by 45%.",
        "initialConditions": "CRAH airflow reduced from 8500 CFM to 4675 CFM; rack internal fan speeds capped at 60%.",
        "trigger": "Mechanical wear on CRAH fan motor.",
        "expectedEffect": "Stagnant hot air recirculates through cold aisle; core temps rise steadily by 0.15°C/min.",
        "suggestedDurationSec": 2700,
    },
    "airflow_blockage": {
        "id": "airflow_blockage",
        "name": "Airflow Blockage (Blanking Panel Breach)",
        "category": "containment",
        "severity": "WARNING",
        "description": "Missing blanking panels and physical containment flap failure causing hot exhaust recirculation in Racks 03 & 04.",
        "initialConditions": "Heat transfer coefficient UA reduced by 55% in Racks 03 and 04 due to recirculating hot air.",
        "trigger": "Physical containment seal compromise.",
        "expectedEffect": "Localized hot spots develop in Rack 03 and 04 despite moderate CPU utilization.",
        "suggestedDurationSec": 1800,
    },
    "high_ambient_temp": {
        "id": "high_ambient_temp",
        "name": "High Ambient Temperature",
        "category": "environmental",
        "severity": "WARNING",
        "description": "External ambient heat dome raising external temperature to 39.5°C, reducing cooling plant COP.",
        "initialConditions": "External ambient temp set to 39.5°C; envelope heat infiltration increases by 300%.",
        "trigger": "Severe meteorological heatwave.",
        "expectedEffect": "Cooling power consumption surges by 32%; chiller COP drops below 2.8.",
        "suggestedDurationSec": 3600,
    },
    "rack_overload": {
        "id": "rack_overload",
        "name": "Rack Overload (Runaway Process)",
        "category": "workload",
        "severity": "CRITICAL",
        "description": "Runaway compute threads and hardware power draw spike on Rack 05 surpassing power density envelope.",
        "initialConditions": "Rack 05 power surge: CPU load 100%, server power draw elevated by +35% above nominal.",
        "trigger": "Unconstrained parallel batch process runaway.",
        "expectedEffect": "Rack 05 temperature accelerates towards critical 34°C threshold within 6 minutes.",
        "suggestedDurationSec": 1800,
    },
    "workload_imbalance": {
        "id": "workload_imbalance",
        "name": "Workload Imbalance (Hot Spotting)",
        "category": "workload",
        "severity": "WARNING",
        "description": "Poor orchestrator scheduling concentrating 95% of active microservices onto Racks 06 & 07 while others idle.",
        "initialConditions": "Racks 06 & 07 at 96% load; Racks 01, 02, 03 at 18-25% load.",
        "trigger": "Kubernetes node affinity misconfiguration.",
        "expectedEffect": "Extreme thermal disparity across hall; wasteful over-cooling of idle zones to protect hotspot zone.",
        "suggestedDurationSec": 2400,
    },
    "multiple_rack_hotspot": {
        "id": "multiple_rack_hotspot",
        "name": "Multiple Rack Hotspot",
        "category": "compound",
        "severity": "CRITICAL",
        "description": "Concurrently developing thermal plumes across Racks 02, 05, 06, and 07 due to cross-rack thermal coupling.",
        "initialConditions": "Adjacent racks experience cross-aisle heat leakage; aggregate core temps exceed 31°C.",
        "trigger": "Combined multi-tenant high load and containment leakage.",
        "expectedEffect": "Requires multi-action coordinated counterfactual intervention (airflow + load balancing).",
        "suggestedDurationSec": 3600,
    },
    "hardware_degradation": {
        "id": "hardware_degradation",
        "name": "Hardware Degradation (Thermal Aging)",
        "category": "wear",
        "severity": "WARNING",
        "description": "Thermal paste pump-out and dust accumulation gradually degrading heat transfer UA over time.",
        "initialConditions": "Thermal transfer efficiency UA degrades at a continuous rate of -0.01 per 500 simulated seconds.",
        "trigger": "Long-term thermal degradation over extended operational window.",
        "expectedEffect": "Progressive upward creep of baseline temperature profile over the simulation.",
        "suggestedDurationSec": 7200,
    },
}


WORKLOAD_PRESETS: Dict[str, Dict[str, Any]] = {
    "baseline": {
        "id": "baseline",
        "name": "Standard Mixed Telemetry",
        "description": "Web, Database, KV-Cache, Analytics, ML clusters running typical diurnal workload.",
        "loads": [45, 60, 52, 58, 78, 82, 88, 40],
    },
    "ai_burst": {
        "id": "ai_burst",
        "name": "Heavy AI / Deep Learning",
        "description": "Compute-bound cluster with heavy GPU training and continuous inference.",
        "loads": [55, 68, 62, 75, 94, 98, 96, 50],
    },
    "balanced": {
        "id": "balanced",
        "name": "Optimally Distributed Load",
        "description": "Evenly partitioned jobs across all 8 racks (55-65% utilization).",
        "loads": [58, 60, 56, 62, 60, 64, 62, 58],
    },
    "idle_night": {
        "id": "idle_night",
        "name": "Off-Peak Night Load",
        "description": "Low demand off-peak profile with minimal compute.",
        "loads": [25, 30, 28, 32, 35, 40, 38, 22],
    },
}


class ScenarioEngine:
    def __init__(self):
        self.active_problem_id = "none"
        self.active_workload_id = "baseline"
        self.sim_elapsed_seconds = 0
        self.active_problem = FAILURE_SCENARIOS["none"]
        self.active_workload = WORKLOAD_PRESETS["baseline"]

    def set_problem(self, problem_id: str):
        if problem_id in FAILURE_SCENARIOS:
            self.active_problem_id = problem_id
            self.active_problem = FAILURE_SCENARIOS[problem_id]

    def set_workload(self, workload_id: str):
        if workload_id in WORKLOAD_PRESETS:
            self.active_workload_id = workload_id
            self.active_workload = WORKLOAD_PRESETS[workload_id]

    def apply_to_physics(self, physics, elapsed_sec: int = 0):
        """
        Mutate physics engine state based on active problem and workload.
        Can be called repeatedly every timestep to handle progressive degradation.
        """
        self.sim_elapsed_seconds = elapsed_sec

        # 1. Apply baseline workload profile
        loads = self.active_workload.get("loads", [50] * len(physics.racks))
        for i, rack in enumerate(physics.racks):
            if i < len(loads):
                rack["cpuLoad"] = loads[i]

        pid = self.active_problem_id

        # 2. Apply specific failure problem mutations
        if pid == "ai_workload_spike":
            if len(physics.racks) >= 7:
                physics.racks[5]["cpuLoad"] = 96
                physics.racks[6]["cpuLoad"] = 98

        elif pid == "gpu_training_burst":
            for i in [3, 4, 5, 6]:
                if i < len(physics.racks):
                    physics.racks[i]["cpuLoad"] = 97

        elif pid == "cooling_failure":
            physics.cooling_supply_temp = 24.5
            physics.crah_airflow_cfm = 5525.0  # 35% drop
            physics.chiller_cop = 2.4

        elif pid == "fan_degradation":
            physics.crah_airflow_cfm = 4675.0  # 45% drop
            for r in physics.racks:
                r["fanSpeed"] = min(60, r.get("fanSpeed", 70))

        elif pid == "airflow_blockage":
            if len(physics.racks) >= 4:
                physics.racks[2]["ua"] = 0.20  # was 0.44
                physics.racks[3]["ua"] = 0.21  # was 0.46

        elif pid == "high_ambient_temp":
            physics.ambient_temp = 39.5
            physics.cooling_supply_temp = 21.8

        elif pid == "rack_overload":
            if len(physics.racks) >= 5:
                physics.racks[4]["cpuLoad"] = 100
                physics.racks[4]["servers"] = 14  # temporary server power surge

        elif pid == "workload_imbalance":
            if len(physics.racks) >= 7:
                physics.racks[5]["cpuLoad"] = 97
                physics.racks[6]["cpuLoad"] = 98
                physics.racks[0]["cpuLoad"] = 20
                physics.racks[1]["cpuLoad"] = 22
                physics.racks[2]["cpuLoad"] = 20

        elif pid == "multiple_rack_hotspot":
            indices = [1, 4, 5, 6]
            for idx in indices:
                if idx < len(physics.racks):
                    physics.racks[idx]["cpuLoad"] = 92
                    physics.racks[idx]["fanSpeed"] = 65

        elif pid == "hardware_degradation":
            # Progressive degradation over time
            decay = min(0.20, (elapsed_sec / 3600.0) * 0.08)
            for r in physics.racks:
                nominal_ua = 0.48 if r.get("zone") == "A" else 0.54
                r["ua"] = max(0.22, nominal_ua - decay)

    def to_dict(self) -> dict:
        return {
            "activeProblemId": self.active_problem_id,
            "activeProblem": self.active_problem,
            "activeWorkloadId": self.active_workload_id,
            "activeWorkload": self.active_workload,
            "allProblems": list(FAILURE_SCENARIOS.values()),
            "allWorkloads": list(WORKLOAD_PRESETS.values()),
        }
