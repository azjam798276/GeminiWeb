from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from .config import GeminiProviderConfig
from .errors import ConfigurationError, UnsupportedFeatureError
from .gemini_official_session import GeminiOfficialSession
from .metrics import request_latency_seconds, requests_total
from .router_contracts import CompletionIntent, CompletionResult

log = structlog.get_logger()


class GeminiProvider:
    name = "GeminiOfficial"
    supports_stream = False

    def __init__(self, cfg: GeminiProviderConfig, *, session: GeminiOfficialSession | None = None):
        self.cfg = cfg
        self.session = session or GeminiOfficialSession(
            api_key=cfg.google_api_key,
            timeout_seconds=cfg.upstream_timeout_seconds,
            max_attempts=cfg.upstream_max_attempts,
            backoff_initial_seconds=cfg.upstream_backoff_initial_seconds,
            backoff_max_seconds=cfg.upstream_backoff_max_seconds,
            circuit_breaker_failures=cfg.upstream_circuit_breaker_failures,
            circuit_breaker_reset_seconds=cfg.upstream_circuit_breaker_reset_seconds,
        )

    async def create_async(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        intent = CompletionIntent(logical_model=model, messages=messages, min_tier="any", extra=kwargs)
        res = await self.complete(intent)
        return res.content

    def _split_messages(self, messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
        system_parts: list[str] = []
        contents: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if not isinstance(content, str):
                raise ConfigurationError("Message content must be a string in this scaffold.")
            if role == "system":
                if content:
                    system_parts.append(content)
                continue
            if role == "tool":
                raise ConfigurationError("tool messages are not supported in this scaffold.")
            if role not in ("user", "assistant"):
                raise ConfigurationError(f"Unsupported message role: {role!r}")
            contents.append({"role": role, "content": content})

        system_instruction = "\n\n".join(system_parts).strip() or None
        return system_instruction, contents

    async def complete(self, intent: CompletionIntent) -> CompletionResult:
        start = time.time()
        provider = self.name
        try:
            system_instruction, chat_messages = self._split_messages(intent.messages)
            if not any(m["role"] == "user" and m["content"] for m in chat_messages):
                raise ConfigurationError("No user message provided.")

            with request_latency_seconds.labels(provider=provider).time():
                extra = intent.extra or {}
                text = await self.session.generate_chat(
                    model=intent.logical_model,
                    messages=chat_messages,
                    system_instruction=system_instruction,
                    temperature=extra.get("temperature"),
                    top_p=extra.get("top_p"),
                    max_tokens=extra.get("max_tokens"),
                    stop=extra.get("stop"),
                    presence_penalty=extra.get("presence_penalty"),
                    frequency_penalty=extra.get("frequency_penalty"),
                )

            latency = time.time() - start
            requests_total.labels(provider=provider, status="success").inc()
            return CompletionResult(
                provider_name=provider,
                actual_model=intent.logical_model,
                tier="standard",
                content=text,
                latency_seconds=latency,
            )
        except Exception as e:
            requests_total.labels(provider=provider, status="error").inc()
            log.exception("provider_error", provider=provider, error=str(e))
            raise

    async def stream(self, intent: CompletionIntent) -> AsyncIterator[str]:
        if not self.cfg.enable_streaming:
            raise UnsupportedFeatureError("Streaming is disabled (set ENABLE_STREAMING=true).")
        system_instruction, chat_messages = self._split_messages(intent.messages)
        if not any(m["role"] == "user" and m["content"] for m in chat_messages):
            raise ConfigurationError("No user message provided.")
        extra = intent.extra or {}
        async for piece in self.session.stream_chat(
            model=intent.logical_model,
            messages=chat_messages,
            system_instruction=system_instruction,
            temperature=extra.get("temperature"),
            top_p=extra.get("top_p"),
            max_tokens=extra.get("max_tokens"),
            stop=extra.get("stop"),
            presence_penalty=extra.get("presence_penalty"),
            frequency_penalty=extra.get("frequency_penalty"),
        ):
            yield piece
