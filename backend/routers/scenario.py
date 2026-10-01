"""
Scenario Router - operational failure modes, weather psychrometrics, and scenario combinations.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from simulation_engine import engine
from weather_engine import WEATHER_PRESETS
from scenario_engine import FAILURE_SCENARIOS, WORKLOAD_PRESETS

router = APIRouter(prefix="/api/scenario", tags=["scenario"])


class WeatherRequest(BaseModel):
    presetId: str
    ambientTemp: Optional[float] = None
    humidity: Optional[float] = None


class ProblemRequest(BaseModel):
    problemId: str


class WorkloadRequest(BaseModel):
    workloadId: str


class CombineRequest(BaseModel):
    weatherId: str = "normal"
    problemId: str = "none"
    workloadId: str = "baseline"
    ambientTemp: Optional[float] = None
    humidity: Optional[float] = None


@router.get("/list")
async def list_all_scenarios():
    return {
        "weatherPresets": list(WEATHER_PRESETS.values()),
        "failureProblems": list(FAILURE_SCENARIOS.values()),
        "workloadProfiles": list(WORKLOAD_PRESETS.values()),
        "currentWeather": engine.weather.to_dict(),
        "currentProblem": engine.scenarios.active_problem,
        "currentWorkload": engine.scenarios.active_workload,
    }


@router.post("/weather")
async def set_weather(body: WeatherRequest):
    if body.presetId == "custom" and body.ambientTemp is not None and body.humidity is not None:
        engine.weather.set_custom(body.ambientTemp, body.humidity)
    elif body.presetId in WEATHER_PRESETS:
        engine.weather.load_preset(body.presetId)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown weather preset '{body.presetId}'")

    engine.twin.ambient_temp = engine.weather.ambient_temp
    engine.twin.ambient_humidity = engine.weather.humidity

    engine.alerts.record_event(
        severity="INFO",
        event_type="Weather Scenario Changed",
        description=f"Ambient weather set to {engine.weather.preset_id.capitalize()} ({engine.weather.ambient_temp}°C, {engine.weather.humidity}% RH).",
        rack_id="ENVIRONMENT",
        sim_time_str=engine.to_dict()["clock"]["elapsedFormatted"],
        action_taken="Thermodynamics Adjusted",
    )
    return {"ok": True, "weather": engine.weather.to_dict()}


@router.post("/problem")
async def set_problem(body: ProblemRequest):
    if body.problemId not in FAILURE_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown problem scenario '{body.problemId}'")

    engine.scenarios.set_problem(body.problemId)
    engine.scenarios.apply_to_physics(engine.twin, elapsed_sec=engine.elapsed_seconds)

    p = engine.scenarios.active_problem
    engine.alerts.record_event(
        severity=p.get("severity", "WARNING"),
        event_type="Problem Scenario Injected",
        description=f"Injected: {p['name']}. {p['description']}",
        rack_id="SCENARIO",
        sim_time_str=engine.to_dict()["clock"]["elapsedFormatted"],
        action_taken="Physics Stress Injected",
    )
    return {"ok": True, "problem": engine.scenarios.active_problem}


@router.post("/workload")
async def set_workload(body: WorkloadRequest):
    if body.workloadId not in WORKLOAD_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown workload profile '{body.workloadId}'")

    engine.scenarios.set_workload(body.workloadId)
    engine.scenarios.apply_to_physics(engine.twin, elapsed_sec=engine.elapsed_seconds)

    w = engine.scenarios.active_workload
    engine.alerts.record_event(
        severity="INFO",
        event_type="Workload Profile Switched",
        description=f"Workload switched to: {w['name']}.",
        rack_id="SCHEDULER",
        sim_time_str=engine.to_dict()["clock"]["elapsedFormatted"],
        action_taken="Workload Dispatched",
    )
    return {"ok": True, "workload": engine.scenarios.active_workload}


@router.post("/combine")
async def combine_scenarios(body: CombineRequest):
    """
    Simulate combination: Weather + Problem + Workload simultaneously.
    """
    if body.weatherId in WEATHER_PRESETS:
        engine.weather.load_preset(body.weatherId)
    if body.problemId in FAILURE_SCENARIOS:
        engine.scenarios.set_problem(body.problemId)
    if body.workloadId in WORKLOAD_PRESETS:
        engine.scenarios.set_workload(body.workloadId)

    engine.twin.ambient_temp = engine.weather.ambient_temp
    engine.twin.ambient_humidity = engine.weather.humidity
    engine.scenarios.apply_to_physics(engine.twin, elapsed_sec=engine.elapsed_seconds)

    engine.alerts.record_event(
        severity="CRITICAL" if body.problemId != "none" else "INFO",
        event_type="Compound Scenario Activated",
        description=f"Combined stress: [{engine.weather.preset_id.capitalize()}] + [{engine.scenarios.active_problem['name']}] + [{engine.scenarios.active_workload['name']}].",
        rack_id="ORCHESTRATOR",
        sim_time_str=engine.to_dict()["clock"]["elapsedFormatted"],
        action_taken="Compound Stress Active",
    )

    return {
        "ok": True,
        "weather": engine.weather.to_dict(),
        "problem": engine.scenarios.active_problem,
        "workload": engine.scenarios.active_workload,
        "state": engine.to_dict(),
    }
