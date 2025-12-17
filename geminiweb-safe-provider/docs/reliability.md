# Reliability (v2 hardening)

## SLO targets (service-level)

These are pragmatic targets for the OpenAI-compatible endpoint (`POST /v1/chat/completions`), assuming the upstream
Gemini API is healthy:

- Availability: 99% non-5xx responses (rolling 1h)
- Latency (non-stream): p95 < 30s, p99 < 60s
- Streaming: time-to-first-token < 10s (p95), with an idle timeout to prevent hung connections

## Retry policy (upstream)

The upstream client retries (bounded) on:

- transient network failures (`httpx.HTTPError`)
- upstream timeouts
- HTTP `429` (respects `Retry-After` when present)
- upstream `5xx`

It does not retry on authentication failures (`401/403`) or other upstream `4xx` responses.

## Circuit breaker

When upstream requests fail consecutively, a circuit breaker opens for a short window to avoid thundering-herd retries.
While open, requests fail fast with HTTP `503` and `Retry-After`.

Configuration:

- `UPSTREAM_CIRCUIT_BREAKER_FAILURES` (default `5`) – consecutive failures before opening
- `UPSTREAM_CIRCUIT_BREAKER_RESET_SECONDS` (default `30`) – how long to stay open

## Server-side timeouts (end-to-end)

The server enforces end-to-end deadlines for `POST /v1/chat/completions` so requests can’t hang forever even if the
upstream does.

- Non-stream: `CHAT_COMPLETIONS_TIMEOUT_SECONDS` (default `90`)
- Stream idle timeout: `CHAT_COMPLETIONS_STREAM_IDLE_TIMEOUT_SECONDS` (default `30`)
- Stream total timeout: `CHAT_COMPLETIONS_STREAM_TOTAL_TIMEOUT_SECONDS` (default `300`)

On timeout the server returns HTTP `504`.

## Error IDs

Every response includes `X-Request-Id`. Error responses also set `error.code` to the same value so clients can
correlate failures with server logs.
