#!/usr/bin/env bash
# Sphere Solar — one-command launcher for macOS / Linux.
# Starts the FastAPI backend and the Expo mobile app together, and shuts
# both down cleanly on Ctrl+C. (Windows users: use start.bat instead.)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PORT=8000

# ── Locate the backend virtualenv (.venv preferred, venv fallback) ───────────
if   [ -d "backend/.venv" ]; then VENV="backend/.venv"
elif [ -d "backend/venv"  ]; then VENV="backend/venv"
else
  echo "[!] No backend virtualenv found. Create it first:"
  echo "    python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

if [ ! -d "mobile/node_modules" ]; then
  echo "[*] Installing mobile dependencies (first run)…"
  (cd mobile && npm install)
fi

# ── Detect LAN IP ────────────────────────────────────────────────────────────
LOCAL_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"
[ -z "$LOCAL_IP" ] && LOCAL_IP="localhost"

# ── Keep mobile/.env pointed at this machine (IP changes between networks) ───
# EXPO_PUBLIC_* vars are inlined at bundle time, so write it before Expo starts.
API_URL="http://$LOCAL_IP:$PORT"
if [ ! -f mobile/.env ] || ! grep -q "^EXPO_PUBLIC_API_URL=$API_URL$" mobile/.env 2>/dev/null; then
  echo "[*] Pointing mobile/.env at $API_URL"
  printf 'EXPO_PUBLIC_API_URL=%s\n' "$API_URL" > mobile/.env
fi

# ── Free the port if a stale backend is still holding it ─────────────────────
stale="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
if [ -n "$stale" ]; then
  echo "[*] Port $PORT in use by PID(s) $stale — stopping stale backend…"
  kill $stale 2>/dev/null || true
  sleep 1
  # Force-kill anything that ignored SIGTERM.
  kill -9 $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null) 2>/dev/null || true
fi

# ── Shut the backend down when this script exits ─────────────────────────────
backend_pid=""
cleanup() {
  echo
  echo "Stopping services…"
  [ -n "$backend_pid" ] && kill "$backend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "============================================"
echo "  Sphere Solar | Launching Services"
echo "============================================"

# ── Backend (FastAPI on :8000) — runs in background ──────────────────────────
echo "[1/2] Backend  → http://localhost:$PORT  (docs: /docs)"
(
  cd backend
  exec "$ROOT/$VENV/bin/uvicorn" app.main:app \
    --reload --host 0.0.0.0 --port "$PORT" --env-file .env
) &
backend_pid=$!

sleep 3  # let the backend bind before Expo starts

echo
echo "  Backend API : http://localhost:$PORT"
echo "  Your LAN IP : http://$LOCAL_IP:$PORT"
echo "  Physical device? set EXPO_PUBLIC_API_URL=http://$LOCAL_IP:$PORT in mobile/.env"
echo
echo "  Press Ctrl+C to stop everything."
echo "============================================"

# ── Mobile (Expo) — runs in the FOREGROUND so keyboard commands work ─────────
echo "[2/2] Mobile   → Expo (press i/a/w for iOS/Android/web, or scan the QR)"
# Not exec'd: keeps the cleanup trap alive so Ctrl+C also stops the backend.
( cd mobile && npx expo start )
