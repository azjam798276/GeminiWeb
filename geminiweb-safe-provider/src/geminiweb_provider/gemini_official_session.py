from __future__ import annotations

import asyncio
import random
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import structlog

from .errors import AuthenticationError, CircuitBreakerOpenError, RateLimitError, UpstreamProtocolError
from .metrics import upstream_circuit_breaker_events_total

log = structlog.get_logger()

GEMINI_DEV_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiOfficialSession:
    """
    Stub session wrapper designed for OFFICIAL APIs.

    You can implement either:
      - Gemini Developer API (api key)
      - Vertex AI Gemini (project/location + auth)
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = GEMINI_DEV_API_BASE,
        timeout_seconds: float = 60,
        max_attempts: int = 3,
        backoff_initial_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
        circuit_breaker_failures: int = 5,
        circuit_breaker_reset_seconds: float = 30.0,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff_initial_seconds = max(0.0, backoff_initial_seconds)
        self._backoff_max_seconds = max(self._backoff_initial_seconds, backoff_max_seconds)
        self._sleep: Callable[[float], Awaitable[None]] = sleeper or asyncio.sleep
        self._clock: Callable[[], float] = clock or time.monotonic

        self._cb_threshold = max(0, int(circuit_breaker_failures))
        self._cb_reset_seconds = max(0.0, float(circuit_breaker_reset_seconds))
        self._cb_failures = 0
        self._cb_open_until: float | None = None

    async def close(self) -> None:
        await self._client.aclose()

    def _circuit_remaining_seconds(self) -> int | None:
        if self._cb_open_until is None:
            return None
        remaining = self._cb_open_until - self._clock()
        if remaining <= 0:
            return None
        return int(remaining) + 1

    def _circuit_allow(self) -> None:
        if self._cb_threshold <= 0:
            return
        remaining = self._circuit_remaining_seconds()
        if remaining is None:
            return
        upstream_circuit_breaker_events_total.labels(event="short_circuit").inc()
        raise CircuitBreakerOpenError(retry_after_seconds=remaining)

    def _circuit_on_success(self) -> None:
        if self._cb_threshold <= 0:
            return
        self._cb_failures = 0
        self._cb_open_until = None

    def _circuit_on_failure(self) -> None:
        if self._cb_threshold <= 0:
            return
        self._cb_failures += 1
        if self._cb_failures < self._cb_threshold:
            return
        if self._cb_reset_seconds <= 0:
            return
        self._cb_open_until = self._clock() + self._cb_reset_seconds
        upstream_circuit_breaker_events_total.labels(event="open").inc()

    def _compute_backoff(self, attempt_index: int) -> float:
        # attempt_index: 0-based retry count (0 for first retry)
        base = float(min(self._backoff_max_seconds, self._backoff_initial_seconds * (2**attempt_index)))
        # Add small jitter to avoid synchronized retries
        jitter = float(random.uniform(0.0, min(0.25, base * 0.1))) if base > 0 else 0.0
        return base + jitter

    async def generate_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        system_instruction: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        stop: str | list[str] | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        **kwargs: Any,
    ) -> str:
        if kwargs:
            log.debug("gemini_generate_chat_ignored_kwargs", keys=list(kwargs.keys()))

        self._circuit_allow()

        if not self.api_key:
            raise AuthenticationError("Missing GOOGLE_API_KEY for official Gemini API call.")

        url = f"{self._base_url}/models/{model}:generateContent"
        params = {"key": self.api_key}

        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            text = msg.get("content", "")
            if role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                raise UpstreamProtocolError(f"Unsupported message role for upstream: {role!r}")
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        payload: dict[str, Any] = {"contents": contents}

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["topP"] = top_p
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if stop is not None:
            stop_sequences = [stop] if isinstance(stop, str) else stop
            generation_config["stopSequences"] = stop_sequences
        if presence_penalty is not None:
            generation_config["presencePenalty"] = presence_penalty
        if frequency_penalty is not None:
            generation_config["frequencyPenalty"] = frequency_penalty
        if generation_config:
            payload["generationConfig"] = generation_config

        last_rate_limit: RateLimitError | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._client.post(url, params=params, json=payload)
            except httpx.TimeoutException as e:
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    raise UpstreamProtocolError("Upstream request timed out.") from e
                await self._sleep(self._compute_backoff(attempt))
                continue
            except httpx.HTTPError as e:
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    raise UpstreamProtocolError("Upstream request failed.") from e
                await self._sleep(self._compute_backoff(attempt))
                continue

            if resp.status_code in (401, 403):
                raise AuthenticationError("Upstream rejected credentials (check GOOGLE_API_KEY).")

            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after")
                retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
                last_rate_limit = RateLimitError(retry_after_seconds=retry_seconds)
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    raise last_rate_limit
                sleep_for = retry_seconds if retry_seconds is not None else self._compute_backoff(attempt)
                await self._sleep(sleep_for)
                continue

            if 500 <= resp.status_code <= 599:
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    log.warning(
                        "gemini_upstream_5xx",
                        status_code=resp.status_code,
                        body=resp.text[:500],
                    )
                    raise UpstreamProtocolError(f"Upstream error {resp.status_code}.")
                await self._sleep(self._compute_backoff(attempt))
                continue

            if resp.status_code >= 400:
                raise UpstreamProtocolError(f"Upstream error {resp.status_code}.")

            data = resp.json()
            break
        else:  # pragma: no cover
            if last_rate_limit is not None:
                raise last_rate_limit
            raise UpstreamProtocolError("Upstream request failed after retries.")

        self._circuit_on_success()

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise UpstreamProtocolError("Missing candidates in upstream response.")

        content = candidates[0].get("content")
        if not isinstance(content, dict):
            raise UpstreamProtocolError("Missing content in upstream response.")

        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise UpstreamProtocolError("Missing parts in upstream response.")

        text = parts[0].get("text")
        if not isinstance(text, str):
            raise UpstreamProtocolError("Missing text in upstream response.")

        log.debug("gemini_generate_ok", model=model, prompt_chars=sum(len(m.get("content", "")) for m in messages))
        return text

    async def generate(self, model: str, prompt: str, **kwargs: Any) -> str:
        return await self.generate_chat(model=model, messages=[{"role": "user", "content": prompt}], **kwargs)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        system_instruction: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        stop: str | list[str] | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
    ) -> AsyncIterator[str]:
        self._circuit_allow()

        if not self.api_key:
            raise AuthenticationError("Missing GOOGLE_API_KEY for official Gemini API call.")

        url = f"{self._base_url}/models/{model}:streamGenerateContent"
        params = {"key": self.api_key}

        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            text = msg.get("content", "")
            if role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                raise UpstreamProtocolError(f"Unsupported message role for upstream: {role!r}")
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        payload: dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        generation_config: dict[str, Any] = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["topP"] = top_p
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        if stop is not None:
            stop_sequences = [stop] if isinstance(stop, str) else stop
            generation_config["stopSequences"] = stop_sequences
        if presence_penalty is not None:
            generation_config["presencePenalty"] = presence_penalty
        if frequency_penalty is not None:
            generation_config["frequencyPenalty"] = frequency_penalty
        if generation_config:
            payload["generationConfig"] = generation_config

        last_rate_limit: RateLimitError | None = None
        for attempt in range(self._max_attempts):
            try:
                async with self._client.stream("POST", url, params=params, json=payload) as resp:
                    if resp.status_code in (401, 403):
                        raise AuthenticationError("Upstream rejected credentials (check GOOGLE_API_KEY).")
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("retry-after")
                        retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
                        last_rate_limit = RateLimitError(retry_after_seconds=retry_seconds)
                        self._circuit_on_failure()
                        if attempt >= self._max_attempts - 1:
                            raise last_rate_limit
                        sleep_for = (
                            retry_seconds if retry_seconds is not None else self._compute_backoff(attempt)
                        )
                        await self._sleep(sleep_for)
                        continue
                    if 500 <= resp.status_code <= 599:
                        self._circuit_on_failure()
                        if attempt >= self._max_attempts - 1:
                            raise UpstreamProtocolError(f"Upstream error {resp.status_code}.")
                        await self._sleep(self._compute_backoff(attempt))
                        continue
                    if resp.status_code >= 400:
                        raise UpstreamProtocolError(f"Upstream error {resp.status_code}.")

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        raw = line[len("data:") :].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError as e:
                            raise UpstreamProtocolError("Failed to decode upstream SSE JSON.") from e

                        candidates = event.get("candidates")
                        if not isinstance(candidates, list) or not candidates:
                            continue
                        content = candidates[0].get("content")
                        if not isinstance(content, dict):
                            continue
                        parts = content.get("parts")
                        if not isinstance(parts, list) or not parts:
                            continue
                        text = parts[0].get("text")
                        if isinstance(text, str) and text:
                            yield text
                    self._circuit_on_success()
                    return
            except httpx.TimeoutException as e:
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    raise UpstreamProtocolError("Upstream request timed out.") from e
                await self._sleep(self._compute_backoff(attempt))
            except httpx.HTTPError as e:
                self._circuit_on_failure()
                if attempt >= self._max_attempts - 1:
                    raise UpstreamProtocolError("Upstream request failed.") from e
                await self._sleep(self._compute_backoff(attempt))

        if last_rate_limit is not None:  # pragma: no cover
            raise last_rate_limit
        raise UpstreamProtocolError("Upstream request failed after retries.")  # pragma: no cover
