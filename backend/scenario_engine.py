"""
Event engine: time-based disturbances for the digital twin.

Events never overwrite the twin's controls. Each step the engine builds a fresh
Modifiers object (availability of chillers, CRAH airflow, workload changes, ...)
from the events that are active at that simulated time. Optimizer actions and
operator edits live on the twin itself and are therefore never undone by an event.
"""

from typing import Any, Dict, List, Optional

import numpy as np

from digital_twin import Modifiers

GPU_TYPES = {"gpu", "infer", "compute"}


def _ramp(x: float, x0: float, x1: float) -> float:
    if x <= x0:
        return 0.0
    if x >= x1:
        return 1.0
    return (x - x0) / (x1 - x0)


EVENT_LIBRARY: Dict[str, Dict[str, Any]] = {
    "cooling_failure": {
        "name": "Cooling failure", "category": "Cooling", "severity": "Critical", "durationS": 600,
        "description": "A chiller compressor trips. Chilled-water cooling stops for 8 minutes, then the chiller restarts over 2 minutes.",
    },
    "power_loss": {
        "name": "Power loss", "category": "Power", "severity": "Critical", "durationS": 420,
        "description": "Utility power is lost. CRAH fans stop for 20 s until generators start; chillers stay locked out for 5 minutes and restart over 2 minutes. IT stays on UPS.",
    },
    "heatwave": {
        "name": "Heatwave", "category": "Environment", "severity": "Warning", "durationS": 2400,
        "description": "Outside temperature rises by up to 8 C over 10 minutes and stays high for 40 minutes, raising wet-bulb and reducing chiller capacity and efficiency.",
    },
    "workload_spike": {
        "name": "Workload spike", "category": "Workload", "severity": "Warning", "durationS": 900,
        "description": "A burst of AI and analytics jobs adds 35 utilization points to GPU, inference and compute racks and 10 points elsewhere for 15 minutes.",
    },
    "flood": {
        "name": "Flood", "category": "Environment", "severity": "Critical", "durationS": 1200,
        "description": "Water ingress takes half of the CRAH units offline and one chilled-water pump set (60 % chiller availability) for 20 minutes.",
    },
    "wildfire_smoke": {
        "name": "Wildfire smoke", "category": "Environment", "severity": "Warning", "durationS": 1800,
        "description": "Smoke loads filters (CRAH airflow 80 %), free cooling is disabled and outside temperature rises 3 C for 30 minutes.",
    },
    "earthquake": {
        "name": "Earthquake", "category": "Power", "severity": "Critical", "durationS": 900,
        "description": "Seismic protection shuts down zone B racks for 3 minutes; they restart at full load for 6 minutes. One chiller trips (50 % availability) for 10 minutes.",
    },
    "cyclone": {
        "name": "Cyclone", "category": "Environment", "severity": "Warning", "durationS": 2400,
        "description": "Humidity reaches 95 %, CRAH airflow drops to 85 %, and two 90 s power dips trip the chillers.",
    },
    "containment_breach": {
        "name": "Containment breach", "category": "Cooling", "severity": "Warning", "durationS": 1200,
        "description": "Missing blanking panels let hot exhaust leak into the inlets of racks 03 and 04 (25 % extra recirculation) for 20 minutes.",
    },
    "fan_degradation": {
        "name": "CRAH fan degradation", "category": "Cooling", "severity": "Warning", "durationS": 1500,
        "description": "Worn CRAH fan drives deliver only 60 % of commanded airflow for 25 minutes.",
    },
    "rack_overload": {
        "name": "Rack overload", "category": "Workload", "severity": "Warning", "durationS": 900,
        "description": "A runaway process pins rack 05 at 100 % and a faulty power supply adds 2 kW of heat for 15 minutes.",
    },
}

EVENT_ORDER = ["cooling_failure", "power_loss", "heatwave", "workload_spike", "flood", "wildfire_smoke",
               "earthquake", "cyclone", "containment_breach", "fan_degradation", "rack_overload"]

DEMO_SCRIPT = [("workload_spike", 300), ("cooling_failure", 1500), ("heatwave", 2400)]


def apply_event(event_id: str, elapsed: float, m: Modifiers, twin, climate) -> None:
    """Add the effect of one active event, `elapsed` seconds after it started."""
    racks = twin.racks
    if event_id == "cooling_failure":
        m.chiller_avail *= _ramp(elapsed, 480, 600)
    elif event_id == "power_loss":
        if elapsed < 20:
            m.plant_avail = 0.0
            m.crah_avail = 0.0
        m.chiller_avail *= _ramp(elapsed, 300, 420)
    elif event_id == "heatwave":
        climate.temp_delta += 8.0 * _ramp(elapsed, 0, 600) * (1.0 - _ramp(elapsed, 2100, 2400))
    elif event_id == "workload_spike":
        k = _ramp(elapsed, 0, 60)
        for r in racks:
            d = 35.0 if r["type"] in GPU_TYPES else 10.0
            m.util_delta[r["id"]] = m.util_delta.get(r["id"], 0.0) + d * k
    elif event_id == "flood":
        m.crah_avail *= 0.5
        m.chiller_avail *= 0.6
    elif event_id == "wildfire_smoke":
        m.economizer_ok = False
        m.crah_avail *= 0.8
        climate.temp_delta += 3.0
    elif event_id == "earthquake":
        zone_b = [r["id"] for r in racks if r["zone"] == "B"]
        if elapsed < 180:
            m.racks_off.update(zone_b)
        elif elapsed < 540:
            for rid in zone_b:
                m.util_set[rid] = 100.0
        if elapsed < 600:
            m.chiller_avail *= 0.5
    elif event_id == "cyclone":
        climate.humidity_set = 95.0
        climate.temp_delta -= 3.0
        m.crah_avail *= 0.85
        if 300 <= elapsed < 390 or 1200 <= elapsed < 1290:
            m.chiller_avail = 0.0
    elif event_id == "containment_breach":
        for rid in (3, 4):
            if rid <= len(racks):
                m.recirc_add[rid] = m.recirc_add.get(rid, 0.0) + 0.25
    elif event_id == "fan_degradation":
        m.crah_avail *= 0.6
    elif event_id == "rack_overload":
        rid = 5 if len(racks) >= 5 else len(racks)
        m.util_set[rid] = 100.0
        m.heat_add[rid] = m.heat_add.get(rid, 0.0) + 2.0


class EventSchedule:
    """Seeded list of scheduled events. Deterministic for a given seed and selection."""

    def __init__(self, selection: Any = "none", duration_s: int = 3600, seed: int = 42, demo: bool = False):
        self.items: List[Dict[str, Any]] = []
        if demo:
            for event_id, start in DEMO_SCRIPT:
                if start < duration_s:
                    self.add(event_id, start, source="Demonstration script")
            return
        if selection in (None, "none", [], ""):
            return
        if selection == "random":
            rng = np.random.default_rng(seed + 7919)
            count = max(1, int(round(duration_s / 1800.0)))
            lo, hi = 300, max(301, duration_s - 600)
            starts = sorted(int(x) for x in rng.uniform(lo, hi, size=count))
            for start in starts:
                event_id = EVENT_ORDER[int(rng.integers(0, len(EVENT_ORDER)))]
                self.add(event_id, start, source="Random event")
            return
        chosen = [selection] if isinstance(selection, str) else list(selection)
        chosen = [e for e in chosen if e in EVENT_LIBRARY]
        if not chosen:
            return
        first = 600 if duration_s > 1200 else max(60, duration_s // 4)
        gap = max(300, (duration_s - first - 300) // max(1, len(chosen)))
        for k, event_id in enumerate(chosen):
            self.add(event_id, first + k * gap, source="Chosen at setup")

    def add(self, event_id: str, start: int, source: str = "Operator") -> Optional[Dict[str, Any]]:
        if event_id not in EVENT_LIBRARY:
            return None
        lib = EVENT_LIBRARY[event_id]
        item = {"eventId": event_id, "name": lib["name"], "start": int(start),
                "end": int(start) + int(lib["durationS"]), "source": source,
                "category": lib["category"], "severity": lib["severity"]}
        self.items.append(item)
        self.items.sort(key=lambda e: e["start"])
        return item

    def active(self, t: int) -> List[Dict[str, Any]]:
        return [e for e in self.items if e["start"] <= t < e["end"]]

    def starting(self, t: int) -> List[Dict[str, Any]]:
        return [e for e in self.items if e["start"] == t]

    def ending(self, t: int) -> List[Dict[str, Any]]:
        return [e for e in self.items if e["end"] == t]

    def modifiers(self, t: int, twin, climate) -> Modifiers:
        m = Modifiers()
        climate.temp_delta = 0.0
        climate.humidity_set = None
        for e in self.active(t):
            apply_event(e["eventId"], t - e["start"], m, twin, climate)
        return m

    def to_list(self) -> List[Dict[str, Any]]:
        return [dict(e) for e in self.items]


def event_catalog() -> List[Dict[str, Any]]:
    return [{"id": k, **EVENT_LIBRARY[k]} for k in EVENT_ORDER]
