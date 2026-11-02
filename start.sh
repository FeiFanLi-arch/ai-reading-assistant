#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r backend/requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
fi
echo "Reading Assistant: http://127.0.0.1:${PORT:-8000}"
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "${PORT:-8000}"
