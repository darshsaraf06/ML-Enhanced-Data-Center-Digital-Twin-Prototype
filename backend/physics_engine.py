"""
Physics-Informed RC Thermal Engine for Data Center Digital Twin.
Equation: C_i * (dT_i/dt) = Q_i - UA_i*(T_i - T_cool) + Sum(K_ij*(T_j - T_i))
Python port of the front-end physics_engine.js
"""

import copy
import time
from datetime import datetime
from typing import List, Optional


def _default_racks() -> List[dict]:
    return [
        {"id": 1, "name": "Rack 01 [Web/API]",    "zone": "A", "cpuLoad": 45, "servers": 12, "temp": 24.5, "inletTemp": 19.2, "outletTemp": 28.1, "thermalCap": 3.2, "ua": 0.45, "fanSpeed": 65, "workloadType": "Web Servers"},
        {"id": 2, "name": "Rack 02 [Database]",   "zone": "A", "cpuLoad": 60, "servers": 14, "temp": 26.8, "inletTemp": 19.8, "outletTemp": 31.4, "thermalCap": 3.5, "ua": 0.48, "fanSpeed": 70, "workloadType": "PostgreSQL DB"},
        {"id": 3, "name": "Rack 03 [Cache/KV]",   "zone": "A", "cpuLoad": 52, "servers": 10, "temp": 25.4, "inletTemp": 19.4, "outletTemp": 29.2, "thermalCap": 3.0, "ua": 0.44, "fanSpeed": 65, "workloadType": "Redis Cluster"},
        {"id": 4, "name": "Rack 04 [Analytics]",  "zone": "A", "cpuLoad": 58, "servers": 12, "temp": 26.1, "inletTemp": 19.5, "outletTemp": 30.8, "thermalCap": 3.2, "ua": 0.46, "fanSpeed": 68, "workloadType": "Spark Nodes"},
        {"id": 5, "name": "Rack 05 [ML Train 1]", "zone": "B", "cpuLoad": 78, "servers":  8, "temp": 29.4, "inletTemp": 21.2, "outletTemp": 35.6, "thermalCap": 4.2, "ua": 0.52, "fanSpeed": 85, "workloadType": "GPU Cluster A"},
        {"id": 6, "name": "Rack 06 [ML Train 2]", "zone": "B", "cpuLoad": 82, "servers":  8, "temp": 30.8, "inletTemp": 21.8, "outletTemp": 37.2, "thermalCap": 4.2, "ua": 0.54, "fanSpeed": 90, "workloadType": "GPU Cluster B"},
        {"id": 7, "name": "Rack 07 [AI LLM Infer]","zone": "B", "cpuLoad": 88, "servers":  8, "temp": 32.1, "inletTemp": 22.4, "outletTemp": 39.8, "thermalCap": 4.5, "ua": 0.55, "fanSpeed": 92, "workloadType": "LLM Inference"},
        {"id": 8, "name": "Rack 08 [Storage]",    "zone": "B", "cpuLoad": 40, "servers": 16, "temp": 25.2, "inletTemp": 20.1, "outletTemp": 29.0, "thermalCap": 3.8, "ua": 0.42, "fanSpeed": 60, "workloadType": "NVMe Array"},
    ]


# Spatial thermal coupling matrix K_ij (heat transfer between adjacent racks)
_COUPLING_MATRIX = [
    [0,    0.08, 0.02, 0,    0.05, 0,    0,    0   ],
    [0.08, 0,    0.09, 0.02, 0,    0.06, 0,    0   ],
    [0.02, 0.09, 0,    0.08, 0,    0,    0.05, 0   ],
    [0,    0.02, 0.08, 0,    0,    0,    0,    0.04],
    [0.05, 0,    0,    0,    0,    0.09, 0.03, 0   ],
    [0,    0.06, 0,    0,    0.09, 0,    0.10, 0.02],
    [0,    0,    0.05, 0,    0.03, 0.10, 0,    0.08],
    [0,    0,    0,    0.04, 0,    0.02, 0.08, 0   ],
]


class ThermalPhysicsEngine:
    def __init__(self):
        self.ambient_temp: float = 28.0        # °C external ambient
        self.cooling_supply_temp: float = 18.0  # °C CRAH cold air supply
        self.crah_airflow_cfm: float = 8500.0   # Total cooling airflow
        self.crah_fan_power_kw: float = 45.0    # CRAH fan power
        self.chiller_cop: float = 3.8           # Coefficient of Performance
        self.coupling_matrix = _COUPLING_MATRIX

        self.racks: List[dict] = _default_racks()
        self.history: List[dict] = []
        self.max_history_length: int = 60
        self.time_step_sec: int = 1

    # ------------------------------------------------------------------
    def compute_rack_power(self, rack: dict) -> float:
        """Compute heat generation Q_i (kW) from CPU load and server count."""
        power_per_server = 0.12 + (rack["cpuLoad"] / 100.0) * 0.36
        return rack["servers"] * power_per_server

    # ------------------------------------------------------------------
    def step(self, dt: float = 1.0) -> dict:
        """Advance the RC thermal ODE by timestep dt (seconds) with sub-stepping."""
        substeps = max(1, int(round(dt / 1.0)))
        sub_dt = dt / substeps

        total_it_power = 0.0
        for _ in range(substeps):
            new_temps = []
            total_it_power = 0.0

            for i, rack in enumerate(self.racks):
                qi = self.compute_rack_power(rack)
                total_it_power += qi

                t_cool = self.cooling_supply_temp + (2.5 if rack["zone"] == "B" else 0.8)
                cooling_rate = rack["ua"] * (rack["fanSpeed"] / 100.0) * (rack["temp"] - t_cool)

                neighbor_heat = sum(
                    self.coupling_matrix[i][j] * (self.racks[j]["temp"] - rack["temp"])
                    for j in range(len(self.racks)) if i != j
                )

                ambient_leakage = 0.015 * (self.ambient_temp - rack["temp"])
                d_t_dt = (qi - cooling_rate + neighbor_heat + ambient_leakage) / rack["thermalCap"]
                next_temp = rack["temp"] + d_t_dt * sub_dt
                next_temp = max(18.0, min(50.0, next_temp))
                new_temps.append(next_temp)

            for i, rack in enumerate(self.racks):
                rack["temp"] = round(new_temps[i], 3)
            rack["inletTemp"] = round(
                self.cooling_supply_temp + (rack["temp"] - self.cooling_supply_temp) * 0.22, 2
            )
            rack["outletTemp"] = round(rack["temp"] + self.compute_rack_power(rack) * 1.8, 2)

        # Thermodynamic COP variation: Lower supply temp increases chiller lift -> lower COP -> more power
        cop_penalty = max(0.5, 1.0 - 0.04 * (18.0 - self.cooling_supply_temp))
        effective_cop = self.chiller_cop * cop_penalty
        fan_kw = self.crah_fan_power_kw * (self.crah_airflow_cfm / 8500.0) ** 1.8
        total_cooling_kw = (total_it_power / effective_cop) + fan_kw
        pue = (total_it_power + total_cooling_kw) / total_it_power if total_it_power > 0 else 1.0
        max_temp = max(r["temp"] for r in self.racks)
        avg_temp = sum(r["temp"] for r in self.racks) / len(self.racks)

        snapshot = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "racks": [
                {"id": r["id"], "temp": r["temp"], "cpuLoad": r["cpuLoad"],
                 "power": round(self.compute_rack_power(r), 3)}
                for r in self.racks
            ],
            "totalITPower": round(total_it_power, 3),
            "coolingPower": round(total_cooling_kw, 3),
            "pue": round(pue, 4),
            "maxTemp": round(max_temp, 2),
            "avgTemp": round(avg_temp, 2),
        }

        self.history.append(snapshot)
        if len(self.history) > self.max_history_length:
            self.history.pop(0)

        return snapshot

    # ------------------------------------------------------------------
    def clone(self) -> "ThermalPhysicsEngine":
        """Return a deep-copy of this engine for counterfactual simulation."""
        cloned = ThermalPhysicsEngine()
        cloned.ambient_temp = self.ambient_temp
        cloned.cooling_supply_temp = self.cooling_supply_temp
        cloned.crah_airflow_cfm = self.crah_airflow_cfm
        cloned.crah_fan_power_kw = self.crah_fan_power_kw
        cloned.chiller_cop = self.chiller_cop
        cloned.racks = copy.deepcopy(self.racks)
        return cloned

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Full serialisable state snapshot (camelCase keys to match JS frontend)."""
        return {
            "ambientTemp":       self.ambient_temp,
            "coolingSupplyTemp": self.cooling_supply_temp,
            "crahAirflowCFM":    self.crah_airflow_cfm,
            "crahFanPowerKW":    self.crah_fan_power_kw,
            "chillerCOP":        self.chiller_cop,
            "racks":             copy.deepcopy(self.racks),
            "history":           self.history[-20:],  # last 20 snapshots
        }

