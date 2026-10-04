"""Backend tests for the live-screen fixes (bugs 1-6 and findings A-F)."""

import time

import numpy as np
import pytest

from alert_engine import EventLog
from digital_twin import DigitalTwinPhysics
from forecasting_engine import FEATURE_NAMES, Forecaster, FeatureTracker
from optimization_engine import plan_action
from simulation_engine import SimulationRun

EVENT_FIELDS = ("t", "time", "severity", "category", "sourceKind", "sourceId", "title", "detail", "values", "racks", "count", "items")


def forecaster():
    return Forecaster("xgboost")


# ── Bug 1: frozen live data ──────────────────────────────────────────────────
def test_engine_steps_change_state():
    run = SimulationRun({"seed": 1}, policy="predictive", forecaster=forecaster())
    before = [(r["inletTemp"], r["exhaustTemp"], r["util"], r["powerKw"]) for r in run.twin.racks]
    for _ in range(60):
        assert run.step()
    after = [(r["inletTemp"], r["exhaustTemp"], r["util"], r["powerKw"]) for r in run.twin.racks]
    assert run.t == 60
    assert all(a != b for a, b in zip(after, before)), "every rack should evolve over 60 s"
    assert len(run.series) == 12


def test_temperatures_evolve_over_minutes_not_seconds():
    twin = DigitalTwinPhysics(8)
    twin.outside_temp, twin.wet_bulb = 24.0, 18.0
    twin.settle(3600)
    rack = twin.racks[4]
    start = rack["exhaustTemp"]
    rack["util"] = 100.0
    twin.step(10.0)
    after_10s = rack["exhaustTemp"] - start
    for _ in range(59):
        twin.step(10.0)
    after_10min = rack["exhaustTemp"] - start
    assert after_10min > 1.0
    assert after_10s < 0.4 * after_10min, "a 10 s step must not reach steady state"


# ── Bug 2 / finding B: changes persist ───────────────────────────────────────
def test_rack_workload_change_persists_and_raises_power():
    run = SimulationRun({"seed": 2}, policy="predictive", forecaster=forecaster())
    run.step()
    p0 = run.twin.racks[0]["powerKw"]
    run.submit({"type": "rack", "rackId": 1, "util": 90})
    for _ in range(60):
        run.step()
    rack = run.twin.racks[0]
    assert rack["util"] == pytest.approx(90.0)
    assert rack["powerKw"] > p0
    assert run.commands and run.commands[0]["t"] == 1


def test_workload_migration_survives_60_steps():
    run = SimulationRun({"seed": 3}, policy="fixed")
    run.step()
    hot = max(run.twin.racks, key=lambda r: r["inletTemp"])
    plan = plan_action("workload_migration", run.twin, hot["code"], set())
    assert plan["migrations"], "migration plan should move workload"
    twin_run = SimulationRun({"seed": 3}, policy="fixed")   # identical run without the migration
    twin_run.step()
    run._apply_plan(plan)
    for _ in range(60):
        run.step()
        twin_run.step()
    src, dst, pts = plan["migrations"][0]
    moved = sum(p for s, _, p in plan["migrations"] if s == src)
    assert run.workload.offsets[src] == pytest.approx(-moved)
    assert run.twin.racks[src - 1]["util"] == pytest.approx(twin_run.twin.racks[src - 1]["util"] - moved)
    assert run.twin.racks[dst - 1]["util"] == pytest.approx(min(100.0, twin_run.twin.racks[dst - 1]["util"] + pts))


def test_setpoint_and_airflow_changes_are_not_reset_by_events():
    run = SimulationRun({"seed": 4, "events": ["fan_degradation"]}, policy="fixed")
    run.twin.supply_setpoint = 17.0
    run.twin.crah_fraction = 1.1
    for _ in range(900):
        run.step()
    assert run.twin.supply_setpoint == 17.0
    assert run.twin.crah_fraction == 1.1


# ── Bug 4 / finding C: realistic temperatures ────────────────────────────────
def test_default_normal_run_stays_below_limit_without_alarms():
    run = SimulationRun({"seed": 42}, policy="predictive", forecaster=forecaster())
    peak = 0.0
    for _ in range(15 * 60):
        assert run.step(), "no hotspot decision should block a default normal run"
        peak = max(peak, run.twin.max_inlet())
    assert peak < 27.0
    alarms = [e for e in run.log.events if e["severity"] in ("Warning", "Critical")]
    assert alarms == [], f"unexpected alarms: {[e['title'] for e in alarms]}"
    inlets = [r["inletTemp"] for r in run.twin.racks]
    assert 18.0 < min(inlets) and max(inlets) < 27.0


def test_inlet_depends_on_supply_and_recirculation():
    twin = DigitalTwinPhysics(8)
    twin.outside_temp, twin.wet_bulb = 24.0, 18.0
    twin.settle(3600)
    base = twin.max_inlet()
    starved = twin.clone()
    starved.crah_fraction = 0.5
    starved.settle(1800)
    assert starved.max_inlet() > base + 1.0, "air starvation must raise inlets through recirculation"
    warm = twin.clone()
    warm.supply_setpoint = 23.0
    warm.settle(1800)
    assert warm.max_inlet() == pytest.approx(base + 3.0, abs=0.6)


def test_chiller_trip_creates_hotspot_over_minutes():
    run = SimulationRun({"seed": 5, "events": ["cooling_failure"], "durationS": 1800}, policy="fixed")
    start = run.schedule.items[0]["start"]
    for _ in range(start + 60):
        run.step()
    one_min = run.twin.max_inlet()
    for _ in range(420):
        run.step()
    assert run.twin.max_inlet() > one_min + 3.0
    assert run.twin.max_inlet() > 27.0


# ── Finding A / E: train-serve consistency, every model is real ─────────────
def test_features_match_training_definition():
    twin = DigitalTwinPhysics(8)
    tr = FeatureTracker(8)
    tr.sample(twin)
    X = tr.features(twin)
    assert X.shape == (8, len(FEATURE_NAMES))
    assert X[0, 0] == pytest.approx(twin.racks[0]["inletTemp"])


@pytest.mark.parametrize("model_id", Forecaster.available_models())
def test_every_available_model_forecasts_inlet(model_id):
    run = SimulationRun({"seed": 6, "mlModel": model_id}, policy="predictive", forecaster=Forecaster(model_id))
    for _ in range(60):
        run.step()
    assert run.forecaster.model_id == model_id
    F = run.latest_forecast
    assert F.shape == (8, 5)
    inlets = np.array([r["inletTemp"] for r in run.twin.racks])
    assert np.all(np.abs(F[:, 0] - inlets) < 3.0), "5 minute forecasts must be close to current inlet in a calm run"
    assert all(0.0 <= p <= 100.0 for p in run.latest_risk)
    assert max(run.latest_risk) < 20.0, "a calm normal run must not report high hotspot risk"


def test_no_hardcoded_model_metrics():
    import forecasting_engine
    import inspect
    src = inspect.getsource(forecasting_engine)
    for fake in ("0.38", "0.988", "0.991", "3.8"):
        assert f'"mae": {fake}' not in src and f'"r2": {fake}' not in src


# ── Bug 5 / finding F: skip to end ───────────────────────────────────────────
def _interactive_like_1x(cfg):
    """Drive a run the way the live controller does at 1x when nobody answers the alert."""
    run = SimulationRun(cfg, policy="predictive", forecaster=forecaster(), interactive=True)
    while not run.done:
        if run.pending is not None:
            while not run.pending.evaluate_next():
                pass
            run.resolve_decision(None, "Automatic (timeout)")
            continue
        run.step()
    return run


def test_skip_gives_same_result_as_1x():
    cfg = {"seed": 11, "events": ["cooling_failure"], "durationS": 1800}
    a = _interactive_like_1x(cfg)
    b = SimulationRun(cfg, policy="predictive", forecaster=forecaster(), interactive=False)
    b.run_to_end()
    assert len(a.decisions) >= 1, "the chiller trip should trigger at least one decision"
    assert a.meter.summary() == b.meter.summary()
    assert [d.chosen for d in a.decisions] == [d.chosen for d in b.decisions]


def test_one_hour_default_run_skips_fast():
    run = SimulationRun({"seed": 42}, policy="predictive", forecaster=forecaster())
    t0 = time.perf_counter()
    run.run_to_end()
    assert run.t == 3600
    assert time.perf_counter() - t0 < 30.0


# ── Bug 6: structured, grouped events ────────────────────────────────────────
def test_events_have_all_fields_and_startup_storm_is_grouped():
    twin = DigitalTwinPhysics(8)
    for r in twin.racks:
        r["inletTemp"] = 28.0
    log = EventLog()
    log.evaluate_thermal(25, twin)
    thermal = [e for e in log.events if e["category"] == "Thermal"]
    assert len(thermal) == 1
    assert len(thermal[0]["racks"]) == 8
    assert thermal[0]["title"].startswith("8 racks above 27 C")
    for e in log.events:
        for f in EVENT_FIELDS:
            assert f in e
        assert e["severity"] in ("Info", "Warning", "Critical")


def test_forecast_warning_cooldown():
    log = EventLog()
    assert log.forecast_warning(30, "R03", 28.0, 15, 27.0, 70.0)
    assert not log.forecast_warning(60, "R03", 28.5, 10, 27.0, 80.0)
    log.clear_forecast("R03")
    assert log.forecast_warning(900, "R03", 28.0, 15, 27.0, 70.0)


def test_run_events_are_structured():
    run = SimulationRun({"seed": 7, "events": ["workload_spike", "cooling_failure"], "durationS": 2400}, policy="predictive",
                        forecaster=forecaster())
    run.run_to_end()
    assert len(run.log.events) > 3
    cats = {e["category"] for e in run.log.events}
    assert {"System", "Workload", "Cooling"} <= cats
    for e in run.log.events:
        for f in EVENT_FIELDS:
            assert f in e


# ── Alerts must not repeat continuously ──────────────────────────────────────
def test_alerts_are_spaced_and_do_not_repeat_for_the_same_racks():
    run = SimulationRun({"seed": 42, "events": ["workload_spike", "heatwave"], "climate": "extreme_heat"},
                        policy="predictive", forecaster=forecaster())
    run.run_to_end()
    popups = [d.t for d in run.decisions if not d.quiet]
    assert 1 <= len(popups) <= 4, f"too many alert pop-ups in one hour: {len(popups)}"
    assert all(b - a >= 600 for a, b in zip(popups, popups[1:])), "pop-ups must be at least 10 simulated minutes apart"
    for d in run.decisions:
        if d.quiet:
            assert d.chooser == "Automatic (quiet period)" and d.chosen is not None, "risks in the quiet period are still handled"


def test_suppressed_alerts_open_no_decision():
    run = SimulationRun({"seed": 11, "events": ["cooling_failure"], "durationS": 1800}, policy="predictive",
                        forecaster=forecaster(), interactive=True)
    run.suppress_alerts = True
    while not run.done:
        assert run.pending is None
        run.step()
    assert run.decisions == []
    assert any(e["kind"] == "forecast_breach" for e in run.log.events), "warnings are still logged while snoozed"


def test_live_accuracy_percent():
    run = SimulationRun({"seed": 12}, policy="predictive", forecaster=forecaster())
    for _ in range(900):
        run.step()
    pct = run.live_view()["kpis"]["liveWithin1Pct"]
    assert pct is not None and 0 <= pct <= 100
    assert run.accuracy.summary()["5"]["within1Pct"] == pct or run.accuracy.summary()["5"]["count"] > 0
