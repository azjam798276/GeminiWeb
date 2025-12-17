#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONUNBUFFERED=1
python3 -m uvicorn geminiweb_provider.server:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload

