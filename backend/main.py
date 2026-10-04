"""
Data Center Digital Twin - FastAPI backend.

  * REST API under /api (run control, catalog, About-the-project data)
  * WebSocket /ws pushes the latest run state twice per second while it changes
  * Serves the single-page frontend (index.html, theme.css, js/)

The simulation itself runs in a worker thread owned by run_controller.controller.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from forecasting_engine import Forecaster, load_metrics
from routers import about, run
from run_controller import controller
from ws_manager import manager

BACKEND_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = BACKEND_DIR.parent.resolve()


async def broadcast_loop():
    """Send the latest server state to every client whenever it changed."""
    last_version = -1
    last_sent = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            now = loop.time()
            if manager.active and (controller.version != last_version or now - last_sent > 5.0):
                snap = controller.snapshot(include_new=True)
                last_version = snap["version"]
                cursors = snap.pop("_cursors", None)
                await manager.broadcast(snap)
                if cursors:
                    snap["_cursors"] = cursors
                    controller.advance_cursors(snap)
                last_sent = now
        except Exception as exc:
            print(f"[WS] broadcast error: {exc!r}")
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(broadcast_loop())
    models = Forecaster.available_models()
    print(f"[API] Forecast models available: {', '.join(models)}")
    if not load_metrics():
        print("[API] No trained models found: run scripts/train_models.py (persistence forecasts are used until then)")
    yield
    for ws in list(manager.active):      # close sockets so a reload never waits on them
        try:
            await ws.close()
        except Exception:
            pass
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Data Center Digital Twin API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(run.router)
app.include_router(run.logs_router)
app.include_router(about.router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_text(json.dumps(controller.snapshot(include_new=False)))
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


@app.get("/api/health")
async def health():
    return {"status": "ok", "wsClients": len(manager.active), "runStatus": controller.status,
            "runId": controller.run_id, "models": Forecaster.available_models()}


# ── frontend (only the app files are served) ────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/theme.css")
async def stylesheet():
    return FileResponse(FRONTEND_DIR / "theme.css", media_type="text/css")


app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
