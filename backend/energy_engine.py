"""
Energy Analytics & Sustainability Engine.
Integrates IT power and CRAH/Chiller cooling power into cumulative kWh.
Tracks PUE, baseline comparison, cost ($0.14/kWh default), and carbon emissions (0.385 kg CO2e/kWh).
"""

from typing import Dict, List, Any


class EnergyEngine:
    def __init__(self):
        self.kwh_rate = 0.14          # USD per kWh
        self.carbon_intensity = 0.385  # kg CO2e per kWh (grid average)
        self.reset()

    def reset(self):
        self.cumulative_it_kwh = 0.0
        self.cumulative_cooling_kwh = 0.0
        self.cumulative_facility_kwh = 0.0
        self.baseline_unoptimized_kwh = 0.0
        self.peak_total_kw = 0.0
        self.peak_cooling_kw = 0.0
        self.history_records = []
        self.ticks_count = 0
        self.pue_sum = 0.0

    def update(self, snapshot: Dict[str, Any], dt_sec: float = 1.0):
        """Accumulate electrical energy usage from snapshot."""
        self.ticks_count += 1
        hours = dt_sec / 3600.0

        it_kw = snapshot.get("totalITPower", 0.0)
        cool_kw = snapshot.get("coolingPower", 0.0)
        facility_kw = snapshot.get("totalFacilityPower", it_kw + cool_kw)

        it_kwh = it_kw * hours
        cool_kwh = cool_kw * hours
        fac_kwh = facility_kw * hours

        self.cumulative_it_kwh += it_kwh
        self.cumulative_cooling_kwh += cool_kwh
        self.cumulative_facility_kwh += fac_kwh

        # Baseline counterfactual: unoptimized fixed 100% cooling without ML dynamic throttling
        # Unoptimized runs chiller at lower setpoint + fixed high fan CFM (+28% cooling power)
        unopt_cool_kw = cool_kw * 1.32
        self.baseline_unoptimized_kwh += (it_kw + unopt_cool_kw) * hours

        self.peak_total_kw = max(self.peak_total_kw, facility_kw)
        self.peak_cooling_kw = max(self.peak_cooling_kw, cool_kw)

        pue = snapshot.get("pue", 1.0)
        self.pue_sum += pue

        # Keep history of energy snapshots
        if self.ticks_count % 3 == 0:
            self.history_records.append({
                "timestamp": snapshot.get("timestamp", ""),
                "itKW": round(it_kw, 2),
                "coolingKW": round(cool_kw, 2),
                "totalKW": round(facility_kw, 2),
                "pue": round(pue, 3),
            })
            if len(self.history_records) > 60:
                self.history_records.pop(0)

    def get_summary(self) -> Dict[str, Any]:
        """Return full energy metrics for dashboard and reports."""
        tot = max(0.001, self.cumulative_facility_kwh)
        cooling_pct = round((self.cumulative_cooling_kwh / tot) * 100.0, 1) if tot > 0 else 0.0
        avg_pue = round(self.pue_sum / max(1, self.ticks_count), 3)

        energy_saved_kwh = max(0.0, round(self.baseline_unoptimized_kwh - self.cumulative_facility_kwh, 3))
        saving_pct = (
            round((energy_saved_kwh / max(0.001, self.baseline_unoptimized_kwh)) * 100.0, 1)
            if self.baseline_unoptimized_kwh > 0 else 0.0
        )

        cost_usd = round(self.cumulative_facility_kwh * self.kwh_rate, 2)
        cost_saved_usd = round(energy_saved_kwh * self.kwh_rate, 2)
        carbon_kg = round(self.cumulative_facility_kwh * self.carbon_intensity, 2)
        carbon_saved_kg = round(energy_saved_kwh * self.carbon_intensity, 2)

        return {
            "totalITKWh": round(self.cumulative_it_kwh, 3),
            "totalCoolingKWh": round(self.cumulative_cooling_kwh, 3),
            "totalFacilityKWh": round(self.cumulative_facility_kwh, 3),
            "coolingPercentage": cooling_pct,
            "averagePUE": avg_pue,
            "peakPowerKW": round(self.peak_total_kw, 2),
            "peakCoolingPowerKW": round(self.peak_cooling_kw, 2),
            "baselineUnoptimizedKWh": round(self.baseline_unoptimized_kwh, 3),
            "energySavedKWh": energy_saved_kwh,
            "energySavingPercent": saving_pct,
            "operationalCostUSD": cost_usd,
            "costSavedUSD": cost_saved_usd,
            "carbonEmissionsKg": carbon_kg,
            "carbonSavedKg": carbon_saved_kg,
            "history": self.history_records,
        }
