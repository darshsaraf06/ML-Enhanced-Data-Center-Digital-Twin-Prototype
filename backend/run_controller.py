"""
Live run controller.

A single worker thread owns the active SimulationRun and advances it at the requested
speed (simulated seconds per wall-clock second) in fixed 1 s physics steps. REST
handlers only queue commands; the WebSocket broadcaster reads snapshots. Hotspot
decisions pause the run: branches are evaluated one by one so the screen can fill
in solution cards, and if the operator does not choose within 30 s the recommended
solution is applied automatically. Skip to End runs the same steps without waiting,
applies recommended solutions automatically and reports progress.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import model_params as P
from alert_engine import fmt_time
from forecasting_engine import Forecaster
from results_engine import compile_results, run_replays
from run_store import save_run
from simulation_engine import DEMO_CONFIG, SimulationRun, normalise_config

SPEEDS = [1, 2, 5, 10, 25]


class ControllerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class LiveController:
    def __init__(self):
        self.lock = threading.RLock()
        self.run: Optional[SimulationRun] = None
        self.run_id: Optional[str] = None
        self.status = "IDLE"        # IDLE RUNNING PAUSED DECISION SKIPPING FINISHED
        self.speed = 1.0
        self.owed = 0.0
        self.last_wall = time.monotonic()
        self.speed_samples: List[tuple] = []
        self.decision_deadline: Optional[float] = None
        self.paused_before_decision = False
        self.toasts: List[Dict[str, Any]] = []
        self.snooze_until: Optional[float] = None
        self.save_to_logs = True
        self.results: Optional[Dict[str, Any]] = None
        self.results_status = {"state": "none", "progress": 0.0, "step": ""}
        self.version = 0
        self.series_cursor = 0
        self.forecast_cursor = 0
        self._counter = 0
        self._thread = threading.Thread(target=self._loop, name="sim-runner", daemon=True)
        self._thread.start()

    # ── commands from the API ──────────────────────────────────────────────
    def start(self, config: Dict[str, Any]) -> Dict[str, Any]:
        save = bool(config.pop("saveToLogs", True))
        cfg = normalise_config({**DEMO_CONFIG} if config.get("mode") == "demo" else config)
        if cfg["mode"] == "demo":
            cfg["mlModel"] = DEMO_CONFIG["mlModel"]
        forecaster = Forecaster(cfg["mlModel"])
        run = SimulationRun(cfg, policy="predictive", forecaster=forecaster, interactive=True)
        with self.lock:
            self._counter += 1
            self.run = run
            self.run_id = f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-S{cfg['seed']}"
            self.status = "RUNNING"
            self.speed = 1.0
            self.owed = 0.0
            self.last_wall = time.monotonic()
            self.speed_samples = []
            self.decision_deadline = None
            self.toasts = []
            self.snooze_until = None
            self.save_to_logs = save
            self.results = None
            self.results_status = {"state": "none", "progress": 0.0, "step": ""}
            self.series_cursor = 0
            self.forecast_cursor = 0
            self.version += 1
        return {"runId": self.run_id, "model": forecaster.model_id}

    def _require_run(self):
        if self.run is None:
            raise ControllerError(409, "No simulation has been started")

    def pause(self):
        with self.lock:
            self._require_run()
            if self.status == "RUNNING":
                self.status = "PAUSED"
                self.run.log.log(self.run.t, "user_pause", "Info", "User action", "Simulation paused",
                                 f"Operator paused the run at {fmt_time(self.run.t)}.")
                self.version += 1

    def resume(self):
        with self.lock:
            self._require_run()
            if self.status == "PAUSED":
                self.status = "RUNNING"
                self.last_wall = time.monotonic()
                self.owed = 0.0
                self.run.log.log(self.run.t, "user_resume", "Info", "User action", "Simulation resumed",
                                 f"Operator resumed the run at {fmt_time(self.run.t)}.")
                self.version += 1

    def set_speed(self, speed: float):
        with self.lock:
            if speed not in SPEEDS:
                raise ControllerError(400, f"Speed must be one of {SPEEDS}")
            self.speed = float(speed)
            self.owed = 0.0
            self.last_wall = time.monotonic()
            self.speed_samples = []
            self.version += 1

    def end(self):
        with self.lock:
            self._require_run()
            if self.status in ("FINISHED",):
                return
            self.run.finish("ended")
            self._on_finished()

    def skip(self):
        with self.lock:
            self._require_run()
            if self.status in ("FINISHED", "SKIPPING"):
                return
            if self.status == "DECISION" and self.run.pending is not None:
                self.run.resolve_decision(None, "Automatic (Skip to End)")
            if self.snooze_until is not None:
                self._end_snooze("Snooze cancelled: Skip to End applies recommended solutions automatically.")
            self.status = "SKIPPING"
            self.run.log.log(self.run.t, "user_skip", "Info", "User action", "Skip to End",
                             "Operator skipped to the end; recommended solutions are applied automatically.")
            self.version += 1

    def submit(self, cmd: Dict[str, Any]):
        with self.lock:
            self._require_run()
            if self.run.demo:
                raise ControllerError(403, "Demonstration settings are fixed")
            if self.status in ("FINISHED", "SKIPPING"):
                raise ControllerError(409, "The run is no longer accepting changes")
            if cmd.get("type") == "rack":
                rid = int(cmd.get("rackId", 0))
                if not any(r["id"] == rid for r in self.run.twin.racks):
                    raise ControllerError(404, f"Rack {rid} not found")
            self.run.submit(cmd)
            # a paused run applies queued changes immediately so the operator sees them
            if self.status in ("PAUSED", "DECISION"):
                self._apply_queue_now()
            self.version += 1

    def _apply_queue_now(self):
        run = self.run
        for cmd in run.queue:
            who = cmd.pop("_who", "Operator")
            run.commands.append({"t": run.t, "cmd": dict(cmd), "who": who})
            run._apply_command(cmd, who)
        run.queue = []

    def decide(self, action_id: str):
        with self.lock:
            self._require_run()
            if self.status != "DECISION" or self.run.pending is None:
                raise ControllerError(409, "There is no open hotspot decision")
            try:
                self.run.resolve_decision(action_id, "Operator")
            except ValueError as exc:
                raise ControllerError(400, str(exc))
            self._after_decision()

    def snooze(self):
        """Dismiss the open alert without action and keep alerts closed for 5 minutes (wall clock)."""
        with self.lock:
            self._require_run()
            if self.status in ("FINISHED", "SKIPPING"):
                raise ControllerError(409, "The run is no longer accepting changes")
            run = self.run
            if self.status == "DECISION" and run.pending is not None:
                run.resolve_decision("none", "Operator (snoozed)", allow_unsafe=True)
                self._after_decision()
            run.suppress_alerts = True
            self.snooze_until = time.monotonic() + P.SNOOZE_S
            run.log.log(run.t, "user_snooze", "Info", "User action", "Hotspot alerts snoozed for 5 minutes",
                        f"Operator snoozed hotspot alerts at {fmt_time(run.t)} for {P.SNOOZE_S // 60} minutes of real time. "
                        "Forecast warnings are still logged, but no alert opens and no solution is applied automatically.")
            self.version += 1

    def unsnooze(self):
        with self.lock:
            self._require_run()
            if self.snooze_until is not None:
                self._end_snooze("Operator turned hotspot alerts back on.")

    def _end_snooze(self, detail: str):
        self.snooze_until = None
        if self.run is not None:
            self.run.suppress_alerts = False
            self.run.log.log(self.run.t, "user_snooze_end", "Info", "User action", "Hotspot alerts active again", detail)
        self.version += 1

    def snooze_left(self) -> Optional[float]:
        if self.snooze_until is None:
            return None
        return max(0.0, round(self.snooze_until - time.monotonic(), 1))

    def _after_decision(self):
        self.decision_deadline = None
        self.status = "PAUSED" if self.paused_before_decision else "RUNNING"
        self.last_wall = time.monotonic()
        self.owed = 0.0
        self.version += 1

    # ── worker ─────────────────────────────────────────────────────────────
    def _loop(self):
        while True:
            try:
                self._tick()
            except Exception as exc:   # keep the runner alive, report the problem
                print(f"[runner] error: {exc!r}")
                import traceback
                traceback.print_exc()
                time.sleep(0.5)
            time.sleep(0.02)

    def _tick(self):
        with self.lock:
            run = self.run
            now = time.monotonic()
            if run is None:
                return
            if self.snooze_until is not None and now >= self.snooze_until:
                self._end_snooze("The 5 minute snooze ended.")
            if self.status == "RUNNING":
                self.owed += self.speed * (now - self.last_wall)
                self.last_wall = now
                steps = 0
                while self.owed >= 1.0 and steps < 60:
                    if not run.step():
                        break
                    self.owed -= 1.0
                    steps += 1
                    if run.pending is not None:
                        self._open_decision(now)
                        break
                    if run.done:
                        break
                if steps:
                    self.version += 1
                self.speed_samples.append((now, run.t))
                self.speed_samples = [s for s in self.speed_samples if now - s[0] <= 3.0]
            elif self.status == "DECISION":
                d = run.pending
                if d is None:
                    self._after_decision()
                elif not d.finished:
                    d.evaluate_next()
                    self.version += 1
                elif self.decision_deadline is not None and now >= self.decision_deadline:
                    rec = d.recommended
                    run.resolve_decision(None, "Automatic (timeout)")
                    self.toasts.append({"t": run.t, "text": f"No choice within {P.DECISION_TIMEOUT_S} s: applied the recommended solution, {d.candidates[[c['actionId'] for c in d.candidates].index(rec)]['title']}."})
                    self._after_decision()
            elif self.status == "SKIPPING":
                for _ in range(400):
                    if run.done:
                        break
                    if run.pending is not None:
                        run.pending.evaluate_all()
                        run.resolve_decision(None, "Automatic (Skip to End)")
                    run.step()
                self.version += 1
            if run.done and self.status != "FINISHED":
                self._on_finished()

    def _open_decision(self, now: float):
        self.paused_before_decision = False
        self.status = "DECISION"
        self.decision_deadline = now + P.DECISION_TIMEOUT_S
        self.owed = 0.0
        self.version += 1

    def _on_finished(self):
        self.status = "FINISHED"
        self.decision_deadline = None
        self.results_status = {"state": "computing", "progress": 0.0, "step": "Starting comparison runs"}
        self.version += 1
        run, run_id = self.run, self.run_id
        threading.Thread(target=self._compute_results, args=(run, run_id), daemon=True).start()

    def _compute_results(self, run, run_id):
        def progress(frac, step):
            with self.lock:
                if self.run is run:
                    self.results_status = {"state": "computing", "progress": round(frac * 100, 1),
                                           "step": f"Finished replay: {step}"}
                    self.version += 1
        try:
            replays = run_replays(run, progress)
            results = compile_results(run, replays, run_id)
            if self.save_to_logs:
                save_run(results)
            with self.lock:
                if self.run is run:
                    self.results = results
                    self.results_status = {"state": "ready", "progress": 100.0, "step": "Results ready"}
                    self.version += 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            with self.lock:
                if self.run is run:
                    self.results_status = {"state": "error", "progress": 0.0, "step": f"Results failed: {exc}"}
                    self.version += 1

    # ── views ──────────────────────────────────────────────────────────────
    def actual_speed(self) -> Optional[float]:
        s = self.speed_samples
        if self.status != "RUNNING" or len(s) < 2 or s[-1][0] - s[0][0] < 0.5:
            return None
        return round((s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]), 1)

    def snapshot(self, include_new: bool = True) -> Dict[str, Any]:
        with self.lock:
            run = self.run
            base = {"type": "state", "version": self.version, "status": self.status, "runId": self.run_id,
                    "speed": self.speed, "actualSpeed": self.actual_speed(),
                    "results": self.results_status, "serverTime": time.time()}
            if run is None:
                return base
            live = run.live_view()
            base.update(live)
            base["mode"] = run.config["mode"]
            base["events"] = run.log.recent(150)
            base["eventCounts"] = run.log.counts()
            base["toasts"] = self.toasts[-5:]
            left = self.snooze_left()
            base["snooze"] = {"active": left is not None, "secondsLeft": left, "durationS": P.SNOOZE_S}
            d = run.pending
            if self.status == "DECISION" and d is not None:
                dd = d.to_dict()
                dd["secondsLeft"] = max(0.0, round(self.decision_deadline - time.monotonic(), 1)) if self.decision_deadline else None
                base["decision"] = dd
            else:
                base["decision"] = None
            if include_new:
                base["newPoints"] = run.series[self.series_cursor:]
                base["newForecasts"] = run.forecasts[self.forecast_cursor:]
                base["_cursors"] = (run, len(run.series), len(run.forecasts))
            return base

    def advance_cursors(self, snap: Dict[str, Any]):
        """Called after a snapshot was broadcast: the next broadcast only carries newer points."""
        cur = snap.pop("_cursors", None)
        with self.lock:
            if cur and cur[0] is self.run:
                self.series_cursor, self.forecast_cursor = cur[1], cur[2]

    def series(self) -> Dict[str, Any]:
        with self.lock:
            if self.run is None:
                return {"points": [], "forecasts": [], "racks": []}
            return {"points": list(self.run.series), "forecasts": list(self.run.forecasts),
                    "racks": [r["code"] for r in self.run.twin.racks], "limit": self.run.twin.inlet_limit,
                    "horizons": P.FORECAST_HORIZONS_MIN,
                    "markers": [{"t": e["t"], "category": e["category"], "severity": e["severity"], "title": e["title"]}
                                for e in self.run.log.events if e["category"] not in ("System",) and e["kind"] != "tuner"]}


controller = LiveController()
