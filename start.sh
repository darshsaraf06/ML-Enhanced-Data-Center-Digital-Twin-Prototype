#!/usr/bin/env bash
# Start the Data Center Digital Twin on http://127.0.0.1:8000 (Linux / macOS).
# Creates ./venv on first use and installs backend/requirements.txt into it.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ ! -d venv ]; then
    python3.11 -m venv venv
    venv/bin/pip install --upgrade pip
    venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt
fi
exec venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
