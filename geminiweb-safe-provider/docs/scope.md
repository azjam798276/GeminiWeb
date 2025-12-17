# Scope (Milestone 1)

## Summary

Deliver an OpenAI-compatible `POST /v1/chat/completions` endpoint (non-streaming) backed by the
**official** Gemini Developer API using `GOOGLE_API_KEY`. Include structured logging and optional
Prometheus metrics.

## In Scope

- OpenAI-compatible `POST /v1/chat/completions` (non-streaming only)
- Backing implementation via official Gemini Developer API `generateContent`
- Minimal message mapping (`messages[]` → a single user prompt)
- Basic structured logging (`structlog`)
- Optional Prometheus metrics exporter
- Local developer workflow: install, configure `.env`, run server, `curl` smoke test

## Out of Scope (Non-goals for M1)

- Streaming (`stream=true`)
- Tool/function calling
- Images/audio/multimodal input
- Embeddings
- Batching
- Multi-provider routing / tier-based selection beyond the existing scaffold types
- Vertex AI authentication (project/location + ADC)
- Persistent conversation state / long-term chat memory

## Risks

- Upstream schema changes (Gemini Developer API is currently accessed via `v1beta`)
- Rate limiting and retry behavior (HTTP 429 / `Retry-After`)
- Prompt/message mapping quality (multi-turn chat condensed to a single prompt in M1)
- Secret handling and misconfiguration (missing/invalid `GOOGLE_API_KEY`)
- Observability overhead (metrics server binding/port conflicts; logging verbosity)

## Success Metrics / Acceptance Criteria

- `curl` to `/v1/chat/completions` returns valid OpenAI-shaped JSON with an assistant message
- Unit tests pass in a configured dev environment (`pytest`)
- Codebase contains **no** web UI reverse engineering (cookies, hidden tokens, private endpoints)
- Docs clearly describe local setup, environment variables, and a basic smoke test

## Status

- Approved by @engineering-director on 2025-12-17

