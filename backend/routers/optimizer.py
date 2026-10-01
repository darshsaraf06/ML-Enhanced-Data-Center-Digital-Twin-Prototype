"""
Optimizer Router - counterfactual evaluation and intervention application.

Endpoints:
  POST /api/optimize            - evaluate all candidate interventions
  POST /api/apply-intervention  - apply chosen intervention to live state
"""

from fastapi import APIRouter
from pydantic import BaseModel
from simulation_state import sim

router = APIRouter(prefix="/api", tags=["optimizer"])


class ApplyInterventionRequest(BaseModel):
    actionId: str


@router.post("/optimize")
async def run_optimizer():
    """
    Clone the live physics state, simulate all 5 candidate interventions,
    and return results ranked by multi-objective cost score.
    """
    results = sim.optimizer.run_counterfactual_evaluation(sim.physics)
    return results


@router.post("/apply-intervention")
async def apply_intervention(body: ApplyInterventionRequest):
    """Apply the chosen intervention directly to the live physics state."""
    action_id = body.actionId
    physics = sim.physics

    if action_id == "airflow_boost":
        physics.crah_airflow_cfm += 1500
        for r in physics.racks:
            r["fanSpeed"] = min(100, r["fanSpeed"] + 15)

    elif action_id == "chiller_boost":
        physics.cooling_supply_temp = max(14.0, physics.cooling_supply_temp - 2.0)

    elif action_id in ("workload_migration", "proactive_combined"):
        sorted_racks = sorted(physics.racks, key=lambda r: r["temp"], reverse=True)
        hot, cool = sorted_racks[0], sorted_racks[-1]
        if hot["cpuLoad"] > 40:
            shift = min(20, hot["cpuLoad"] - 30)
            hot["cpuLoad"] -= shift
            cool["cpuLoad"] = min(100, cool["cpuLoad"] + shift)
        if action_id == "proactive_combined":
            physics.cooling_supply_temp = max(16.0, physics.cooling_supply_temp - 1.0)

    snap = await sim.tick(1)
    return {
        "ok": True,
        "appliedAction": action_id,
        "snapshot": snap,
        "racks": physics.racks,
    }
