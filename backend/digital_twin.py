"""
Digital twin physics for a small data hall.

Air path, per rack i:
    inlet_i   = (1 - r_i) * supply_local + r_i * hot_aisle_i + disturbance_i      (cold-aisle mixing, tau 30 s)
    C * d(exhaust_i)/dt = P_i - rho*cp*Q_i * (exhaust_i - inlet_i)                (server thermal mass)
r_i is the recirculation share: hot exhaust that leaks back into the rack inlet.
It grows when the CRAH units supply less air than the servers pull (air starvation),
at row ends, and when containment is breached.

Cooling plant (water-cooled chiller + cooling tower + CRAH fans):
    capacity = design * plant_avail * (free + (1 - free) * chiller_avail * derate(wet_bulb))
    if heat load > capacity the stored heat warms the supply air:
    C_loop * dT_supply/dt = load - capacity.
Power: chiller = mechanical load / COP (Carnot fraction), CRAH fans follow the cube law,
pumps follow load squared, tower fans scale with heat rejected.

All parameters are documented in docs/MODEL_PARAMETERS.md and defined in model_params.py.
"""

import copy
import math
from typing import Any, Dict, List

import model_params as P


class Modifiers:
    """Effects of active events on the facility. Rebuilt every step from the event schedule."""

    __slots__ = ("plant_avail", "chiller_avail", "crah_avail", "economizer_ok",
                 "util_delta", "util_set", "racks_off", "recirc_add", "heat_add")

    def __init__(self):
        self.plant_avail = 1.0      # whole cooling plant incl. pumps and tower (0 during power loss)
        self.chiller_avail = 1.0    # compressor availability
        self.crah_avail = 1.0       # CRAH airflow availability
        self.economizer_ok = True   # waterside free cooling allowed
        self.util_delta: Dict[int, float] = {}   # rack id -> utilization change (points)
        self.util_set: Dict[int, float] = {}     # rack id -> forced utilization
        self.racks_off: set = set()              # rack ids shut down
        self.recirc_add: Dict[int, float] = {}   # rack id -> extra recirculation share
        self.heat_add: Dict[int, float] = {}     # rack id -> extra heat (kW), e.g. runaway hardware


def _rack_name(i: int, rtype: str) -> str:
    return f"Rack {i + 1:02d}"


class DigitalTwinPhysics:
    def __init__(self, num_racks: int = 8, scale: str = "medium",
                 setpoint: float = P.DEFAULT_SUPPLY_SETPOINT_C,
                 crah_fraction: float = P.DEFAULT_CRAH_FRACTION,
                 inlet_limit: float = P.DEFAULT_INLET_LIMIT_C):
        self.num_racks = int(num_racks)
        self.scale = scale if scale in P.SCALE_DENSITY else "medium"
        density = P.SCALE_DENSITY[self.scale]
        self.inlet_limit = float(inlet_limit)
        self.allowable_limit = P.ALLOWABLE_INLET_LIMIT_C

        n_a = (self.num_racks + 1) // 2
        self.racks: List[Dict[str, Any]] = []
        for i in range(self.num_racks):
            rtype = P.RACK_LAYOUT[i % len(P.RACK_LAYOUT)]
            spec = P.RACK_TYPES[rtype]
            zone = "A" if i < n_a else "B"
            row = list(range(0, n_a)) if zone == "A" else list(range(n_a, self.num_racks))
            pos = row.index(i)
            row_len = len(row)
            is_end = pos == 0 or pos == row_len - 1
            pmax = spec["pmax_kw"] * density
            design_flow = pmax / (P.RHO_CP_AIR * P.SERVER_DESIGN_DELTA_T)
            self.racks.append({
                "id": i + 1,
                "code": f"R{i + 1:02d}",
                "name": _rack_name(i, rtype),
                "type": rtype,
                "typeLabel": spec["label"],
                "zone": zone,
                "rowPosition": pos,
                "rowLength": row_len,
                "pmaxKw": round(pmax, 3),
                "idleFraction": spec["idle_fraction"],
                "baseUtil": float(spec["base_util"]),
                "designFlow": design_flow,
                "recircBase": P.RECIRC_BASE_END if is_end else P.RECIRC_BASE_MIDDLE,
                "starvationWeight": 0.7 + 0.6 * (pos / max(1, row_len - 1)),
                # controllable
                "powerCapKw": None,
                "airflowFactor": 1.0,
                # disturbances (set by the simulation each step)
                "heatPulseKw": 0.0,
                "inletOffset": 0.0,
                # state
                "util": float(spec["base_util"]),
                "powerKw": 0.0,
                "airflowM3s": design_flow * 0.7,
                "inletTemp": setpoint,
                "exhaustTemp": setpoint + P.SERVER_TARGET_DELTA_T,
                "recirc": 0.0,
                "off": False,
            })

        self.design_it_kw = sum(r["pmaxKw"] for r in self.racks)
        self.design_server_flow = sum(r["designFlow"] for r in self.racks)
        self.crah_design_flow = self.design_server_flow * P.CRAH_DESIGN_OVERSUPPLY
        self.design_capacity_kw = self.design_it_kw * P.PLANT_CAPACITY_FACTOR
        self.pump_design_kw = self.design_capacity_kw * P.PUMP_DESIGN_FRACTION
        self.crah_fan_design_kw = P.CRAH_FAN_SFP_KW_PER_M3S * self.crah_design_flow
        self.envelope_ua = P.ENVELOPE_UA_KW_K_PER_RACK * self.num_racks

        # controls
        self.supply_setpoint = float(setpoint)
        self.crah_fraction = float(crah_fraction)
        # environment inputs
        self.outside_temp = 24.0
        self.humidity = 50.0
        self.wet_bulb = 17.0
        self.mods = Modifiers()
        # state
        self.supply_temp = float(setpoint)
        self.out: Dict[str, float] = {}
        self._compute_power_and_flow()

    # ── helpers ────────────────────────────────────────────────────────────
    def _rack_power(self, rack: Dict[str, Any]) -> float:
        if rack["off"]:
            return 0.0
        util = max(0.0, min(100.0, rack["util"]))
        p = rack["pmaxKw"] * (rack["idleFraction"] + (1.0 - rack["idleFraction"]) * util / 100.0)
        if rack["powerCapKw"] is not None:
            p = min(p, float(rack["powerCapKw"]))
        return p + max(0.0, rack["heatPulseKw"]) + max(0.0, self.mods.heat_add.get(rack["id"], 0.0))

    def _compute_power_and_flow(self):
        for rack in self.racks:
            p = self._rack_power(rack)
            rack["powerKw"] = p
            if rack["off"]:
                rack["airflowM3s"] = 0.0
                continue
            f = max(0.3, rack["airflowFactor"])
            qmax = rack["designFlow"] * f
            qmin = P.SERVER_MIN_FLOW_FRACTION * rack["designFlow"] * f
            q = p / (P.RHO_CP_AIR * P.SERVER_TARGET_DELTA_T) * f
            rack["airflowM3s"] = max(qmin, min(qmax, q))

    def chiller_cop(self) -> float:
        t_evap = self.supply_setpoint - P.CHW_APPROACH_K + 273.15
        t_cond = self.wet_bulb + P.TOWER_APPROACH_K + P.CONDENSER_APPROACH_K + 273.15
        lift = max(3.0, t_cond - t_evap)
        return max(P.COP_MIN, min(P.COP_MAX, P.CHILLER_CARNOT_EFFICIENCY * t_evap / lift))

    def free_cooling_fraction(self) -> float:
        if not self.mods.economizer_ok:
            return 0.0
        t_chw = self.supply_setpoint - P.CHW_APPROACH_K
        t_tower = self.wet_bulb + P.TOWER_APPROACH_K
        return max(0.0, min(1.0, (t_chw - t_tower) / P.FREE_COOLING_BAND_K))

    def capacity_derate(self) -> float:
        return max(0.4, 1.0 - P.CAPACITY_DERATE_PER_K * max(0.0, self.wet_bulb - P.CAPACITY_REF_WET_BULB_C))

    # ── main step ──────────────────────────────────────────────────────────
    def step(self, dt: float = P.PHYSICS_DT_S) -> Dict[str, float]:
        m = self.mods
        for rack in self.racks:
            rack["off"] = rack["id"] in m.racks_off
        self._compute_power_and_flow()

        it_kw = sum(r["powerKw"] for r in self.racks)
        demand_flow = sum(r["airflowM3s"] for r in self.racks)
        crah_flow = self.crah_fraction * max(0.0, m.crah_avail) * self.crah_design_flow
        ratio = crah_flow / demand_flow if demand_flow > 1e-6 else 2.0

        # recirculation per rack
        for rack in self.racks:
            base = rack["recircBase"]
            if ratio >= 1.0:
                r = base * max(0.5, min(1.0, 2.0 - ratio))
            else:
                r = base + (1.0 - ratio) * rack["starvationWeight"] * P.RECIRC_STARVATION_GAIN
            rack["recirc"] = max(0.0, min(0.85, r + m.recirc_add.get(rack["id"], 0.0)))

        # cooling plant
        exhaust_avg = sum(r["exhaustTemp"] for r in self.racks) / self.num_racks
        env_kw = self.envelope_ua * (self.outside_temp - exhaust_avg)
        crah_fan_kw = self.crah_fan_design_kw * (crah_flow / self.crah_design_flow) ** 3 if self.crah_design_flow else 0.0
        load_kw = max(0.0, it_kw + env_kw + crah_fan_kw)
        free = self.free_cooling_fraction() * (1.0 if m.plant_avail > 0 else 0.0)
        capacity_kw = self.design_capacity_kw * max(0.0, m.plant_avail) * (
            free + (1.0 - free) * max(0.0, m.chiller_avail) * self.capacity_derate())
        # Supply air: an energy balance on the air, coil and chilled-water loop mass.
        # With spare capacity the controller pulls the supply air back to the setpoint;
        # during a deficit the stored heat accumulates and the supply air warms up.
        c_loop = P.SUPPLY_THERMAL_MASS_KJ_K_PER_RACK * self.num_racks
        net_kw = load_kw - capacity_kw
        if net_kw > 0:
            d_sup = net_kw / c_loop * dt
        else:
            d_sup = (self.supply_setpoint - self.supply_temp) * min(1.0, dt / P.SUPPLY_TAU_S)
            if d_sup < 0:
                d_sup = max(d_sup, net_kw / c_loop * dt)   # recovery limited by spare capacity
        new_supply = min(45.0, self.supply_temp + d_sup)
        removed_kw = max(0.0, min(capacity_kw, load_kw - c_loop * (new_supply - self.supply_temp) / dt))
        deficit_kw = max(0.0, net_kw)
        self.supply_temp = new_supply

        # rack air temperatures
        new_inlet = []
        new_exhaust = []
        for idx, rack in enumerate(self.racks):
            neighbours = [self.racks[j]["exhaustTemp"] for j in (idx - 1, idx + 1)
                          if 0 <= j < self.num_racks and self.racks[j]["zone"] == rack["zone"]]
            hot_local = 0.6 * rack["exhaustTemp"] + 0.4 * (sum(neighbours) / len(neighbours) if neighbours else rack["exhaustTemp"])
            supply_local = self.supply_temp + P.ZONE_SUPPLY_OFFSET_C.get(rack["zone"], 0.0)
            target_in = (1.0 - rack["recirc"]) * supply_local + rack["recirc"] * hot_local + rack["inletOffset"]
            rack["inletTarget"] = target_in
            t_in = rack["inletTemp"] + (target_in - rack["inletTemp"]) * min(1.0, dt / P.COLD_AISLE_TAU_S)
            q = rack["airflowM3s"]
            if q > 1e-6:
                d_ex = (rack["powerKw"] - P.RHO_CP_AIR * q * (rack["exhaustTemp"] - t_in)) / P.RACK_THERMAL_MASS_KJ_K
                t_ex = rack["exhaustTemp"] + d_ex * dt
            else:   # rack shut down: chassis drifts toward the inlet air
                t_ex = rack["exhaustTemp"] + (t_in - rack["exhaustTemp"]) * min(1.0, dt / 600.0)
            new_inlet.append(t_in)
            new_exhaust.append(t_ex)
        for rack, t_in, t_ex in zip(self.racks, new_inlet, new_exhaust):
            rack["inletTemp"] = t_in
            rack["exhaustTemp"] = t_ex

        # energy
        cop = self.chiller_cop()
        free_removed = min(removed_kw, self.design_capacity_kw * max(0.0, m.plant_avail) * free)
        mech_removed = removed_kw - free_removed
        chiller_kw = mech_removed / cop if m.chiller_avail > 0 else 0.0
        heat_rejected_kw = removed_kw + chiller_kw
        tower_fan_kw = P.TOWER_FAN_FRACTION * heat_rejected_kw
        pump_kw = (self.pump_design_kw * max(0.25, removed_kw / self.design_capacity_kw) ** 2) if m.plant_avail > 0 else 0.0
        fans_kw = crah_fan_kw + tower_fan_kw
        cooling_kw = chiller_kw + fans_kw + pump_kw
        facility_kw = it_kw + cooling_kw
        self.out = {
            "itKw": it_kw,
            "chillerKw": chiller_kw,
            "fansKw": fans_kw,
            "crahFanKw": crah_fan_kw,
            "towerFanKw": tower_fan_kw,
            "pumpsKw": pump_kw,
            "coolingKw": cooling_kw,
            "facilityKw": facility_kw,
            "pue": facility_kw / it_kw if it_kw > 0 else 1.0,
            "heatRejectedKw": heat_rejected_kw,
            "removedKw": removed_kw,
            "loadKw": load_kw,
            "capacityKw": capacity_kw,
            "deficitKw": deficit_kw,
            "cop": cop,
            "freeCoolingFraction": free,
            "envelopeKw": env_kw,
            "crahFlowM3s": crah_flow,
            "demandFlowM3s": demand_flow,
            "airflowRatio": ratio,
            "maxInlet": max(new_inlet),
            "netKw": net_kw,
            "supplyRateKPerMin": d_sup / dt * 60.0,
            "plantAvail": m.plant_avail,
            "chillerAvail": m.chiller_avail,
            "crahAvail": m.crah_avail,
        }
        return self.out

    def settle(self, seconds: int = 1800, dt: float = 5.0):
        """Run quietly to a realistic warmed-up starting state."""
        for _ in range(int(seconds / dt)):
            self.step(dt)

    def clone(self) -> "DigitalTwinPhysics":
        return copy.deepcopy(self)

    def max_inlet(self) -> float:
        return max(r["inletTemp"] for r in self.racks)

    # ── serialisation ──────────────────────────────────────────────────────
    def rack_view(self) -> List[Dict[str, Any]]:
        lim = self.inlet_limit
        out = []
        for r in self.racks:
            t = r["inletTemp"]
            status = "Critical" if t >= self.allowable_limit else "Warning" if t >= lim else "Safe"
            out.append({
                "id": r["id"], "code": r["code"], "name": r["name"], "type": r["type"],
                "typeLabel": r["typeLabel"], "zone": r["zone"],
                "util": round(r["util"], 1),
                "powerKw": round(r["powerKw"], 2),
                "pmaxKw": round(r["pmaxKw"], 2),
                "inletTemp": round(t, 2),
                "exhaustTemp": round(r["exhaustTemp"], 2),
                "airflowCfm": round(r["airflowM3s"] * P.M3S_TO_CFM, 0),
                "airflowFactor": round(r["airflowFactor"], 2),
                "powerCapKw": r["powerCapKw"],
                "recircPercent": round(r["recirc"] * 100.0, 1),
                "heatPulseKw": round(r["heatPulseKw"], 2),
                "inletOffset": round(r["inletOffset"], 2),
                "off": r["off"],
                "status": status,
            })
        return out

    def facility_view(self) -> Dict[str, Any]:
        o = self.out
        return {
            "supplySetpoint": round(self.supply_setpoint, 2),
            "supplyTemp": round(self.supply_temp, 2),
            "crahFraction": round(self.crah_fraction, 3),
            "crahFlowCfm": round(o.get("crahFlowM3s", 0.0) * P.M3S_TO_CFM, 0),
            "demandFlowCfm": round(o.get("demandFlowM3s", 0.0) * P.M3S_TO_CFM, 0),
            "airflowRatio": round(o.get("airflowRatio", 0.0), 3),
            "itKw": round(o.get("itKw", 0.0), 2),
            "coolingKw": round(o.get("coolingKw", 0.0), 2),
            "chillerKw": round(o.get("chillerKw", 0.0), 2),
            "fansKw": round(o.get("fansKw", 0.0), 2),
            "pumpsKw": round(o.get("pumpsKw", 0.0), 2),
            "facilityKw": round(o.get("facilityKw", 0.0), 2),
            "pue": round(o.get("pue", 1.0), 3),
            "cop": round(o.get("cop", 0.0), 2),
            "freeCoolingPercent": round(o.get("freeCoolingFraction", 0.0) * 100.0, 1),
            "capacityKw": round(o.get("capacityKw", 0.0), 1),
            "loadKw": round(o.get("loadKw", 0.0), 1),
            "deficitKw": round(o.get("deficitKw", 0.0), 2),
            "designItKw": round(self.design_it_kw, 1),
            "inletLimit": self.inlet_limit,
            "allowableLimit": self.allowable_limit,
        }
