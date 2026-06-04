#!/usr/bin/env bash
PORT=${PORT:-8080}
cd "$(dirname "$0")"
set -a; source .env 2>/dev/null; set +a
exec ~/project/DownTube/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
