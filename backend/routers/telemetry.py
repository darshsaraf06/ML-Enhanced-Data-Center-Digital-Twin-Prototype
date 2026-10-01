"""
Telemetry Router - live physics state and simulation control.

Endpoints:
  GET  /api/state           - full datacenter state snapshot
  POST /api/step            - advance simulation by N ticks
  POST /api/rack/{id}/update - update a rack's CPU load / fan speed
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from simulation_state import sim

router = APIRouter(prefix="/api", tags=["telemetry"])


class StepRequest(BaseModel):
    ticks: int = Field(default=1, ge=1, le=50)


class RackUpdateRequest(BaseModel):
    cpuLoad:  Optional[int] = Field(default=None, ge=10, le=100)
    fanSpeed: Optional[int] = Field(default=None, ge=20, le=100)


# ---------------------------------------------------------------------------
@router.get("/state")
async def get_state():
    """Return full serialised datacenter state including all racks."""
    return sim.full_state()


# ---------------------------------------------------------------------------
@router.post("/step")
async def step_simulation(body: StepRequest):
    """Advance the physics simulation by N ticks (1 tick = 1 second)."""
    snap = await sim.tick(body.ticks)
    return {
        "ok": True,
        "ticks": body.ticks,
        "snapshot": snap,
        "racks": sim.physics.racks,
    }


# ---------------------------------------------------------------------------
@router.post("/rack/{rack_id}/update")
async def update_rack(rack_id: int, body: RackUpdateRequest):
    """Interactively update a rack's CPU load and/or fan speed."""
    rack = next((r for r in sim.physics.racks if r["id"] == rack_id), None)
    if rack is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Rack {rack_id} not found")

    if body.cpuLoad is not None:
        rack["cpuLoad"] = body.cpuLoad
    if body.fanSpeed is not None:
        rack["fanSpeed"] = body.fanSpeed

    return {"ok": True, "rack": rack}
