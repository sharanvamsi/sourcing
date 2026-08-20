#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
PIP_BIN="$PROJECT_DIR/venv/bin/pip"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$PROJECT_DIR/venv"
fi

if ! "$PYTHON_BIN" -c 'import fastapi, jwt, sendgrid, uvicorn' 2>/dev/null; then
  echo "Installing backend dependencies..."
  "$PIP_BIN" install -r "$PROJECT_DIR/requirements.txt" -r "$PROJECT_DIR/backend/requirements.txt"
fi

if [[ ! -d "$PROJECT_DIR/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  npm --prefix "$PROJECT_DIR/frontend" install
fi

echo "Starting API at http://127.0.0.1:8000"
(
  cd "$PROJECT_DIR"
  "$PYTHON_BIN" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "Starting Sourcing UI at http://127.0.0.1:3000"
(
  cd "$PROJECT_DIR/frontend"
  npm run dev -- --hostname 127.0.0.1 --port 3000
) &
FRONTEND_PID=$!

echo ""
echo "Open http://localhost:3000/login"
echo "Press Ctrl+C to stop both services."
echo ""

wait "$BACKEND_PID" "$FRONTEND_PID"
