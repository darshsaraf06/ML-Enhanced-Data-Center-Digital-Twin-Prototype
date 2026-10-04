"""
Structured event log.

Every event has: time, severity (Info, Warning, Critical), category, source
(rack, zone or facility), a short title, a one-line detail and related values.
Events of the same kind and severity that occur within 30 simulated seconds are
merged into one expandable entry (for example "Critical, Thermal: 6 racks above
limit (R02, R04, ...)"). Forecast warnings use a per-rack cooldown: a rack is not
warned again while its warning is still active.
"""

from typing import Any, Callable, Dict, List, Optional

import model_params as P

SEVERITIES = ["Info", "Warning", "Critical"]
CATEGORIES = ["Thermal", "Forecast", "Cooling", "Power", "Workload", "Environment",
              "Decision", "User action", "System"]


def fmt_time(t: float) -> str:
    t = int(max(0, t))
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def rack_list_text(codes: List[str], limit: int = 4) -> str:
    if len(codes) <= limit:
        return ", ".join(codes)
    return ", ".join(codes[:limit]) + f" and {len(codes) - limit} more"


class EventLog:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self._next_id = 1
        self._thermal_state: Dict[str, str] = {}      # rack code -> "Warning" | "Critical"
        self._forecast_active: Dict[str, float] = {}  # rack code -> time warning was raised

    # ── core ───────────────────────────────────────────────────────────────
    def log(self, t: float, kind: str, severity: str, category: str, title: str, detail: str,
            source_kind: str = "facility", source_id: str = "Facility",
            values: Optional[Dict[str, Any]] = None, racks: Optional[List[str]] = None,
            group_title: Optional[Callable[[List[str], int], str]] = None) -> Dict[str, Any]:
        values = values or {}
        racks = list(racks or [])
        child = {"t": int(t), "time": fmt_time(t), "title": title, "detail": detail,
                 "racks": racks, "values": values}
        if group_title is not None:
            for ev in reversed(self.events[-30:]):
                if (ev["kind"] == kind and ev["severity"] == severity
                        and int(t) - ev["t"] <= P.EVENT_MERGE_WINDOW_S):
                    ev["items"].append(child)
                    for code in racks:
                        if code not in ev["racks"]:
                            ev["racks"].append(code)
                    ev["count"] = len(ev["items"])
                    ev["lastT"] = int(t)
                    ev["title"] = group_title(ev["racks"], ev["count"])
                    ev["detail"] = detail if ev["count"] == 1 else f"{ev['count']} related events between {ev['time']} and {fmt_time(t)}. Latest: {detail}"
                    if len(ev["racks"]) > 1:
                        ev["sourceKind"], ev["sourceId"] = "facility", "Facility"
                    ev["values"] = {**ev["values"], **values}
                    return ev
        ev = {
            "id": self._next_id, "t": int(t), "lastT": int(t), "time": fmt_time(t),
            "severity": severity, "category": category, "kind": kind,
            "sourceKind": source_kind, "sourceId": source_id,
            "title": title if group_title is None else group_title(racks, 1),
            "detail": detail, "values": values, "racks": racks,
            "count": 1, "items": [child],
        }
        self._next_id += 1
        self.events.append(ev)
        return ev

    # ── automatic evaluations ──────────────────────────────────────────────
    def evaluate_thermal(self, t: float, twin) -> None:
        limit, allowable = twin.inlet_limit, twin.allowable_limit
        for rack in twin.racks:
            code, temp = rack["code"], rack["inletTemp"]
            prev = self._thermal_state.get(code)
            if temp >= allowable:
                state = "Critical"
            elif temp >= limit:
                state = "Warning"
            elif prev and temp > limit - 0.3:      # hysteresis: stay until 0.3 K below limit
                state = "Warning"
            else:
                state = None
            if state and state != prev and (prev is None or SEVERITIES.index(state) > SEVERITIES.index(prev)):
                lim = allowable if state == "Critical" else limit
                self.log(t, f"thermal_{state.lower()}", state, "Thermal",
                         f"{code} inlet above {lim:.0f} C",
                         f"{code} inlet reached {temp:.1f} C (limit {lim:.1f} C).",
                         "rack", code, {"inletTemp": round(temp, 2), "limit": lim}, [code],
                         group_title=lambda rs, n, s=state, l=lim: (
                             f"{rs[0]} inlet above {l:.0f} C" if len(rs) == 1
                             else f"{len(rs)} racks above {l:.0f} C ({rack_list_text(rs)})"))
            if state is None and prev is not None:
                self.log(t, "thermal_clear", "Info", "Thermal", f"{code} back within limit",
                         f"{code} inlet fell to {temp:.1f} C, below the {limit:.1f} C limit.",
                         "rack", code, {"inletTemp": round(temp, 2)}, [code],
                         group_title=lambda rs, n: (f"{rs[0]} back within limit" if len(rs) == 1
                                                    else f"{len(rs)} racks back within limit ({rack_list_text(rs)})"))
            if state is None:
                self._thermal_state.pop(code, None)
            else:
                self._thermal_state[code] = state

    def forecast_warning(self, t: float, code: str, value: float, horizon_min: int, limit: float,
                         probability: float) -> bool:
        """Log a forecast warning unless one is already active for this rack. Returns True if logged."""
        if code in self._forecast_active:
            return False
        self._forecast_active[code] = t
        self.log(t, "forecast_breach", "Warning", "Forecast",
                 f"{code} forecast to exceed {limit:.0f} C",
                 f"{code} inlet forecast {value:.1f} C in about {horizon_min} min (limit {limit:.1f} C, probability {probability:.0f} %).",
                 "rack", code, {"forecastTemp": round(value, 2), "horizonMin": horizon_min,
                                "probabilityPercent": round(probability, 1), "limit": limit}, [code],
                 group_title=lambda rs, n, l=limit: (f"{rs[0]} forecast to exceed {l:.0f} C" if len(rs) == 1
                                                     else f"{len(rs)} racks forecast to exceed {l:.0f} C ({rack_list_text(rs)})"))
        return True

    def clear_forecast(self, code: str) -> None:
        self._forecast_active.pop(code, None)

    def forecast_active(self, code: str) -> bool:
        return code in self._forecast_active

    # ── views ──────────────────────────────────────────────────────────────
    def counts(self) -> Dict[str, Any]:
        by_cat = {c: 0 for c in CATEGORIES}
        by_sev = {s: 0 for s in SEVERITIES}
        for ev in self.events:
            by_cat[ev["category"]] = by_cat.get(ev["category"], 0) + 1
            by_sev[ev["severity"]] = by_sev.get(ev["severity"], 0) + 1
        return {"total": len(self.events), "byCategory": by_cat, "bySeverity": by_sev}

    def recent(self, n: int = 200) -> List[Dict[str, Any]]:
        return list(reversed(self.events[-n:]))
