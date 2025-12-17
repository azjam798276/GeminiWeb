from __future__ import annotations


class ProviderError(Exception):
    """Base error for provider failures."""


class ConfigurationError(ProviderError):
    pass


class AuthenticationError(ProviderError):
    pass


class RateLimitError(ProviderError):
    def __init__(self, retry_after_seconds: int | None = None, message: str = "Rate limited"):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class UpstreamProtocolError(ProviderError):
    """Unexpected upstream response shape / contract mismatch."""


class CircuitBreakerOpenError(ProviderError):
    def __init__(self, retry_after_seconds: int | None = None, message: str = "Upstream temporarily unavailable"):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RequestTimeoutError(ProviderError):
    """Server-side request deadline exceeded."""


class UnsupportedFeatureError(ProviderError):
    """Requested feature not supported by current milestone/config."""
