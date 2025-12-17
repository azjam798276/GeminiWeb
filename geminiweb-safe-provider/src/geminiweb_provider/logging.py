from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any, TypeAlias, cast

import structlog


_SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "fernet_key",
    "credentials",
}


_BEARER_RE = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._-]{6,})")

ProcessorReturn: TypeAlias = Mapping[str, Any] | str | bytes | bytearray | tuple[Any, ...]
Processor: TypeAlias = Callable[[Any, str, MutableMapping[str, Any]], ProcessorReturn]


def _redact_str(value: str, *, secrets: list[str]) -> str:
    out = value
    for secret in secrets:
        if secret and secret in out:
            out = out.replace(secret, "[REDACTED]")
    out = _BEARER_RE.sub("Bearer [REDACTED]", out)
    return out


def _redact_obj(obj: Any, *, secrets: list[str]) -> Any:
    if obj is None:
        return None
    if isinstance(obj, str):
        return _redact_str(obj, secrets=secrets)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_redact_obj(v, secrets=secrets) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_obj(v, secrets=secrets) for v in obj)
    if isinstance(obj, dict):
        redacted: dict[Any, Any] = {}
        for k, v in obj.items():
            key_str = str(k).lower()
            if key_str in _SENSITIVE_KEYS or any(s in key_str for s in ("key", "token", "secret", "password")):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_obj(v, secrets=secrets)
        return redacted
    return obj


def _make_redaction_processor(*, secrets: list[str]) -> Processor:
    secrets_norm = [s for s in secrets if isinstance(s, str) and s]

    def _processor(_logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]) -> ProcessorReturn:
        return cast(dict[str, Any], _redact_obj(event_dict, secrets=secrets_norm))

    return _processor


def configure_logging(level: str = "INFO", fmt: str = "json", *, secrets: list[str] | None = None) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))

    processors: list[Processor] = [
        cast(Processor, structlog.contextvars.merge_contextvars),
        cast(Processor, structlog.processors.add_log_level),
        cast(Processor, structlog.processors.TimeStamper(fmt="iso")),
    ]

    if secrets:
        processors.append(_make_redaction_processor(secrets=secrets))

    if fmt == "json":
        processors.append(cast(Processor, structlog.processors.JSONRenderer()))
    else:
        processors.append(cast(Processor, structlog.dev.ConsoleRenderer()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
