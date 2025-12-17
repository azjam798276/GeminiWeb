# Runbook (10-minute setup)

## Goal

In ~10 minutes you should be able to:

1. Start the local server
2. Hit `GET /healthz`
3. Call `POST /v1/chat/completions` and receive OpenAI-shaped JSON

## Prereqs

- Python 3.10+
- A Gemini Developer API key in `GOOGLE_API_KEY`

## Setup

```bash
cd geminiweb-safe-provider
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,server]"

cp .env.example .env
# edit .env and set GOOGLE_API_KEY=...
```

## Run (minimal command)

```bash
export $(grep -v '^#' .env | xargs) || true
python3 -m uvicorn geminiweb_provider.server:app --host 0.0.0.0 --port 8000 --reload
```

## Smoke test

```bash
curl -sS http://localhost:8000/healthz

curl -sS http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemini-1.5-pro","messages":[{"role":"user","content":"Say hi in one sentence."}]}'
```

## Optional: streaming (Milestone 2)

Set `ENABLE_STREAMING=true` in `.env`, then:

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemini-1.5-pro","stream":true,"messages":[{"role":"user","content":"Stream 5 words."}]}'
```

## Troubleshooting

- `ModuleNotFoundError: fastapi` / `uvicorn`: install server deps: `pip install -e ".[server]"`
- 401 auth error: ensure `GOOGLE_API_KEY` is set and valid
- 429 rate limit: reduce request rate; increase `UPSTREAM_MAX_ATTEMPTS` or backoff settings in `.env`
- 503 upstream temporarily unavailable: circuit breaker may be open (tune `UPSTREAM_CIRCUIT_BREAKER_*`)
- 504 timeout: tune `CHAT_COMPLETIONS_TIMEOUT_SECONDS` (and streaming timeout settings)
- Metrics port conflict: set `ENABLE_METRICS=false` or change `METRICS_PORT`
- Request rejected with `invalid_request_error`: `tool` messages are rejected; streaming requires `ENABLE_STREAMING=true`
