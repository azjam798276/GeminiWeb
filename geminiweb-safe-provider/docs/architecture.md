# Architecture (Milestone 1)

## Core Flow

Request path (non-streaming):

`server.py` (FastAPI) → `openai_compat.py` (OpenAI request/response models) → `provider.py`
→ `gemini_official_session.py` (official Gemini Developer API HTTP call)

## Module Responsibilities

- `src/geminiweb_provider/server.py`
  - Hosts `POST /v1/chat/completions`
  - Validates request shape via Pydantic models
  - Rejects unsupported features (e.g., `stream=true`)
  - Delegates to `GeminiProvider`

- `src/geminiweb_provider/openai_compat.py`
  - Pydantic models for an OpenAI-compatible subset
  - Helpers to translate OpenAI `messages[]` into provider message dicts
  - Helper to generate OpenAI-shaped response JSON

- `src/geminiweb_provider/provider.py`
  - Provider facade used by the server/router
  - Maps messages to a single prompt (M1: last `user` message)
  - Emits Prometheus metrics and structured error logs

- `src/geminiweb_provider/gemini_official_session.py`
  - Performs the official Gemini Developer API call (`generateContent`)
  - Handles auth errors (401/403), rate limiting (429), and response-shape validation

## Configuration and Environment

- Config model: `src/geminiweb_provider/config.py::GeminiProviderConfig`
- Environment variables:
  - `GOOGLE_API_KEY` (required for upstream calls)
  - `ENABLE_METRICS`, `METRICS_BIND`, `METRICS_PORT`
  - `LOG_LEVEL`, `LOG_FORMAT`
- Encrypted credential store (`src/geminiweb_provider/credential_store.py`) remains available for
  future auth/token flows, but is not required for M1’s API-key based path.

## Error Taxonomy

- `AuthenticationError`: missing/invalid API key or upstream rejects credentials
- `RateLimitError`: upstream 429 with optional `retry_after_seconds`
- `UpstreamProtocolError`: upstream response is missing required fields / unexpected shape
- `ConfigurationError`: invalid request/mapping preconditions (e.g., no `user` content)

## Observability

- Logging: `src/geminiweb_provider/logging.py` configures `structlog` JSON or console output
- Metrics:
  - `provider_requests_total{provider,status}`
  - `provider_request_latency_seconds{provider}`
  - Exported via `prometheus_client.start_http_server` when enabled

## Status

- Approved by @engineering-director on 2025-12-17

