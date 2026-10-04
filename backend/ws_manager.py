"""
WebSocket Connection Manager.
Broadcasts live telemetry state to all connected clients every second.
"""

import asyncio
import json
from typing import Set
from fastapi import WebSocket


def _to_builtin(obj):
    """Convert numpy scalars and arrays that may appear in simulation state."""
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class WSConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, data: dict):
        """Send JSON payload to all connected WebSocket clients."""
        if not self.active:
            return
        payload = json.dumps(data, default=_to_builtin)
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = WSConnectionManager()
