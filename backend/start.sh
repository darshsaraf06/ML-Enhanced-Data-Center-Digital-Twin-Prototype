#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ML Data Center Digital Twin - Backend Startup Script
# Usage: cd backend && bash start.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
UVICORN_BIN="$VENV_DIR/bin/uvicorn"

echo "══════════════════════════════════════════════════════════════"
echo "  ML-Enhanced Data Center Digital Twin - Backend Startup"
echo "══════════════════════════════════════════════════════════════"

# ── 1. Create virtual environment if needed ───────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[SETUP] Creating Python virtual environment…"
    python3 -m venv "$VENV_DIR"
fi

# ── 2. Install / upgrade dependencies ────────────────────────────────────────
echo "[SETUP] Installing Python dependencies…"
"$PIP_BIN" install --quiet --upgrade pip
"$PIP_BIN" install --quiet -r requirements.txt

echo "[SETUP] ✓ Dependencies ready"

# ── 3. Launch uvicorn ────────────────────────────────────────────────────────
echo ""
echo "  → Frontend: http://localhost:8000/"
echo "  → API docs: http://localhost:8000/docs"
echo "  → WebSocket: ws://localhost:8000/ws"
echo ""
echo "[API] Starting uvicorn on port 8000…"
echo "══════════════════════════════════════════════════════════════"

"$UVICORN_BIN" main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
