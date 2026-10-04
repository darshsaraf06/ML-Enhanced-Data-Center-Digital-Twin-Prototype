"""
Climate engine: outside dry-bulb temperature, humidity and wet-bulb for the twin.

Each climate profile has a daily cycle (cosine with the peak at 15:00) and a small
seeded random walk, so runs with the same seed see identical weather.
Operators can override temperature or humidity during a Simulation run.
"""

import math
from typing import Any, Dict, Optional

import numpy as np


def calculate_wet_bulb(t_dry: float, rh: float) -> float:
    """Wet-bulb temperature (C) using Stull's (2011) empirical formula.
    Valid for RH 5-99 % and -20 to 50 C."""
    rh = max(1.0, min(99.0, rh))
    tw = (
        t_dry * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t_dry + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(min(tw, t_dry), 2)


def calculate_air_enthalpy(t_dry: float, rh: float) -> float:
    """Approximate moist air enthalpy (kJ/kg dry air)."""
    es = 0.61078 * math.exp((17.27 * t_dry) / (t_dry + 237.3))
    e = (rh / 100.0) * es
    w = 0.622 * e / (101.325 - e)
    return round(1.006 * t_dry + w * (2501.0 + 1.86 * t_dry), 2)


CLIMATES: Dict[str, Dict[str, Any]] = {
    "temperate": {
        "id": "temperate", "name": "Temperate",
        "meanTemp": 24.0, "dailySwing": 4.0, "humidity": 60.0,
        "description": "Mild conditions similar to an inland Indian plateau city. Chillers work efficiently.",
    },
    "coastal_monsoon": {
        "id": "coastal_monsoon", "name": "Coastal monsoon",
        "meanTemp": 30.0, "dailySwing": 3.0, "humidity": 80.0,
        "description": "Warm and very humid. High wet-bulb temperature makes the cooling tower and chiller work harder and use more water.",
    },
    "hot_desert": {
        "id": "hot_desert", "name": "Hot desert",
        "meanTemp": 38.0, "dailySwing": 7.0, "humidity": 18.0,
        "description": "Very hot but dry. Wet-bulb stays moderate, so a water-cooled plant copes, but water evaporation rises.",
    },
    "nordic_cold": {
        "id": "nordic_cold", "name": "Nordic cold",
        "meanTemp": 4.0, "dailySwing": 3.0, "humidity": 75.0,
        "description": "Cold outside air allows the cooling tower to cool the water directly (free cooling); chillers mostly rest.",
    },
    "extreme_heat": {
        "id": "extreme_heat", "name": "Extreme humid heat",
        "meanTemp": 38.0, "dailySwing": 4.0, "humidity": 55.0,
        "description": "Pre-monsoon heat with high humidity. Wet-bulb near 30 C reduces chiller capacity; hotspots appear when workload is high.",
    },
}

DEFAULT_CLIMATE = "temperate"
START_HOUR = 12.0      # simulated runs start at 12:00 local time


class ClimateEngine:
    def __init__(self, climate_id: str = DEFAULT_CLIMATE, seed: int = 42):
        self.climate_id = climate_id if climate_id in CLIMATES else DEFAULT_CLIMATE
        self.rng = np.random.default_rng(seed + 1009)
        self.noise = 0.0
        self.temp_override: Optional[float] = None
        self.humidity_override: Optional[float] = None
        self.temp_delta = 0.0          # from events (heatwave, smoke)
        self.humidity_set: Optional[float] = None   # from events (cyclone)
        self.outside_temp = CLIMATES[self.climate_id]["meanTemp"]
        self.humidity = CLIMATES[self.climate_id]["humidity"]
        self.wet_bulb = calculate_wet_bulb(self.outside_temp, self.humidity)

    def set_climate(self, climate_id: str):
        if climate_id in CLIMATES:
            self.climate_id = climate_id

    def update(self, t_seconds: float):
        """Advance the weather to simulated time t (call once per second)."""
        c = CLIMATES[self.climate_id]
        hour = (START_HOUR + t_seconds / 3600.0) % 24.0
        daily = c["dailySwing"] * math.cos(2.0 * math.pi * (hour - 15.0) / 24.0)
        # slow seeded random walk with mean reversion, std about 0.6 C
        self.noise += -self.noise / 1800.0 + 0.035 * float(self.rng.standard_normal())
        base_t = c["meanTemp"] + daily + self.noise
        t = self.temp_override if self.temp_override is not None else base_t
        t += self.temp_delta
        # relative humidity falls as the day warms
        rh = c["humidity"] - 1.5 * daily
        if self.humidity_override is not None:
            rh = self.humidity_override
        if self.humidity_set is not None:
            rh = self.humidity_set
        self.outside_temp = t
        self.humidity = max(5.0, min(99.0, rh))
        self.wet_bulb = calculate_wet_bulb(self.outside_temp, self.humidity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "climateId": self.climate_id,
            "climateName": CLIMATES[self.climate_id]["name"],
            "outsideTemp": round(self.outside_temp, 2),
            "humidity": round(self.humidity, 1),
            "wetBulb": round(self.wet_bulb, 2),
            "tempOverride": self.temp_override,
            "humidityOverride": self.humidity_override,
        }
