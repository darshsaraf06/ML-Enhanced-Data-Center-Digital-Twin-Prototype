"""
Deterministic simulation core.

A SimulationRun advances the twin in fixed 1 s physics steps. The same step function
drives the live run at every speed, Skip to End, the baseline runs and the solution
replays, so a given seed, event selection and list of operator commands always
produces the same result. Operator commands are queued and applied at the start of
the next step; their simulated time is recorded so replays can apply them at the
same moment.

Control policies:
  fixed       constant 18 C supply air and 100 % CRAH airflow (conventional, no prediction)
  reactive    21 C / 85 %; boosts to 17 C / 110 % once any inlet is within 1 K of the limit,
              releases after 5 minutes 3 K below the limit
  predictive  this project: ML forecasts every 30 s, hotspot decisions evaluated in cloned
              twins, and a 5-minute tuner that minimises energy with a 2.0 K safety margin
  random      used only to build the training dataset (seeded random setpoints)
"""

from typing import Any, Dict, List, Optional

import numpy as np

import model_params as P
from alert_engine import EventLog, fmt_time
from digital_twin import DigitalTwinPhysics
from energy_engine import ResourceMeter
from forecasting_engine import HORIZONS, FeatureTracker, LiveAccuracy
from optimization_engine import (ACTION_ORDER, ACTIONS, POWER_CAP_DURATION_S, choose_recommended,
                                 disruption_score, explain_choice, plan_action, score_branch,
                                 simulate_branch, tune_cooling)
from scenario_engine import EVENT_LIBRARY, EventSchedule
from weather_engine import CLIMATES, ClimateEngine
from workload_engine import WorkloadEngine

DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "sim",               # "sim" or "demo"
    "numRacks": 8,
    "scale": "medium",
    "climate": "temperate",
    "events": "none",            # "none", "random" or a list of event ids
    "durationS": 3600,
    "seed": 42,
    "mlModel": "xgboost",
    "inletLimit": P.DEFAULT_INLET_LIMIT_C,
    "weights": dict(P.DEFAULT_COST_WEIGHTS),
    "gridFactor": P.DEFAULT_GRID_FACTOR_KG_PER_KWH,
    "priceKwh": P.DEFAULT_ELECTRICITY_INR_PER_KWH,
    "priceWaterKl": P.DEFAULT_WATER_INR_PER_KL,
    "workloadLevel": 1.0,
}

DEMO_CONFIG: Dict[str, Any] = {**DEFAULT_CONFIG, "mode": "demo", "events": "demo", "durationS": 3600, "seed": 7}

POLICY_START = {
    "fixed": (P.FIXED_POLICY["setpoint"], P.FIXED_POLICY["crah"]),
    "reactive": (P.REACTIVE_POLICY["setpoint"], P.REACTIVE_POLICY["crah"]),
    "predictive": (P.DEFAULT_SUPPLY_SETPOINT_C, P.DEFAULT_CRAH_FRACTION),
    "random": (P.DEFAULT_SUPPLY_SETPOINT_C, P.DEFAULT_CRAH_FRACTION),
}


def normalise_config(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = {**DEFAULT_CONFIG, **(cfg or {})}
    out["weights"] = {**P.DEFAULT_COST_WEIGHTS, **(out.get("weights") or {})}
    out["numRacks"] = int(max(4, min(12, int(out["numRacks"]))))
    out["durationS"] = int(max(300, min(24 * 3600, int(out["durationS"]))))
    out["seed"] = int(out["seed"])
    out["inletLimit"] = float(out["inletLimit"])
    if out["climate"] not in CLIMATES:
        out["climate"] = "temperate"
    if out["scale"] not in P.SCALE_DENSITY:
        out["scale"] = "medium"
    return out


class Decision:
    """A hotspot decision: candidate actions evaluated in cloned twins."""

    def __init__(self, run: "SimulationRun", hot_code: str, value: float, horizon_min: int,
                 probability: float, at_risk: List[str]):
        self.id = len(run.decisions) + 1
        self.t = run.t
        self.hot_code = hot_code
        self.value = value
        self.horizon_min = horizon_min
        self.probability = probability
        self.at_risk = at_risk
        self.limit = run.twin.inlet_limit
        self.weights = run.config["weights"]
        self.base_twin = run.twin.clone()
        protected = set(run.workload.overrides.keys())
        self.candidates = []
        for aid in ACTION_ORDER:
            plan = plan_action(aid, self.base_twin, hot_code, protected)
            self.candidates.append({"actionId": aid, "title": ACTIONS[aid]["title"],
                                    "description": ACTIONS[aid]["description"], "plan": plan,
                                    "disruption": disruption_score(self.base_twin, plan),
                                    "status": "pending", "result": None})
        self.baseline_kwh: Optional[float] = None
        self.chosen: Optional[str] = None
        self.chooser: Optional[str] = None
        self.reason: Optional[str] = None
        self.recommended: Optional[str] = None
        self.quiet = False

    def evaluate_next(self) -> bool:
        """Evaluate one pending branch. Returns True when all branches are done."""
        for c in self.candidates:
            if c["status"] == "pending":
                raw = simulate_branch(self.base_twin, c["plan"] if c["actionId"] != "none" else None)
                if c["actionId"] == "none":
                    self.baseline_kwh = raw["energyKwh"]
                c["result"] = score_branch(raw, self.baseline_kwh or raw["energyKwh"], self.limit,
                                           self.weights, c["disruption"])
                c["status"] = "done"
                break
        finished = all(c["status"] == "done" for c in self.candidates)
        self.recommended = choose_recommended(self.candidates)
        for c in self.candidates:
            c["recommended"] = c["actionId"] == self.recommended
        return finished

    def evaluate_all(self):
        while not self.evaluate_next():
            pass

    @property
    def finished(self) -> bool:
        return all(c["status"] == "done" for c in self.candidates)

    def headline(self) -> str:
        num = self.hot_code[1:]
        if self.horizon_min == 0:
            return f"Rack {num} is at {self.value:.1f} C, above the {self.limit:.0f} C limit"
        return f"Rack {num} will reach {self.value:.1f} C in about {self.horizon_min} minutes"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "t": self.t, "time": fmt_time(self.t), "rack": self.hot_code,
            "forecastTemp": round(self.value, 2), "horizonMin": self.horizon_min,
            "probabilityPercent": round(self.probability, 1), "atRisk": self.at_risk,
            "limit": self.limit, "headline": self.headline(),
            "candidates": [{k: v for k, v in c.items() if k != "plan"} | {
                "plan": {"setpoint": c["plan"]["setpoint"], "crah": c["plan"]["crah"],
                         "migrations": c["plan"]["migrations"], "cap": c["plan"]["cap"]}}
                for c in self.candidates],
            "recommended": self.recommended, "finished": self.finished,
            "chosen": self.chosen, "chooser": self.chooser, "reason": self.reason, "quiet": self.quiet,
        }


class SimulationRun:
    def __init__(self, config: Optional[Dict[str, Any]] = None, policy: str = "predictive",
                 forecaster=None, interactive: bool = False, decision_choice: Optional[str] = None,
                 replay_commands: Optional[List[Dict[str, Any]]] = None, record: bool = True,
                 settle: bool = True):
        self.config = normalise_config(config)
        cfg = self.config
        self.policy = policy
        self.forecaster = forecaster
        self.interactive = interactive
        self.decision_choice = decision_choice
        self.record = record
        self.demo = cfg["mode"] == "demo"
        sp, cr = POLICY_START[policy]
        self.twin = DigitalTwinPhysics(cfg["numRacks"], cfg["scale"], sp, cr, cfg["inletLimit"])
        self.climate = ClimateEngine(cfg["climate"], cfg["seed"])
        events = cfg["events"]
        self.schedule = EventSchedule(None if events == "demo" else events, cfg["durationS"], cfg["seed"],
                                      demo=(events == "demo"))
        self.workload = WorkloadEngine(self.twin.racks, cfg["seed"], cfg["workloadLevel"])
        self.rng_policy = np.random.default_rng(cfg["seed"] + 31337)
        self.t = 0
        self.duration = cfg["durationS"]
        self.log = EventLog()
        self.meter = ResourceMeter(self.twin.racks, cfg["inletLimit"], cfg["gridFactor"],
                                   cfg["priceKwh"], cfg["priceWaterKl"])
        self.tracker = FeatureTracker(self.twin.num_racks)
        self.accuracy = LiveAccuracy(self.twin.num_racks)
        self.queue: List[Dict[str, Any]] = []
        self.commands: List[Dict[str, Any]] = []
        self.replay = sorted(replay_commands or [], key=lambda c: c["t"])
        self._replay_idx = 0
        self.disturbances: List[Dict[str, Any]] = []
        self.operator_caps: Dict[int, float] = {}
        self.optimizer_caps: Dict[int, tuple] = {}     # rack id -> (cap kW, end time)
        self.decisions: List[Decision] = []
        self.pending: Optional[Decision] = None
        self.alert_latched: Dict[str, int] = {}     # rack code -> time of its last alert
        self.last_alert_t = -10 ** 9
        self.suppress_alerts = False                 # set by Snooze in the live controller
        self.hold_until = 0
        self.reactive_boost = False
        self.reactive_calm_since: Optional[int] = None
        self.series: List[Dict[str, Any]] = []
        self.forecasts: List[Dict[str, Any]] = []
        self.latest_forecast: Optional[np.ndarray] = None
        self.latest_risk: List[float] = [0.0] * self.twin.num_racks
        self.decision_counts = {"applied": 0, "byChooser": {}}
        self.done = False
        self.end_reason: Optional[str] = None
        self.feature_log: Optional[list] = None      # set to [] to collect features (dataset building)

        # warm start: settle with t = 0 conditions so the run starts from a realistic state
        self._set_inputs(0)
        if settle:
            self.twin.settle(1800, 5.0)
        self.tracker.sample(self.twin)
        self.log.log(0, "system_start", "Info", "System", "Simulation started",
                     f"{cfg['numRacks']} racks, {cfg['scale']} scale, {CLIMATES[cfg['climate']]['name']} climate, "
                     f"{len(self.schedule.items)} scheduled events, inlet limit {cfg['inletLimit']:.0f} C, "
                     f"policy {policy}.", values={"seed": cfg["seed"]})

    # ── inputs ─────────────────────────────────────────────────────────────
    def _set_inputs(self, t: int):
        mods = self.schedule.modifiers(t, self.twin, self.climate)
        self.twin.mods = mods
        self.climate.update(t)
        self.twin.outside_temp = self.climate.outside_temp
        self.twin.humidity = self.climate.humidity
        self.twin.wet_bulb = self.climate.wet_bulb
        for r in self.twin.racks:
            r["util"] = self.workload.utilization(t, r["id"], mods.util_delta.get(r["id"], 0.0),
                                                  mods.util_set.get(r["id"]))
            caps = [c for c in (self.operator_caps.get(r["id"]),
                                self.optimizer_caps.get(r["id"], (None,))[0]) if c is not None]
            r["powerCapKw"] = min(caps) if caps else None
            r["heatPulseKw"] = sum(d["magnitude"] for d in self.disturbances
                                   if d["rackId"] == r["id"] and d["kind"] == "heat_pulse" and d["start"] <= t < d["end"])
            r["inletOffset"] = sum(d["magnitude"] for d in self.disturbances
                                   if d["rackId"] == r["id"] and d["kind"] == "inlet_offset" and d["start"] <= t < d["end"])

    # ── commands ───────────────────────────────────────────────────────────
    def submit(self, cmd: Dict[str, Any]):
        self.queue.append(cmd)

    def _apply_command(self, cmd: Dict[str, Any], who: str = "Operator"):
        t = self.t
        if cmd["type"] == "rack":
            rid = int(cmd["rackId"])
            rack = next((r for r in self.twin.racks if r["id"] == rid), None)
            if rack is None:
                return
            changes = []
            if cmd.get("util") is not None:
                self.workload.overrides[rid] = float(cmd["util"])
                self.workload.offsets.pop(rid, None)
                changes.append(f"workload {float(cmd['util']):.0f} %")
            if cmd.get("clearUtil"):
                self.workload.overrides.pop(rid, None)
                changes.append("workload back to automatic")
            if "powerCapKw" in cmd:
                if cmd["powerCapKw"] is None:
                    self.operator_caps.pop(rid, None)
                    changes.append("power cap removed")
                else:
                    self.operator_caps[rid] = float(cmd["powerCapKw"])
                    changes.append(f"power cap {float(cmd['powerCapKw']):.1f} kW")
            if cmd.get("airflowPct") is not None:
                rack["airflowFactor"] = max(0.5, min(1.5, float(cmd["airflowPct"]) / 100.0))
                changes.append(f"local airflow {float(cmd['airflowPct']):.0f} %")
            dist = cmd.get("disturbance")
            if dist:
                kind = dist.get("kind", "heat_pulse")
                mag = float(dist.get("magnitude", 2.0))
                dur = int(float(dist.get("durationMin", 5)) * 60)
                self.disturbances.append({"rackId": rid, "kind": kind, "magnitude": mag, "start": t, "end": t + dur})
                label = f"heat pulse +{mag:.1f} kW" if kind == "heat_pulse" else f"inlet offset {mag:+.1f} K"
                changes.append(f"temperature disturbance ({label} for {dur // 60} min)")
            self.log.log(t, f"user_rack_{rid}", "Info", "User action", f"{rack['code']} settings changed",
                         f"{who} set {rack['code']}: " + ", ".join(changes) + ".", "rack", rack["code"],
                         {k: v for k, v in cmd.items() if k not in ("type",)}, [rack["code"]])
        elif cmd["type"] == "environment":
            parts = []
            if cmd.get("climate") and cmd["climate"] in CLIMATES:
                self.climate.set_climate(cmd["climate"])
                parts.append(f"climate {CLIMATES[cmd['climate']]['name']}")
            if "outsideTemp" in cmd:
                self.climate.temp_override = None if cmd["outsideTemp"] is None else float(cmd["outsideTemp"])
                parts.append("outside temperature automatic" if cmd["outsideTemp"] is None
                             else f"outside temperature {float(cmd['outsideTemp']):.1f} C")
            if "humidity" in cmd:
                self.climate.humidity_override = None if cmd["humidity"] is None else float(cmd["humidity"])
                parts.append("humidity automatic" if cmd["humidity"] is None else f"humidity {float(cmd['humidity']):.0f} %")
            if cmd.get("event") in EVENT_LIBRARY:
                self.schedule.add(cmd["event"], t, source=who)
                parts.append(f"event {EVENT_LIBRARY[cmd['event']]['name']}")
            if parts:
                self.log.log(t, "user_env", "Info", "User action", "Environment changed",
                             f"{who} changed: " + ", ".join(parts) + ".", "facility", "Facility",
                             {k: v for k, v in cmd.items() if k != "type"})

    # ── control policies ───────────────────────────────────────────────────
    def _control(self):
        t, twin = self.t, self.twin
        if self.policy == "reactive":
            rp = P.REACTIVE_POLICY
            peak = twin.max_inlet()
            if not self.reactive_boost and peak >= twin.inlet_limit - rp["trigger_margin_k"]:
                self.reactive_boost = True
                self.reactive_calm_since = None
                twin.supply_setpoint, twin.crah_fraction = rp["boost_setpoint"], rp["boost_crah"]
                self.log.log(t, "reactive_boost", "Warning", "Decision", "Reactive cooling boost",
                             f"Inlet reached {peak:.1f} C; supply set to {rp['boost_setpoint']:.0f} C and airflow {rp['boost_crah'] * 100:.0f} %.")
            elif self.reactive_boost:
                if peak < twin.inlet_limit - rp["release_margin_k"]:
                    self.reactive_calm_since = self.reactive_calm_since if self.reactive_calm_since is not None else t
                    if t - self.reactive_calm_since >= rp["release_hold_s"]:
                        self.reactive_boost = False
                        twin.supply_setpoint, twin.crah_fraction = rp["setpoint"], rp["crah"]
                        self.log.log(t, "reactive_release", "Info", "Decision", "Reactive boost released",
                                     "Inlets stayed 3 K below the limit for 5 minutes; normal cooling restored.")
                else:
                    self.reactive_calm_since = None
        elif self.policy == "predictive":
            if t % P.TUNER_INTERVAL_S == 0 and t >= self.hold_until:
                sp0, cr0 = twin.supply_setpoint, twin.crah_fraction
                res = tune_cooling(twin, twin.inlet_limit)
                twin.supply_setpoint, twin.crah_fraction = res["setpoint"], res["crah"]
                if abs(res["setpoint"] - sp0) > 1e-6 or abs(res["crah"] - cr0) > 1e-6:
                    self.log.log(t, "tuner", "Info", "Decision", "Cooling tuned",
                                 f"Setpoint {sp0:.1f} to {res['setpoint']:.1f} C, CRAH airflow {cr0 * 100:.0f} to "
                                 f"{res['crah'] * 100:.0f} %; forecast peak inlet {res['peakInlet']:.1f} C over 20 min.",
                                 values=res)
        elif self.policy == "random":
            if t % 900 == 0:
                twin.supply_setpoint = float(self.rng_policy.uniform(16.5, 24.0))
                twin.crah_fraction = float(self.rng_policy.uniform(0.55, 1.1))

    # ── decisions ──────────────────────────────────────────────────────────
    def _apply_plan(self, plan: Dict[str, Any]):
        twin = self.twin
        if plan.get("setpoint") is not None:
            twin.supply_setpoint = plan["setpoint"]
        if plan.get("crah") is not None:
            twin.crah_fraction = plan["crah"]
        for src, dst, pts in plan.get("migrations", []):
            self.workload.offsets[src] = self.workload.offsets.get(src, 0.0) - pts
            self.workload.offsets[dst] = self.workload.offsets.get(dst, 0.0) + pts
        if plan.get("cap"):
            rid, cap = plan["cap"]
            self.optimizer_caps[rid] = (cap, self.t + POWER_CAP_DURATION_S)

    def resolve_decision(self, action_id: Optional[str] = None, chooser: str = "Automatic", allow_unsafe: bool = False):
        d = self.pending
        if d is None:
            return
        if not d.finished:
            d.evaluate_all()
        rec = d.recommended
        action_id = action_id or rec
        cand = next(c for c in d.candidates if c["actionId"] == action_id)
        if chooser == "Operator" and not allow_unsafe and not cand["result"]["safe"] and any(c["result"]["safe"] for c in d.candidates):
            raise ValueError("Unsafe solutions cannot be applied")
        d.chosen, d.chooser = action_id, chooser
        d.reason = explain_choice(d.candidates, action_id)
        if action_id != "none":
            self._apply_plan(cand["plan"])
            self.hold_until = self.t + P.ACTION_HOLD_S
        self.decision_counts["applied"] += 1
        self.decision_counts["byChooser"][chooser] = self.decision_counts["byChooser"].get(chooser, 0) + 1
        r = cand["result"]
        self.log.log(self.t, f"decision_{d.id}", "Info" if r["safe"] else "Warning", "Decision",
                     f"{ACTIONS[action_id]['title']} applied for {d.hot_code}",
                     f"{chooser} chose {ACTIONS[action_id]['title']}"
                     + (" (recommended)" if action_id == rec else f" (recommended was {ACTIONS[rec]['title']})")
                     + f". Forecast peak {r['peakInlet']:.1f} C, energy change {r['energyChangePercent']:+.1f} %.",
                     "rack", d.hot_code, {"actionId": action_id, "recommended": rec, "chooser": chooser,
                                          "peakInlet": r["peakInlet"], "safe": r["safe"]}, [d.hot_code])
        self.pending = None

    def _forecast(self):
        if self.forecaster is None:
            X = self.tracker.features(self.twin)
            if self.feature_log is not None:
                self.feature_log.append((self.t, X))
            return
        X = self.tracker.features(self.twin)
        seq = self.tracker.sequences() if self.forecaster.model_id == "gru" else None
        F = self.forecaster.predict(X, seq)
        limit = self.twin.inlet_limit
        probs = self.forecaster.risk(F, limit)
        self.latest_forecast, self.latest_risk = F, probs
        if self.record:
            self.forecasts.append({"t": self.t, "values": np.round(F, 2).tolist(),
                                   "risk": [round(p, 1) for p in probs]})
        self.accuracy.add(self.t, F)
        # hotspot detection
        breaches = []
        for i, rack in enumerate(self.twin.racks):
            code = rack["code"]
            hit = None
            if rack["inletTemp"] > limit:
                hit = (rack["inletTemp"], 0)
            else:
                for k, h in enumerate(HORIZONS):
                    if h > P.ALERT_HORIZON_MIN:
                        break
                    if F[i, k] > limit:
                        hit = (float(F[i, k]), h)
                        break
            if hit:
                breaches.append((code, hit[0], hit[1], probs[i]))
                if hit[1] > 0:
                    self.log.forecast_warning(self.t, code, hit[0], hit[1], limit, probs[i])
            else:
                calm = probs[i] < 20 and rack["inletTemp"] < limit - P.ALERT_CLEAR_MARGIN_K
                if calm and self.log.forecast_active(code):
                    self.log.clear_forecast(code)
                if calm:
                    self.alert_latched.pop(code, None)      # re-arm the rack once it has recovered
        if self.policy != "predictive" or self.pending is not None or not breaches or self.suppress_alerts:
            return
        # One alert covers every rack at risk, and a rack only alerts again once it has recovered
        # (or after 30 minutes if it stays hot). After an alert the operator gets a 10 minute
        # quiet period: racks that become at risk during it are still protected, but the
        # recommended solution is applied automatically instead of opening another alert.
        eligible = [b for b in breaches if self.t - self.alert_latched.get(b[0], -10 ** 9) >= P.ALERT_RELATCH_S]
        if not eligible:
            return
        quiet = self.t - self.last_alert_t < P.ALERT_COOLDOWN_S
        hot = max(eligible, key=lambda b: b[1])
        d = Decision(self, hot[0], hot[1], hot[2], hot[3], [b[0] for b in breaches])
        d.quiet = quiet
        self.decisions.append(d)
        if not quiet:
            self.last_alert_t = self.t
        for b in breaches:
            self.alert_latched[b[0]] = self.t
        detail = (f"Racks at risk: {', '.join(d.at_risk)}. "
                  + ("Raised during the quiet period after the previous alert, so the recommended solution is applied automatically without a pop-up."
                     if quiet else f"Hotspot alert: evaluating {len(d.candidates)} solutions in cloned twins."))
        self.log.log(self.t, f"hotspot_alert_{d.id}", "Critical" if hot[2] == 0 else "Warning", "Forecast",
                     d.headline(), detail, "rack", hot[0],
                     {"forecastTemp": round(hot[1], 2), "horizonMin": hot[2], "probabilityPercent": round(hot[3], 1),
                      "quietPeriod": quiet}, d.at_risk)
        self.pending = d
        if self.interactive and not quiet:
            return
        d.evaluate_all()
        if self.decision_choice:
            self.resolve_decision(self.decision_choice, "Replay policy")
        else:
            self.resolve_decision(None, "Automatic (quiet period)" if quiet else "Automatic")

    # ── main step ──────────────────────────────────────────────────────────
    def step(self) -> bool:
        """Advance one simulated second. Returns False if blocked by a pending decision or done."""
        if self.done or self.pending is not None:
            return False
        t = self.t
        while self._replay_idx < len(self.replay) and self.replay[self._replay_idx]["t"] <= t:
            self._apply_command(self.replay[self._replay_idx]["cmd"], self.replay[self._replay_idx].get("who", "Operator"))
            self._replay_idx += 1
        if self.queue:
            for cmd in self.queue:
                who = cmd.pop("_who", "Operator")
                self.commands.append({"t": t, "cmd": dict(cmd), "who": who})
                self._apply_command(cmd, who)
            self.queue = []
        for e in self.schedule.starting(t):
            lib = EVENT_LIBRARY[e["eventId"]]
            self.log.log(t, f"event_start_{e['eventId']}", lib["severity"], lib["category"], f"{lib['name']} started",
                         lib["description"], "facility", "Facility", {"eventId": e["eventId"], "endsAt": fmt_time(e["end"]),
                                                                       "source": e["source"]})
        for e in self.schedule.ending(t):
            lib = EVENT_LIBRARY[e["eventId"]]
            self.log.log(t, f"event_end_{e['eventId']}", "Info", lib["category"], f"{lib['name']} ended",
                         f"{lib['name']} is over; normal conditions are returning.", "facility", "Facility",
                         {"eventId": e["eventId"]})
        for rid, (cap, end) in list(self.optimizer_caps.items()):
            if t >= end:
                del self.optimizer_caps[rid]
        self.workload.step(t)
        self._set_inputs(t)
        self._control()
        self.twin.step(P.PHYSICS_DT_S)
        self.t = t + 1
        self.meter.update(self.t, self.twin, self.twin.wet_bulb)
        self.log.evaluate_thermal(self.t, self.twin)
        if self.t % 10 == 0:
            self.tracker.sample(self.twin)
        if self.t % 60 == 0 or self.t in self.accuracy.pending:
            self.accuracy.resolve(self.t, np.array([r["inletTemp"] for r in self.twin.racks]))
        if self.record and self.t % P.SERIES_INTERVAL_S == 0:
            self._record_point()
        if self.t % P.FORECAST_INTERVAL_S == 0:
            self._forecast()
        if self.t >= self.duration:
            self.finish("completed")
        return True

    def finish(self, reason: str):
        if self.done:
            return
        if self.pending is not None:
            self.resolve_decision(None, "Automatic")
        self.done = True
        self.end_reason = reason
        self.log.log(self.t, "system_end", "Info", "System",
                     "Simulation completed" if reason == "completed" else "Simulation ended early",
                     f"Run {'reached its full duration' if reason == 'completed' else 'was ended by the operator'} at {fmt_time(self.t)}.")

    def run_to_end(self, progress=None, stop_at: Optional[int] = None):
        while not self.done:
            if stop_at is not None and self.t >= stop_at:
                self.finish("ended")
                break
            if self.pending is not None:
                self.pending.evaluate_all()
                self.resolve_decision(self.decision_choice, "Replay policy" if self.decision_choice else "Automatic")
            self.step()
            if progress and self.t % 120 == 0:
                progress(self.t / self.duration)

    # ── views ──────────────────────────────────────────────────────────────
    def _record_point(self):
        tw, o, c = self.twin, self.twin.out, self.climate
        racks = tw.racks
        m = self.meter
        self.series.append({
            "t": self.t,
            "inlet": [round(r["inletTemp"], 2) for r in racks],
            "exhaust": [round(r["exhaustTemp"], 2) for r in racks],
            "util": [round(r["util"], 1) for r in racks],
            "power": [round(r["powerKw"], 2) for r in racks],
            "maxInlet": round(o["maxInlet"], 2),
            "supply": round(tw.supply_temp, 2),
            "setpoint": round(tw.supply_setpoint, 2),
            "crah": round(tw.crah_fraction, 3),
            "itKw": round(o["itKw"], 2),
            "chillerKw": round(o["chillerKw"], 2),
            "fansKw": round(o["fansKw"], 2),
            "pumpsKw": round(o["pumpsKw"], 2),
            "coolingKw": round(o["coolingKw"], 2),
            "pue": round(o["pue"], 3),
            "outside": round(c.outside_temp, 2),
            "humidity": round(c.humidity, 1),
            "wetBulb": round(c.wet_bulb, 2),
            "energyKwh": round(m.facility_kwh, 3),
            "waterL": round(m.water_l, 2),
            "risk": round(max(self.latest_risk) if self.latest_risk else 0.0, 1),
        })

    def rack_forecasts(self) -> List[Dict[str, Any]]:
        out = []
        for i, r in enumerate(self.twin.racks):
            f = self.latest_forecast[i] if self.latest_forecast is not None else None
            out.append({"code": r["code"],
                        "forecast": {str(h): round(float(f[k]), 2) for k, h in enumerate(HORIZONS)} if f is not None else None,
                        "riskPercent": round(self.latest_risk[i], 1) if self.latest_risk else 0.0})
        return out

    def live_view(self) -> Dict[str, Any]:
        racks = self.twin.rack_view()
        fc = self.rack_forecasts()
        for r, f in zip(racks, fc):
            r["forecast"] = f["forecast"]
            r["riskPercent"] = f["riskPercent"]
            r["workloadOverride"] = self.workload.overrides.get(r["id"])
            r["operatorCapKw"] = self.operator_caps.get(r["id"])
        hottest = max(racks, key=lambda r: r["inletTemp"])
        return {
            "t": self.t, "time": fmt_time(self.t), "durationS": self.duration,
            "progressPercent": round(min(100.0, self.t / self.duration * 100.0), 2),
            "policy": self.policy, "config": self.config, "done": self.done, "endReason": self.end_reason,
            "racks": racks, "facility": self.twin.facility_view(), "climate": self.climate.to_dict(),
            "kpis": {"hottestInlet": hottest["inletTemp"], "hottestRack": hottest["code"],
                     "hotspotRiskPercent": round(max(self.latest_risk), 1) if self.latest_risk else 0.0,
                     "coolingKw": round(self.twin.out.get("coolingKw", 0.0), 2),
                     "pue": round(self.twin.out.get("pue", 1.0), 3),
                     "liveMae": self.accuracy.rolling_mae(),
                     "liveWithin1Pct": self.accuracy.rolling_within1(),
                     "liveMaeSamples": len(self.accuracy.recent5),
                     "model": self.forecaster.model_id if self.forecaster else None},
            "activeEvents": [{**e, "description": EVENT_LIBRARY[e["eventId"]]["description"]}
                             for e in self.schedule.active(self.t)],
            "scheduledEvents": self.schedule.to_list(),
            "resources": self.meter.summary(),
            "decisionsCount": len(self.decisions),
        }
