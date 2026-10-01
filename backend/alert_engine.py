"""
Alert and Event Logging Engine.
Tracks real-time thermal threshold breaches, predictive early warnings,
equipment degradation, and optimization intervention events.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional


class AlertEngine:
    def __init__(self, max_history: int = 150):
        self.max_history = max_history
        self.events: List[Dict[str, Any]] = []
        self._last_breached_racks = set()

    def reset(self):
        self.events = []
        self._last_breached_racks = set()

    def record_event(
        self,
        severity: str,
        event_type: str,
        description: str,
        rack_id: Optional[str] = None,
        sim_time_str: str = "00:00:00",
        action_taken: str = "Logged",
    ) -> Dict[str, Any]:
        """Record an alert event into history."""
        event = {
            "id": len(self.events) + 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "simTime": sim_time_str,
            "rackId": rack_id or "DC-HALL",
            "severity": severity.upper(),  # CRITICAL, WARNING, INFO
            "eventType": event_type,
            "description": description,
            "actionTaken": action_taken,
        }
        self.events.insert(0, event)
        if len(self.events) > self.max_history:
            self.events.pop()
        return event

    def evaluate_telemetry(self, twin_physics, forecast_data: Dict[str, Any], sim_time_str: str):
        """
        Evaluate live state and predictive forecast to automatically raise alerts.
        """
        threshold = twin_physics.safety_threshold_temp
        crit_threshold = twin_physics.critical_threshold_temp

        # 1. Check current rack temperatures
        for rack in twin_physics.racks:
            r_id = f"R{rack['id']:02d}"
            temp = rack["temp"]

            if temp >= crit_threshold:
                if (r_id, "CRITICAL") not in self._last_breached_racks:
                    self.record_event(
                        severity="CRITICAL",
                        event_type="Thermal Threshold Exceeded",
                        description=f"{rack['name']} reached critical core temperature of {temp:.1f}°C (Threshold: {crit_threshold:.1f}°C). Emergency cooling engaged.",
                        rack_id=r_id,
                        sim_time_str=sim_time_str,
                        action_taken="Auto-Intervention Triggered",
                    )
                    self._last_breached_racks.add((r_id, "CRITICAL"))

            elif temp >= threshold:
                if (r_id, "WARNING") not in self._last_breached_racks:
                    self.record_event(
                        severity="WARNING",
                        event_type="Warning Threshold Approaching",
                        description=f"{rack['name']} elevated to {temp:.1f}°C. Exceeds ASHRAE recommended range.",
                        rack_id=r_id,
                        sim_time_str=sim_time_str,
                        action_taken="Monitoring",
                    )
                    self._last_breached_racks.add((r_id, "WARNING"))
            else:
                self._last_breached_racks.discard((r_id, "CRITICAL"))
                self._last_breached_racks.discard((r_id, "WARNING"))

        # 2. Check predictive ML forecast for early warnings
        for rf in forecast_data.get("rackForecasts", []):
            r_id = f"R{rf['rackId']:02d}"
            prob = rf.get("hotspotProbability", 0)
            time_to_breach = rf.get("timeToBreachMin")

            if prob >= 70 and time_to_breach:
                key = (r_id, f"PREDICT_{time_to_breach}m")
                if key not in self._last_breached_racks:
                    self.record_event(
                        severity="CRITICAL",
                        event_type="Predictive Hotspot Warning",
                        description=f"{rf['rackName']} predicted to exceed {threshold:.1f}°C in approx {time_to_breach} minutes (Risk: {prob}%). Proactive mitigation recommended.",
                        rack_id=r_id,
                        sim_time_str=sim_time_str,
                        action_taken="Counterfactual Analysis Recommended",
                    )
                    self._last_breached_racks.add(key)

    def get_events(self, severity_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if severity_filter and severity_filter.upper() != "ALL":
            return [e for e in self.events if e["severity"] == severity_filter.upper()]
        return self.events

    def get_summary(self) -> Dict[str, Any]:
        critical_count = sum(1 for e in self.events if e["severity"] == "CRITICAL")
        warning_count = sum(1 for e in self.events if e["severity"] == "WARNING")
        info_count = sum(1 for e in self.events if e["severity"] == "INFO")
        return {
            "totalCount": len(self.events),
            "criticalCount": critical_count,
            "warningCount": warning_count,
            "infoCount": info_count,
            "recentEvents": self.events[:25],
        }
