from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionIntent:
    logical_model: str
    messages: list[dict[str, str]]
    min_tier: str = "any"
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompletionResult:
    provider_name: str
    actual_model: str
    tier: str
    content: str
    latency_seconds: float
    metadata: dict[str, Any] | None = None

