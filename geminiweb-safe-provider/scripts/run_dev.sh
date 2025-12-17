#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
python3 -c "from geminiweb_provider.config import GeminiProviderConfig; from geminiweb_provider.metrics import maybe_start_metrics; cfg=GeminiProviderConfig(); maybe_start_metrics(enable=cfg.enable_metrics, bind=cfg.metrics_bind, port=cfg.metrics_port); print('metrics ready (if enabled)')"
python3 -c "print('Scaffold ready. Integrate into your server/router next.')"
