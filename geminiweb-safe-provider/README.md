# geminiweb-safe-provider

A from-scratch Linux/Python project scaffold for an OpenAI-compatible provider that calls
**official** Google Gemini/Vertex APIs (no web UI reverse engineering).

## Quick start (Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,server]"

cp .env.example .env
# edit .env with your API key / config
make test
make run
```

## Run tests

From the repo root:

```bash
cd geminiweb-safe-provider
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```

## 10-minute runbook

See `docs/runbook.md`.

## What’s inside

- Provider contract + router contracts
- Credential storage with encryption at rest (Fernet)
- Structured logging
- Prometheus metrics endpoint (optional)
- Session wrapper designed for official Gemini API calls (stubbed)

## Environment

See `.env.example`.

## Notes

This scaffold intentionally avoids any code that automates or reverse-engineers consumer
web session flows (cookies, hidden tokens, private batchexecute endpoints, etc.).
Use official APIs for compliance and stability.

## Design docs

- `docs/scope.md`
- `docs/architecture.md`
- `docs/milestone-1.md`
- `docs/openai-compatibility.md`
- `docs/release.md`
- `docs/reliability.md`
- `docs/runbook.md`
- `docs/shipping.md`

## Try the OpenAI-compatible endpoint

```bash
curl http://localhost:8000/healthz

curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemini-1.5-pro","messages":[{"role":"user","content":"Say hi"}]}'
```

Optional streaming (Milestone 2; set `ENABLE_STREAMING=true`):

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemini-1.5-pro","stream":true,"messages":[{"role":"user","content":"Stream a short reply."}]}'
```

Minimal server command (no `make`):

```bash
python3 -m uvicorn geminiweb_provider.server:app --host 0.0.0.0 --port 8000 --reload
```

Console script (installed via `pip`):

```bash
geminiweb-safe-provider
```
