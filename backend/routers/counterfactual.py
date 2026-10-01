"""
Counterfactual & Optimization Router.
Provides endpoints for:
  - Multi-candidate intervention evaluations in cloned digital twins
  - Intervention execution / enforcement
  - Interactive What-If simulation with custom sliders (workload, power, cooling, airflow, ambient)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from simulation_engine import engine

router = APIRouter(prefix="/api/counterfactual", tags=["counterfactual"])


class ApplyInterventionRequest(BaseModel):
    actionId: str


class WhatIfRequest(BaseModel):
    workloadPct: Optional[float] = Field(default=None, ge=10.0, le=100.0)
    powerMultiplier: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)
    coolingSetpoint: Optional[float] = Field(default=None, ge=14.0, le=26.0)
    airflowCFM: Optional[float] = Field(default=None, ge=3000.0, le=14000.0)
    ambientTemp: Optional[float] = Field(default=None, ge=10.0, le=50.0)
    activeRacksCount: Optional[int] = Field(default=None, ge=1, le=12)
    horizonMinutes: int = Field(default=30, ge=5, le=120)


@router.post("/evaluate")
async def evaluate_interventions():
    """Run parallel counterfactual branch simulations across all candidate actions."""
    res = engine.optimizer.evaluate_all(engine.twin, horizon_steps=15)
    engine.last_optimization_result = res
    return res


@router.post("/apply")
async def apply_intervention(body: ApplyInterventionRequest):
    """Enact a chosen intervention onto the live Digital Twin."""
    action_id = body.actionId
    engine.optimizer.apply_action_to_twin(engine.twin, action_id)

    # Find intervention metadata
    from optimization_engine import CANDIDATE_INTERVENTIONS
    action_meta = next((a for a in CANDIDATE_INTERVENTIONS if a["id"] == action_id), {"title": action_id})

    rec_item = {
        "actionId": action_id,
        "title": action_meta.get("title", action_id),
        "appliedAtSec": engine.elapsed_seconds,
        "timestamp": engine.to_dict()["clock"]["elapsedFormatted"],
    }
    engine.interventions_history.append(rec_item)

    engine.alerts.record_event(
        severity="INFO",
        event_type="Intervention Enacted",
        description=f"Operator enacted intervention: {action_meta.get('title', action_id)}.",
        rack_id="OPTIMIZER",
        sim_time_str=engine.to_dict()["clock"]["elapsedFormatted"],
        action_taken="Control Action Dispatched",
    )

    return {"ok": True, "applied": rec_item, "state": engine.to_dict()}


@router.post("/what-if")
async def run_what_if(body: WhatIfRequest):
    """
    Run forward What-If Counterfactual Simulation comparing BEFORE vs AFTER
    under modified parameters.
    """
    res = engine.what_if.run_what_if_simulation(
        base_twin=engine.twin,
        workload_pct=body.workloadPct,
        power_multiplier=body.powerMultiplier,
        cooling_setpoint=body.coolingSetpoint,
        airflow_cfm=body.airflowCFM,
        ambient_temp=body.ambientTemp,
        active_racks_count=body.activeRacksCount,
        simulation_horizon_minutes=body.horizonMinutes,
    )
    return res
