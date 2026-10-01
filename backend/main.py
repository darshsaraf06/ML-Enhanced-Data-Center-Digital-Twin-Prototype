"""
ML-Enhanced Data Center Digital Twin - FastAPI Backend
=======================================================
Starts a FastAPI server that:
  • Serves the static engineering frontend (../index.html, ../js/, ../style.css)
  • Exposes REST API under /api/
  • Provides a WebSocket at /ws for real-time state broadcasts
  • Runs a background task that steps the physics simulation every second
    and pushes the new state to all connected WebSocket clients
  • Trains ML models asynchronously after startup (non-blocking)
"""

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from simulation_state import sim
from ws_manager import manager
from routers import telemetry, ml, optimizer, benchmark, scenario, simulation, counterfactual, report, experiments

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = BACKEND_DIR.parent.resolve()   # /dc proj/


# ── Background simulation loop ───────────────────────────────────────────────
async def simulation_loop():
    """Advance physics every second and broadcast state to WebSocket clients."""
    while True:
        try:
            await sim.tick(1)
            if manager.active:
                state = sim.full_state()
                await manager.broadcast(state)
        except Exception as exc:
            print(f"[SIM] Simulation loop error: {exc}")
        await asyncio.sleep(1.0)


async def train_ml_background():
    """Train ML models in a thread pool so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    try:
        print("[ML] Starting multi-horizon XGBoost training in background thread…")
        await loop.run_in_executor(None, lambda: sim.engine.forecasting.train_synthetic(n_samples=250))
        print("[ML] ✓ Model training complete - real multi-horizon XGBoost inference active")
    except Exception as exc:
        print(f"[ML] Training notice (using analytic fallback): {exc}")


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start simulation loop
    sim_task = asyncio.create_task(simulation_loop())
    # Start ML training (non-blocking)
    asyncio.create_task(train_ml_background())
    print("[API] ✓ Data Center Digital Twin backend started on http://localhost:8000")
    print("[API] ✓ Frontend served at http://localhost:8000/")
    yield
    sim_task.cancel()
    try:
        await sim_task
    except asyncio.CancelledError:
        pass


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ML-Enhanced Data Center Digital Twin API",
    description="Physics-informed RC thermal engine with ML predictive forecasting and counterfactual optimization.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register API routers ──────────────────────────────────────────────────────
app.include_router(simulation.router)
app.include_router(telemetry.router)
app.include_router(ml.router)
app.include_router(optimizer.router)
app.include_router(counterfactual.router)
app.include_router(benchmark.router)
app.include_router(scenario.router)
app.include_router(experiments.router)
app.include_router(report.router)


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # Send full state immediately on connect
    try:
        await ws.send_text(json.dumps(sim.full_state()))
    except Exception:
        manager.disconnect(ws)
        return

    try:
        while True:
            # Keep connection alive; simulation loop handles broadcasts
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg == "step":
                await sim.tick(1)
                await ws.send_text(json.dumps(sim.full_state()))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "wsClients": len(manager.active),
        "simMode": sim.engine.mode,
        "simStatus": sim.engine.status,
        "simClock": sim.engine.to_dict()["clock"],
        "mlTrained": sim.engine.forecasting._trained,
    }


# ── Serve static frontend ─────────────────────────────────────────────────────
# Mounted LAST so API routes take priority
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
