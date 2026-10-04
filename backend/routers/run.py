"""
Run API: start, control and inspect the live simulation, and export its results.
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from run_controller import ControllerError, controller
from run_store import list_runs, load_run

router = APIRouter(prefix="/api/run", tags=["run"])
logs_router = APIRouter(prefix="/api/runs", tags=["logs"])


def _call(fn, *args):
    try:
        return fn(*args)
    except ControllerError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


class Weights(BaseModel):
    energy: float = Field(default=1.0, ge=0, le=10)
    temperature: float = Field(default=1.0, ge=0, le=10)
    disruption: float = Field(default=1.0, ge=0, le=10)


class StartRequest(BaseModel):
    mode: str = Field(default="sim", pattern="^(sim|demo)$")
    numRacks: int = Field(default=8, ge=4, le=12)
    scale: str = Field(default="medium", pattern="^(small|medium|large)$")
    climate: str = "temperate"
    events: Union[str, List[str]] = "none"
    durationS: int = Field(default=3600, ge=300, le=86400)
    seed: int = 42
    mlModel: str = "xgboost"
    inletLimit: float = Field(default=27.0, ge=20.0, le=35.0)
    weights: Weights = Weights()
    gridFactor: float = Field(default=0.716, ge=0, le=2)
    priceKwh: float = Field(default=8.0, ge=0, le=100)
    priceWaterKl: float = Field(default=60.0, ge=0, le=1000)
    saveToLogs: bool = True


class SpeedRequest(BaseModel):
    speed: float


class Disturbance(BaseModel):
    kind: str = Field(default="heat_pulse", pattern="^(heat_pulse|inlet_offset)$")
    magnitude: float = Field(default=2.0, ge=-5, le=10)
    durationMin: float = Field(default=5, ge=1, le=60)


class RackRequest(BaseModel):
    util: Optional[float] = Field(default=None, ge=0, le=100)
    clearUtil: bool = False
    powerCapKw: Optional[float] = Field(default=None, ge=0.5, le=50)
    clearCap: bool = False
    airflowPct: Optional[float] = Field(default=None, ge=50, le=150)
    disturbance: Optional[Disturbance] = None


class EnvironmentRequest(BaseModel):
    climate: Optional[str] = None
    outsideTemp: Optional[float] = Field(default=None, ge=-20, le=55)
    humidity: Optional[float] = Field(default=None, ge=5, le=100)
    autoTemp: bool = False
    autoHumidity: bool = False
    event: Optional[str] = None


class DecisionRequest(BaseModel):
    actionId: str


@router.post("/start")
async def start(body: StartRequest):
    cfg = body.model_dump()
    return {"ok": True, **_call(controller.start, cfg), "state": controller.snapshot(include_new=False)}


@router.post("/pause")
async def pause():
    _call(controller.pause)
    return {"ok": True, "status": controller.status}


@router.post("/resume")
async def resume():
    _call(controller.resume)
    return {"ok": True, "status": controller.status}


@router.post("/end")
async def end():
    _call(controller.end)
    return {"ok": True, "status": controller.status}


@router.post("/skip")
async def skip():
    _call(controller.skip)
    return {"ok": True, "status": controller.status}


@router.post("/snooze")
async def snooze():
    _call(controller.snooze)
    return {"ok": True, "secondsLeft": controller.snooze_left()}


@router.post("/unsnooze")
async def unsnooze():
    _call(controller.unsnooze)
    return {"ok": True}


@router.post("/speed")
async def speed(body: SpeedRequest):
    _call(controller.set_speed, body.speed)
    return {"ok": True, "speed": controller.speed}


@router.post("/rack/{rack_id}")
async def rack(rack_id: int, body: RackRequest):
    cmd: Dict[str, Any] = {"type": "rack", "rackId": rack_id}
    if body.util is not None:
        cmd["util"] = body.util
    if body.clearUtil:
        cmd["clearUtil"] = True
    if body.clearCap:
        cmd["powerCapKw"] = None
    elif body.powerCapKw is not None:
        cmd["powerCapKw"] = body.powerCapKw
    if body.airflowPct is not None:
        cmd["airflowPct"] = body.airflowPct
    if body.disturbance is not None:
        cmd["disturbance"] = body.disturbance.model_dump()
    if len(cmd) == 2:
        raise HTTPException(status_code=400, detail="No change requested")
    _call(controller.submit, cmd)
    return {"ok": True, "queued": cmd}


@router.post("/environment")
async def environment(body: EnvironmentRequest):
    cmd: Dict[str, Any] = {"type": "environment"}
    if body.climate:
        cmd["climate"] = body.climate
    if body.autoTemp:
        cmd["outsideTemp"] = None
    elif body.outsideTemp is not None:
        cmd["outsideTemp"] = body.outsideTemp
    if body.autoHumidity:
        cmd["humidity"] = None
    elif body.humidity is not None:
        cmd["humidity"] = body.humidity
    if body.event:
        cmd["event"] = body.event
    if len(cmd) == 1:
        raise HTTPException(status_code=400, detail="No change requested")
    _call(controller.submit, cmd)
    return {"ok": True, "queued": cmd}


@router.post("/decision")
async def decision(body: DecisionRequest):
    _call(controller.decide, body.actionId)
    return {"ok": True, "status": controller.status}


@router.get("/state")
async def state():
    snap = controller.snapshot(include_new=False)
    return snap


@router.get("/series")
async def series():
    return controller.series()


@router.get("/results")
async def results():
    return {"status": controller.results_status, "results": controller.results}


def _export_response(res, format: str) -> Response:
    import results_export as rx
    name = f"{res['runId']}_results"
    if format == "pdf":
        data, media, ext = rx.to_pdf(res), "application/pdf", "pdf"
    elif format == "csv":
        data, media, ext = rx.to_csv(res), "text/csv", "csv"
    else:
        data, media, ext = rx.to_json(res), "application/json", "json"
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})


@router.get("/export")
async def export(format: str = Query("json", pattern="^(json|csv|pdf)$")):
    res = controller.results
    if res is None:
        raise HTTPException(status_code=409, detail="Results are not ready yet")
    return _export_response(res, format)


# ── past logs ────────────────────────────────────────────────────────────────
@logs_router.get("")
async def runs_list(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    runs = list_runs()
    return {"total": len(runs), "runs": runs[offset:offset + limit]}


@logs_router.get("/{run_id}")
async def runs_get(run_id: str):
    res = load_run(run_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Saved run not found")
    return res


@logs_router.get("/{run_id}/export")
async def runs_export(run_id: str, format: str = Query("json", pattern="^(json|csv|pdf)$")):
    res = load_run(run_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Saved run not found")
    return _export_response(res, format)
