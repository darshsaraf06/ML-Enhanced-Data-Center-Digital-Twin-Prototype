"""
ML Router - multi-horizon forecasting and model comparison.

Endpoints:
  GET /api/forecast  - T+5m/T+15m/T+30m forecasts for all racks
  GET /api/models    - model comparison metrics table
"""

from fastapi import APIRouter
from simulation_state import sim

router = APIRouter(prefix="/api", tags=["ml"])


@router.get("/forecast")
async def get_forecast():
    """Return ML multi-horizon temperature forecasts for all 8 racks."""
    return sim.ml.generate_datacenter_forecast(sim.physics)


@router.get("/models")
async def get_models():
    """Return model comparison metrics (MAE, RMSE, R², latency)."""
    return {
        "models": sim.ml.model_comparison,
        "selectedModel": sim.ml.selected_model,
        "isTrained": sim.ml._trained,
    }
