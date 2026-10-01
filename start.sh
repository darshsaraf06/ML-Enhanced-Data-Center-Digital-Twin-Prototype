#!/usr/bin/env bash
# ML Data Center Digital Twin - Root Startup Script
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR/backend"
bash start.sh
