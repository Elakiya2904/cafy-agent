#!/usr/bin/env bash
# macOS / Linux launcher for the Cafy Agent development servers (Windows: backend/start.bat).
# Installs/updates Python packages with uv, frees port 8000, then starts the FastAPI backend and
# the Vite frontend. Press Ctrl+C to stop both.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it with:  brew install uv   (or: curl -LsSf https://astral.sh/uv/install.sh | sh)"
  exit 1
fi

echo "================================================================"
echo "  Cafy Agent - Starting Backend + Frontend"
echo "================================================================"

uv sync --quiet
[ -d frontend/node_modules ] || npm --prefix frontend install

# Free port 8000 if an old backend is still running.
if command -v lsof >/dev/null 2>&1; then
  old_pids="$(lsof -ti tcp:8000 -sTCP:LISTEN || true)"
  [ -n "$old_pids" ] && kill $old_pids 2>/dev/null || true
fi

echo "[1/2] Starting Backend on http://127.0.0.1:8000 ..."
uv run backend/run.py &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

sleep 4
echo "[2/2] Starting Frontend on http://127.0.0.1:5173 ..."
echo "================================================================"
echo "  Backend  : http://127.0.0.1:8000   (API + static fallback)"
echo "  Frontend : http://127.0.0.1:5173   (Vite dev server)"
echo "================================================================"
npm --prefix frontend run dev
