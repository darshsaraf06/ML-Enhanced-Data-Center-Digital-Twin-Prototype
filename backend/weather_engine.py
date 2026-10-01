"""
Weather and Environmental Engine for Data Center Digital Twin.
Simulates thermodynamic psychrometric effects of ambient temperature and humidity
on chiller lift, heat rejection, cooling tower wet-bulb approach, and envelope heat leakage.
"""

import math
from typing import Dict, Any


def calculate_wet_bulb(t_dry: float, rh: float) -> float:
    """
    Calculate wet-bulb temperature using Stull's empirical psychrometric formula (°C).
    Valid for RH between 1% and 99% and temperatures between -20°C and 50°C.
    """
    rh = max(1.0, min(99.0, rh))
    tw = (
        t_dry * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t_dry + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh ** 1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return round(tw, 2)


def calculate_air_enthalpy(t_dry: float, rh: float) -> float:
    """Approximate moist air enthalpy (kJ/kg)."""
    # Saturation vapor pressure (kPa) via Magnus formula
    es = 0.61078 * math.exp((17.27 * t_dry) / (t_dry + 237.3))
    # Actual vapor pressure
    e = (rh / 100.0) * es
    # Humidity ratio W (kg water / kg dry air) at standard pressure 101.325 kPa
    w = 0.622 * e / (101.325 - e)
    # Enthalpy h = 1.006 * T + W * (2501 + 1.86 * T)
    h = 1.006 * t_dry + w * (2501.0 + 1.86 * t_dry)
    return round(h, 2)


WEATHER_PRESETS: Dict[str, Dict[str, Any]] = {
    "normal": {
        "id": "normal",
        "name": "Normal Ambient",
        "ambientTemp": 24.0,
        "humidity": 50.0,
        "description": "Standard temperate day. Optimal chiller operation, low ambient thermal infiltration.",
        "icon": "🌤️",
        "copMultiplier": 1.0,
    },
    "hot": {
        "id": "hot",
        "name": "Hot Weather",
        "ambientTemp": 35.0,
        "humidity": 70.0,
        "description": "Subtropical summer heat. Elevated chiller condenser lift, higher ambient infiltration.",
        "icon": "☀️",
        "copMultiplier": 0.82,
    },
    "extreme_heat": {
        "id": "extreme_heat",
        "name": "Extreme Heatwave",
        "ambientTemp": 42.0,
        "humidity": 80.0,
        "description": "Severe heat dome stress. High wet-bulb temperature severely penalises cooling tower heat rejection.",
        "icon": "🔥",
        "copMultiplier": 0.65,
    },
    "cool": {
        "id": "cool",
        "name": "Cool Weather",
        "ambientTemp": 15.0,
        "humidity": 45.0,
        "description": "Cool ambient allowing partial free-cooling (economiser) mode and maximal chiller COP.",
        "icon": "❄️",
        "copMultiplier": 1.18,
    },
    "high_humidity": {
        "id": "high_humidity",
        "name": "High Humidity",
        "ambientTemp": 27.0,
        "humidity": 90.0,
        "description": "High ambient moisture content. Limits evaporative cooling tower delta-T without extreme dry-bulb heat.",
        "icon": "💧",
        "copMultiplier": 0.88,
    },
}


class WeatherEngine:
    def __init__(self, preset: str = "normal"):
        self.preset_id = preset
        self.ambient_temp = 24.0
        self.humidity = 50.0
        self.load_preset(preset)

    def load_preset(self, preset_id: str):
        if preset_id in WEATHER_PRESETS:
            p = WEATHER_PRESETS[preset_id]
            self.preset_id = preset_id
            self.ambient_temp = float(p["ambientTemp"])
            self.humidity = float(p["humidity"])

    def set_custom(self, ambient_temp: float, humidity: float):
        self.preset_id = "custom"
        self.ambient_temp = round(float(ambient_temp), 1)
        self.humidity = round(float(humidity), 1)

    @property
    def wet_bulb_temp(self) -> float:
        return calculate_wet_bulb(self.ambient_temp, self.humidity)

    @property
    def enthalpy_kj_kg(self) -> float:
        return calculate_air_enthalpy(self.ambient_temp, self.humidity)

    def get_cop_derate_factor(self) -> float:
        """
        Thermodynamic COP factor for chillers based on wet-bulb lift.
        Standard baseline: 24°C dry bulb, 50% RH -> Twb ~ 17°C -> factor 1.0
        For each degree of wet-bulb rise above 17°C, cooling COP drops ~ 2.4%.
        """
        twb = self.wet_bulb_temp
        delta = twb - 17.0
        factor = 1.0 - (delta * 0.024)
        return max(0.45, min(1.30, round(factor, 3)))

    def to_dict(self) -> dict:
        return {
            "presetId": self.preset_id,
            "ambientTemp": self.ambient_temp,
            "humidity": self.humidity,
            "wetBulbTemp": self.wet_bulb_temp,
            "enthalpyKjKg": self.enthalpy_kj_kg,
            "copMultiplier": self.get_cop_derate_factor(),
            "presets": list(WEATHER_PRESETS.values()),
        }
