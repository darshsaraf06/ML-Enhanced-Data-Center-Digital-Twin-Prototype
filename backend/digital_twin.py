"""
Digital Twin Physics & Thermal Model for Data Center Hall.
Implements the RC (Resistance-Capacitance) network thermal differential equations:
    C_i * (dT_i / dt) = Q_i - UA_i * (v_fan_i / v_max) * (T_i - T_supply)
                        + Sum_j [ K_ij * (T_j - T_i) ]
                        + k_env * (T_ambient - T_i)

Includes:
- Multi-zone airflow coupling (Zone A Web/DB, Zone B GPU/AI clusters)
- Rack inlet (supply approach) and outlet (exhaust) temperatures
- CPU & GPU utilization modeling
- Chiller thermodynamic COP and CRAH fan affinity laws
- Safe / Warning / Critical risk assessment
"""

import copy
import math
from datetime import datetime
from typing import List, Dict, Any, Optional


def create_rack_bay(num_racks: int = 8, initial_load: float = 60.0) -> List[Dict[str, Any]]:
    """Generate configurable number of racks with realistic thermal properties."""
    specs = [
        {"name": "Rack 01 [Web/Ingress]",  "zone": "A", "type": "Web Servers",     "servers": 12, "baseLoad": 45, "gpu": 10, "cap": 3.2, "ua": 0.45, "fan": 65},
        {"name": "Rack 02 [Primary DB]",   "zone": "A", "type": "PostgreSQL DB",   "servers": 14, "baseLoad": 60, "gpu": 15, "cap": 3.5, "ua": 0.48, "fan": 70},
        {"name": "Rack 03 [Redis/KV]",     "zone": "A", "type": "Cache Cluster",   "servers": 10, "baseLoad": 52, "gpu": 5,  "cap": 3.0, "ua": 0.44, "fan": 65},
        {"name": "Rack 04 [Analytics/ETL]","zone": "A", "type": "Spark Compute",   "servers": 12, "baseLoad": 58, "gpu": 25, "cap": 3.2, "ua": 0.46, "fan": 68},
        {"name": "Rack 05 [ML Train 1]",   "zone": "B", "type": "GPU H100 Node A", "servers":  8, "baseLoad": 78, "gpu": 85, "cap": 4.2, "ua": 0.52, "fan": 85},
        {"name": "Rack 06 [ML Train 2]",   "zone": "B", "type": "GPU H100 Node B", "servers":  8, "baseLoad": 82, "gpu": 90, "cap": 4.2, "ua": 0.54, "fan": 90},
        {"name": "Rack 07 [LLM Inference]","zone": "B", "type": "LLM Inference",   "servers":  8, "baseLoad": 88, "gpu": 95, "cap": 4.5, "ua": 0.55, "fan": 92},
        {"name": "Rack 08 [NVMe Storage]", "zone": "B", "type": "Ceph Storage",    "servers": 16, "baseLoad": 40, "gpu": 0,  "cap": 3.8, "ua": 0.42, "fan": 60},
        {"name": "Rack 09 [Microservices]","zone": "A", "type": "K8s Workers",     "servers": 12, "baseLoad": 50, "gpu": 20, "cap": 3.2, "ua": 0.45, "fan": 65},
        {"name": "Rack 10 [High-Mem DB]",  "zone": "A", "type": "In-Memory DB",    "servers": 14, "baseLoad": 65, "gpu": 10, "cap": 3.6, "ua": 0.48, "fan": 72},
        {"name": "Rack 11 [Vision Model]", "zone": "B", "type": "GPU Vision Node", "servers":  8, "baseLoad": 80, "gpu": 88, "cap": 4.3, "ua": 0.53, "fan": 88},
        {"name": "Rack 12 [Backup Archive]","zone": "B", "type": "Glacier Storage", "servers": 16, "baseLoad": 35, "gpu": 0,  "cap": 3.7, "ua": 0.40, "fan": 55},
    ]

    racks = []
    ratio = initial_load / 60.0 if initial_load > 0 else 1.0
    for i in range(num_racks):
        spec = specs[i % len(specs)]
        cpu_load = max(10, min(100, round(spec["baseLoad"] * ratio)))
        gpu_load = max(0, min(100, round(spec["gpu"] * ratio)))
        racks.append({
            "id": i + 1,
            "name": f"Rack {i+1:02d} [{spec['type']}]",
            "zone": spec["zone"],
            "workloadType": spec["type"],
            "servers": spec["servers"],
            "cpuLoad": cpu_load,
            "gpuLoad": gpu_load,
            "temp": round(23.5 + (cpu_load / 100.0) * 8.5, 2),
            "inletTemp": 19.5,
            "outletTemp": 29.0,
            "thermalCap": spec["cap"],
            "ua": spec["ua"],
            "fanSpeed": spec["fan"],
            "airflowCfm": round(spec["fan"] * 12.5, 1),
            "powerKw": 0.0,
            "thermalRisk": "Safe",
        })
    return racks


def build_coupling_matrix(n: int) -> List[List[float]]:
    """Generate spatial heat coupling matrix based on proximity in row."""
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist = abs(i - j)
            if dist == 1:
                matrix[i][j] = 0.085
            elif dist == 2:
                matrix[i][j] = 0.020
            elif dist == 4:  # cross-aisle facing rack
                matrix[i][j] = 0.045
    return matrix


class DigitalTwinPhysics:
    def __init__(self, num_racks: int = 8, initial_load: float = 60.0):
        self.num_racks = num_racks
        self.ambient_temp: float = 24.0          # °C dry-bulb
        self.ambient_humidity: float = 50.0      # % RH
        self.cooling_supply_temp: float = 18.0   # °C CRAH air supply setpoint
        self.crah_airflow_cfm: float = 8500.0    # Total CRAH fan airflow
        self.crah_fan_power_kw: float = 45.0     # Baseline fan electrical power
        self.chiller_cop: float = 3.8            # Nominal chiller COP
        self.safety_threshold_temp: float = 33.0 # °C ASHRAE warning threshold
        self.critical_threshold_temp: float = 36.0 # °C ASHRAE critical threshold

        self.racks: List[Dict[str, Any]] = create_rack_bay(num_racks, initial_load)
        self.coupling_matrix = build_coupling_matrix(num_racks)
        self.history: List[Dict[str, Any]] = []
        self.max_history_length: int = 120

    def compute_rack_power(self, rack: Dict[str, Any]) -> float:
        """
        Compute total electrical power / heat dissipation Q_i (kW).
        P = P_idle + P_cpu(cpuLoad) + P_gpu(gpuLoad)
        """
        servers = rack.get("servers", 10)
        cpu_load = rack.get("cpuLoad", 50)
        gpu_load = rack.get("gpuLoad", 0)

        # Baseline server idle + CPU power
        cpu_kw = servers * (0.12 + (cpu_load / 100.0) * 0.32)
        # Accelerated GPU TDP power
        gpu_kw = servers * (0.05 + (gpu_load / 100.0) * 0.45) if gpu_load > 0 else 0.0

        total_kw = round(cpu_kw + gpu_kw, 3)
        rack["powerKw"] = total_kw
        return total_kw

    def step(self, dt: float = 1.0, cop_multiplier: float = 1.0) -> Dict[str, Any]:
        """
        Advance RC thermal state by dt seconds.
        dt: simulated seconds elapsed in this step.
        """
        substeps = max(1, int(round(dt / 1.0)))
        sub_dt = dt / substeps

        total_it_power = 0.0

        for _ in range(substeps):
            new_temps = []
            total_it_power = 0.0

            for i, rack in enumerate(self.racks):
                qi = self.compute_rack_power(rack)
                total_it_power += qi

                # Local microclimate cooling supply temperature
                # Zone B (AI/GPU high-density) experiences slight plenum thermal mixing (+2.2°C)
                zone_penalty = 2.2 if rack.get("zone") == "B" else 0.6
                t_cool_local = self.cooling_supply_temp + zone_penalty

                # Convective cooling rate through chassis heat sink
                fan_ratio = max(0.2, rack.get("fanSpeed", 70) / 100.0)
                cooling_rate = rack["ua"] * fan_ratio * (rack["temp"] - t_cool_local)

                # Cross-rack spatial conduction and air mixing
                neighbor_heat = sum(
                    self.coupling_matrix[i][j] * (self.racks[j]["temp"] - rack["temp"])
                    for j in range(len(self.racks)) if i != j
                )

                # Building envelope heat leakage from ambient
                ambient_leakage = 0.018 * (self.ambient_temp - rack["temp"])

                # Thermal ODE: C * dT/dt = Q_in - Q_cool + Q_coupled + Q_leak
                c_cap = max(1.5, rack.get("thermalCap", 3.5))
                d_temp_dt = (qi - cooling_rate + neighbor_heat + ambient_leakage) / c_cap

                next_temp = rack["temp"] + d_temp_dt * sub_dt
                # Physical bounds (18°C floor to 55°C ceiling)
                next_temp = max(18.0, min(55.0, next_temp))
                new_temps.append(next_temp)

            for i, rack in enumerate(self.racks):
                rack["temp"] = round(new_temps[i], 3)
                # Compute inlet and outlet temperatures
                rack["inletTemp"] = round(
                    self.cooling_supply_temp + (rack["temp"] - self.cooling_supply_temp) * 0.24, 2
                )
                rack["outletTemp"] = round(rack["temp"] + self.compute_rack_power(rack) * 1.65, 2)
                rack["airflowCfm"] = round(rack.get("fanSpeed", 70) * 12.5, 1)

                # Thermal risk categorization
                if rack["temp"] >= self.critical_threshold_temp:
                    rack["thermalRisk"] = "Critical"
                elif rack["temp"] >= self.safety_threshold_temp:
                    rack["thermalRisk"] = "Warning"
                else:
                    rack["thermalRisk"] = "Safe"

        # Thermodynamic COP calculation with ambient wet-bulb factor & supply temperature lift
        effective_cop = self.chiller_cop * cop_multiplier * max(0.5, 1.0 - 0.035 * (18.0 - self.cooling_supply_temp))
        effective_cop = max(1.2, effective_cop)

        # Fan affinity law: Power is proportional to airflow cubed (P_fan ~ (CFM/CFM_nominal)^2.2)
        fan_ratio = max(0.3, self.crah_airflow_cfm / 8500.0)
        fan_kw = self.crah_fan_power_kw * (fan_ratio ** 2.2)

        # Chiller compressor electrical power to remove IT thermal heat
        chiller_kw = total_it_power / effective_cop
        total_cooling_kw = chiller_kw + fan_kw
        total_facility_kw = total_it_power + total_cooling_kw

        pue = total_facility_kw / total_it_power if total_it_power > 0 else 1.0

        max_temp = max(r["temp"] for r in self.racks)
        min_temp = min(r["temp"] for r in self.racks)
        avg_temp = sum(r["temp"] for r in self.racks) / len(self.racks)

        snapshot = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "racks": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "zone": r["zone"],
                    "temp": r["temp"],
                    "inletTemp": r["inletTemp"],
                    "outletTemp": r["outletTemp"],
                    "cpuLoad": r["cpuLoad"],
                    "gpuLoad": r["gpuLoad"],
                    "powerKw": r["powerKw"],
                    "fanSpeed": r["fanSpeed"],
                    "airflowCfm": r["airflowCfm"],
                    "thermalRisk": r["thermalRisk"],
                }
                for r in self.racks
            ],
            "totalITPower": round(total_it_power, 3),
            "coolingPower": round(total_cooling_kw, 3),
            "chillerPower": round(chiller_kw, 3),
            "fanPower": round(fan_kw, 3),
            "totalFacilityPower": round(total_facility_kw, 3),
            "pue": round(pue, 4),
            "maxTemp": round(max_temp, 2),
            "minTemp": round(min_temp, 2),
            "avgTemp": round(avg_temp, 2),
            "effectiveCOP": round(effective_cop, 2),
            "ambientTemp": self.ambient_temp,
            "coolingSupplyTemp": self.cooling_supply_temp,
            "crahAirflowCFM": self.crah_airflow_cfm,
        }

        self.history.append(snapshot)
        if len(self.history) > self.max_history_length:
            self.history.pop(0)

        return snapshot

    def clone(self) -> "DigitalTwinPhysics":
        """Deep copy for parallel counterfactual branch simulations."""
        cloned = DigitalTwinPhysics(num_racks=len(self.racks))
        cloned.ambient_temp = self.ambient_temp
        cloned.ambient_humidity = self.ambient_humidity
        cloned.cooling_supply_temp = self.cooling_supply_temp
        cloned.crah_airflow_cfm = self.crah_airflow_cfm
        cloned.crah_fan_power_kw = self.crah_fan_power_kw
        cloned.chiller_cop = self.chiller_cop
        cloned.safety_threshold_temp = self.safety_threshold_temp
        cloned.critical_threshold_temp = self.critical_threshold_temp
        cloned.racks = copy.deepcopy(self.racks)
        cloned.coupling_matrix = copy.deepcopy(self.coupling_matrix)
        return cloned

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numRacks": len(self.racks),
            "ambientTemp": self.ambient_temp,
            "ambientHumidity": self.ambient_humidity,
            "coolingSupplyTemp": self.cooling_supply_temp,
            "crahAirflowCFM": self.crah_airflow_cfm,
            "crahFanPowerKW": self.crah_fan_power_kw,
            "chillerCOP": self.chiller_cop,
            "safetyThresholdTemp": self.safety_threshold_temp,
            "criticalThresholdTemp": self.critical_threshold_temp,
            "racks": copy.deepcopy(self.racks),
            "history": self.history[-30:],
        }
