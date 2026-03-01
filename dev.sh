#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Backend ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Starting BlindSight Backend ==="
if [ ! -f "$ROOT/blindsight-backend/.env" ]; then
  echo "WARNING: .env not found — copy .env.example and fill in your API keys"
  echo "  cp blindsight-backend/.env.example blindsight-backend/.env"
  echo "Backend will not connect without keys. Skipping backend start."
else
  cd "$ROOT/blindsight-backend"
  source .venv/bin/activate || true
  python main.py --call-type default --call-id blindsight-live &
  BACKEND_PID=$!
  echo "Backend PID: $BACKEND_PID"
fi

# ── Frontend ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Starting BlindSight Frontend ==="
if [ ! -f "$ROOT/blindsight-frontend/.env.local" ]; then
  echo "WARNING: .env.local not found — copy .env.local.example and fill in your API key"
  echo "  cp blindsight-frontend/.env.local.example blindsight-frontend/.env.local"
fi

cd "$ROOT/blindsight-frontend"
npm run dev
