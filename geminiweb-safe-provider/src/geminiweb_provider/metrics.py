from __future__ import annotations

from prometheus_client import Counter, Histogram, start_http_server

server_requests_total = Counter(
    "server_requests_total",
    "Total HTTP requests handled by server",
    labelnames=["path", "status"],
)

server_request_latency_seconds = Histogram(
    "server_request_latency_seconds",
    "HTTP request latency (seconds)",
    buckets=[0.05, 0.1, 0.3, 0.5, 1, 2, 5, 10, 30, 60, 120, 300],
    labelnames=["path"],
)

server_errors_total = Counter(
    "server_errors_total",
    "Total errors returned by server",
    labelnames=["type"],
)

upstream_circuit_breaker_events_total = Counter(
    "upstream_circuit_breaker_events_total",
    "Circuit breaker events",
    labelnames=["event"],
)

requests_total = Counter(
    "provider_requests_total",
    "Total requests handled by provider",
    labelnames=["provider", "status"],
)

request_latency_seconds = Histogram(
    "provider_request_latency_seconds",
    "Provider request latency",
    buckets=[0.1, 0.3, 0.5, 1, 2, 5, 10, 30, 60],
    labelnames=["provider"],
)


def maybe_start_metrics(*, enable: bool, bind: str, port: int) -> None:
    if not enable:
        return
    start_http_server(port, addr=bind)
