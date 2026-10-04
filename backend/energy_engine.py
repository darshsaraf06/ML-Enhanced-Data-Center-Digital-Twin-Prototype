"""
Resource accounting for one simulated run.

Integrates the twin's power outputs every physics step:
  energy (IT, chiller, fans, pumps, total), PUE = total / IT energy,
  water = evaporation + blowdown from the heat rejected in the cooling tower,
        evaporation (kg) = heat rejected (kJ) * f_evap(wet-bulb) / 2430 kJ/kg,
        blowdown = evaporation / (cycles of concentration - 1),  1 kg = 1 L,
  WUE = water (L) / IT energy (kWh),
  carbon = total energy * grid emission factor,
  cost = total energy * electricity price + water (kL) * water price,
  thermal: minutes with any rack inlet above the limit, hotspot episodes, peak inlet.
"""

from typing import Any, Dict, List

import model_params as P


class ResourceMeter:
    def __init__(self, racks: List[Dict[str, Any]], limit: float,
                 grid_factor: float = P.DEFAULT_GRID_FACTOR_KG_PER_KWH,
                 price_kwh: float = P.DEFAULT_ELECTRICITY_INR_PER_KWH,
                 price_water_kl: float = P.DEFAULT_WATER_INR_PER_KL):
        self.limit = limit
        self.grid_factor = grid_factor
        self.price_kwh = price_kwh
        self.price_water_kl = price_water_kl
        self.seconds = 0.0
        self.it_kwh = self.chiller_kwh = self.fans_kwh = self.pumps_kwh = 0.0
        self.facility_kwh = self.heat_rejected_kwh = 0.0
        self.water_l = 0.0
        self.seconds_above = 0.0
        self.hotspot_events = 0
        self.peak_inlet = -1e9
        self.peak_inlet_time = 0
        self._above: Dict[str, bool] = {}
        self.racks = {r["code"]: {"code": r["code"], "peakInlet": -1e9, "sumInlet": 0.0, "secondsAbove": 0.0,
                                  "energyKwh": 0.0, "sumUtil": 0.0, "peakExhaust": -1e9, "hotspotEvents": 0}
                      for r in racks}

    def update(self, t: float, twin, wet_bulb: float, dt: float = P.PHYSICS_DT_S):
        o = twin.out
        h = dt / 3600.0
        self.seconds += dt
        self.it_kwh += o["itKw"] * h
        self.chiller_kwh += o["chillerKw"] * h
        self.fans_kwh += o["fansKw"] * h
        self.pumps_kwh += o["pumpsKw"] * h
        self.facility_kwh += o["facilityKw"] * h
        rejected_kj = o["heatRejectedKw"] * dt
        self.heat_rejected_kwh += o["heatRejectedKw"] * h
        evap = rejected_kj * P.evaporative_fraction(wet_bulb) / P.LATENT_HEAT_KJ_KG
        self.water_l += evap * (1.0 + 1.0 / (P.CYCLES_OF_CONCENTRATION - 1.0))
        any_above = False
        for r in twin.racks:
            code, temp = r["code"], r["inletTemp"]
            st = self.racks[code]
            st["peakInlet"] = max(st["peakInlet"], temp)
            st["peakExhaust"] = max(st["peakExhaust"], r["exhaustTemp"])
            st["sumInlet"] += temp * dt
            st["sumUtil"] += r["util"] * dt
            st["energyKwh"] += r["powerKw"] * h
            above = temp > self.limit
            if above:
                st["secondsAbove"] += dt
                any_above = True
            if above and not self._above.get(code):
                self.hotspot_events += 1
                st["hotspotEvents"] += 1
            self._above[code] = above
            if temp > self.peak_inlet:
                self.peak_inlet = temp
                self.peak_inlet_time = int(t)
        if any_above:
            self.seconds_above += dt

    def summary(self) -> Dict[str, Any]:
        cooling = self.chiller_kwh + self.fans_kwh + self.pumps_kwh
        carbon = self.facility_kwh * self.grid_factor
        cost_energy = self.facility_kwh * self.price_kwh
        cost_water = self.water_l / 1000.0 * self.price_water_kl
        secs = max(1.0, self.seconds)
        return {
            "durationS": round(self.seconds),
            "itKwh": round(self.it_kwh, 3),
            "chillerKwh": round(self.chiller_kwh, 3),
            "fansKwh": round(self.fans_kwh, 3),
            "pumpsKwh": round(self.pumps_kwh, 3),
            "coolingKwh": round(cooling, 3),
            "totalKwh": round(self.facility_kwh, 3),
            "pue": round(self.facility_kwh / self.it_kwh, 4) if self.it_kwh > 0 else None,
            "heatRejectedKwh": round(self.heat_rejected_kwh, 3),
            "waterL": round(self.water_l, 2),
            "wueLPerKwh": round(self.water_l / self.it_kwh, 4) if self.it_kwh > 0 else None,
            "carbonKg": round(carbon, 3),
            "costInr": round(cost_energy + cost_water, 2),
            "costEnergyInr": round(cost_energy, 2),
            "costWaterInr": round(cost_water, 2),
            "minutesAboveLimit": round(self.seconds_above / 60.0, 2),
            "hotspotEvents": self.hotspot_events,
            "peakInlet": round(self.peak_inlet, 2) if self.peak_inlet > -1e8 else None,
            "peakInletTime": self.peak_inlet_time,
            "assumptions": {"gridFactorKgPerKwh": self.grid_factor, "electricityInrPerKwh": self.price_kwh,
                            "waterInrPerKl": self.price_water_kl, "inletLimitC": self.limit},
            "racks": [{
                "code": st["code"],
                "peakInlet": round(st["peakInlet"], 2),
                "avgInlet": round(st["sumInlet"] / secs, 2),
                "peakExhaust": round(st["peakExhaust"], 2),
                "avgUtil": round(st["sumUtil"] / secs, 1),
                "energyKwh": round(st["energyKwh"], 3),
                "minutesAboveLimit": round(st["secondsAbove"] / 60.0, 2),
                "hotspotEvents": st["hotspotEvents"],
            } for st in self.racks.values()],
        }
