# Milestone 1: OpenAI-compatible Chat Completions (Non-streaming)

## Deliverable

A working `POST /v1/chat/completions` endpoint that returns OpenAI-shaped JSON and is backed by the
official Gemini Developer API (`GOOGLE_API_KEY`).

## PR-sized Implementation Steps

### PR1 — Official API call

- Change: implement `GeminiOfficialSession.generate()` using official `generateContent`
- Files:
  - `src/geminiweb_provider/gemini_official_session.py`
- Acceptance:
  - Missing API key raises `AuthenticationError`
  - 401/403 mapped to `AuthenticationError`
  - 429 mapped to `RateLimitError`
  - Response parsing validates `candidates[0].content.parts[0].text`

### PR2 — OpenAI-compatible HTTP server

- Change: add FastAPI app exposing `POST /v1/chat/completions`
- Files:
  - `src/geminiweb_provider/server.py`
  - `src/geminiweb_provider/openai_compat.py`
  - `scripts/run_server.sh`
  - `Makefile`
- Acceptance:
  - `GET /healthz` returns `{"status":"ok"}`
  - `POST /v1/chat/completions` rejects `stream=true` with HTTP 400
  - Returns OpenAI-shaped JSON with `choices[0].message.role == "assistant"`

### PR3 — Docs and tests

- Change: document usage and add request-model sanity test
- Files:
  - `README.md`
  - `tests/test_openai_compat.py`
- Acceptance:
  - Docs include local run + `curl` examples
  - Tests run in a dev environment with `pytest`

## Smoke Test

1. Install:
   - `pip install -e ".[dev,server]"`
2. Configure:
   - `cp .env.example .env` and set `GOOGLE_API_KEY`
3. Run:
   - `make run`
4. Verify:
   - `curl http://localhost:8000/healthz`
   - `curl http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"gemini-1.5-pro","messages":[{"role":"user","content":"Say hi"}]}'`

## Status

- Approved by @engineering-director on 2025-12-17

