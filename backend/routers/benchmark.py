"""
Benchmark Router - research ablation metrics.

Endpoints:
  GET  /api/benchmark        - cumulative 3-approach benchmark summary
  POST /api/benchmark/reset  - reset accumulated benchmark metrics
"""

from fastapi import APIRouter
from simulation_state import sim

router = APIRouter(prefix="/api", tags=["benchmark"])


@router.get("/benchmark")
async def get_benchmark():
    """Return cumulative comparative benchmark and ablation table data."""
    return sim.benchmark.get_summary()


@router.post("/benchmark/reset")
async def reset_benchmark():
    """Reset benchmark metrics (useful when switching scenarios)."""
    sim.benchmark.reset()
    return {"ok": True, "message": "Benchmark metrics reset"}
