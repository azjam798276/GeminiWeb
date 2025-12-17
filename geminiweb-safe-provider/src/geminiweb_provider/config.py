from __future__ import annotations

import os

from pydantic import BaseModel, Field


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class GeminiProviderConfig(BaseModel):
    # Credential storage
    credentials_path: str = Field(default="credentials.enc")

    # Official API settings
    google_api_key: str | None = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    vertex_project_id: str | None = Field(default_factory=lambda: os.getenv("VERTEX_PROJECT_ID"))
    vertex_location: str = Field(default_factory=lambda: os.getenv("VERTEX_LOCATION", "us-central1"))

    # Encryption
    fernet_key: str | None = Field(default_factory=lambda: os.getenv("CREDENTIALS_FERNET_KEY"))

    # Observability
    enable_metrics: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_METRICS", "false").lower() == "true"
    )
    metrics_bind: str = Field(default_factory=lambda: os.getenv("METRICS_BIND", "127.0.0.1"))
    metrics_port: int = Field(default_factory=lambda: int(os.getenv("METRICS_PORT", "9109")))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_format: str = Field(default_factory=lambda: os.getenv("LOG_FORMAT", "json"))
    enable_streaming: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_STREAMING", "false").lower() == "true"
    )

    # Server hardening
    server_auth_token: str | None = Field(default_factory=lambda: os.getenv("SERVER_AUTH_TOKEN"))
    enable_api_docs: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_API_DOCS", "false").lower() == "true"
    )
    allowed_hosts: list[str] = Field(default_factory=lambda: _parse_csv(os.getenv("ALLOWED_HOSTS")))
    cors_allow_origins: list[str] = Field(default_factory=lambda: _parse_csv(os.getenv("CORS_ALLOW_ORIGINS")))
    cors_allow_credentials: bool = Field(
        default_factory=lambda: os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
    )
    max_request_body_bytes: int = Field(
        default_factory=lambda: int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))
    )
    max_inflight_requests: int = Field(default_factory=lambda: int(os.getenv("MAX_INFLIGHT_REQUESTS", "32")))
    max_messages: int = Field(default_factory=lambda: int(os.getenv("MAX_MESSAGES", "64")))
    max_total_message_chars: int = Field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_MESSAGE_CHARS", "20000"))
    )

    # HTTP behavior (hardening)
    upstream_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60"))
    )
    upstream_max_attempts: int = Field(default_factory=lambda: int(os.getenv("UPSTREAM_MAX_ATTEMPTS", "3")))
    upstream_backoff_initial_seconds: float = Field(
        default_factory=lambda: float(os.getenv("UPSTREAM_BACKOFF_INITIAL_SECONDS", "0.5"))
    )
    upstream_backoff_max_seconds: float = Field(
        default_factory=lambda: float(os.getenv("UPSTREAM_BACKOFF_MAX_SECONDS", "8.0"))
    )
    upstream_circuit_breaker_failures: int = Field(
        default_factory=lambda: int(os.getenv("UPSTREAM_CIRCUIT_BREAKER_FAILURES", "5"))
    )
    upstream_circuit_breaker_reset_seconds: float = Field(
        default_factory=lambda: float(os.getenv("UPSTREAM_CIRCUIT_BREAKER_RESET_SECONDS", "30"))
    )

    # Server request timeouts (end-to-end deadlines)
    chat_completions_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("CHAT_COMPLETIONS_TIMEOUT_SECONDS", "90"))
    )
    chat_completions_stream_idle_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("CHAT_COMPLETIONS_STREAM_IDLE_TIMEOUT_SECONDS", "30"))
    )
    chat_completions_stream_total_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("CHAT_COMPLETIONS_STREAM_TOTAL_TIMEOUT_SECONDS", "300"))
    )

    def require_fernet_key(self) -> str:
        if not self.fernet_key:
            raise ValueError("CREDENTIALS_FERNET_KEY is required for encrypted credential storage.")
        return self.fernet_key
