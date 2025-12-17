import json

import httpx
import pytest

from geminiweb_provider.errors import (
    AuthenticationError,
    CircuitBreakerOpenError,
    RateLimitError,
    UpstreamProtocolError,
)
from geminiweb_provider.gemini_official_session import GeminiOfficialSession


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_generate_success_parses_text():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/models/gemini-1.5-pro:generateContent")
        assert request.url.params.get("key") == "k"

        body = json.loads(request.content.decode("utf-8"))
        assert body["contents"][0]["parts"][0]["text"] == "hi"

        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "hello from gemini"}]}},
                ]
            },
        )

    client = httpx.AsyncClient(transport=_mock_transport(handler))
    s = GeminiOfficialSession(api_key="k", client=client, base_url="https://example.test/v1beta")
    try:
        out = await s.generate("gemini-1.5-pro", "hi")
        assert out == "hello from gemini"
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_missing_key_raises_authentication_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    s = GeminiOfficialSession(api_key=None, client=httpx.AsyncClient(transport=_mock_transport(handler)))
    try:
        with pytest.raises(AuthenticationError):
            await s.generate("gemini-1.5-pro", "hi")
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_429_raises_rate_limit_error_with_retry_after():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "12"}, json={"error": {"message": "rl"}})

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=1,
        sleeper=no_sleep,
    )
    try:
        with pytest.raises(RateLimitError) as exc:
            await s.generate("gemini-1.5-pro", "hi")
        assert exc.value.retry_after_seconds == 12
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_401_raises_authentication_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    s = GeminiOfficialSession(api_key="k", client=httpx.AsyncClient(transport=_mock_transport(handler)))
    try:
        with pytest.raises(AuthenticationError):
            await s.generate("gemini-1.5-pro", "hi")
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_bad_shape_raises_upstream_protocol_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    s = GeminiOfficialSession(api_key="k", client=httpx.AsyncClient(transport=_mock_transport(handler)))
    try:
        with pytest.raises(UpstreamProtocolError):
            await s.generate("gemini-1.5-pro", "hi")
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": "rl"}})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=2,
        sleeper=no_sleep,
    )
    try:
        out = await s.generate("gemini-1.5-pro", "hi")
        assert out == "ok"
        assert calls["n"] == 2
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=2,
        sleeper=no_sleep,
    )
    try:
        out = await s.generate("gemini-1.5-pro", "hi")
        assert out == "ok"
        assert calls["n"] == 2
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_chat_maps_generation_config_and_system_instruction():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["systemInstruction"]["parts"][0]["text"] == "You are helpful."
        assert body["contents"][0]["role"] == "user"
        assert body["contents"][1]["role"] == "model"
        assert body["generationConfig"]["temperature"] == 0.2
        assert body["generationConfig"]["topP"] == 0.9
        assert body["generationConfig"]["maxOutputTokens"] == 123
        assert body["generationConfig"]["stopSequences"] == ["\n\n", "###"]
        assert body["generationConfig"]["presencePenalty"] == 1.25
        assert body["generationConfig"]["frequencyPenalty"] == -0.5
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=1,
        sleeper=no_sleep,
    )
    try:
        out = await s.generate_chat(
            model="gemini-1.5-pro",
            messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
            system_instruction="You are helpful.",
            temperature=0.2,
            top_p=0.9,
            max_tokens=123,
            stop=["\n\n", "###"],
            presence_penalty=1.25,
            frequency_penalty=-0.5,
        )
        assert out == "ok"
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_missing_text_raises_upstream_protocol_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{}]}}]})

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=1,
        sleeper=no_sleep,
    )
    try:
        with pytest.raises(UpstreamProtocolError):
            await s.generate("gemini-1.5-pro", "hi")
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_stream_chat_parses_upstream_sse_text_events():
    sse = "\n".join(
        [
            'data: {"candidates":[{"content":{"parts":[{"text":"he"}]}}]}',
            "",
            'data: {"candidates":[{"content":{"parts":[{"text":"llo"}]}}]}',
            "",
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=1,
        sleeper=lambda _: None,
    )
    try:
        out = []
        async for piece in s.stream_chat(model="gemini-1.5-pro", messages=[{"role": "user", "content": "hi"}]):
            out.append(piece)
        assert "".join(out) == "hello"
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_generate_opens_circuit_breaker_after_consecutive_failures():
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="overloaded")

    now = {"t": 100.0}

    def clock() -> float:
        return now["t"]

    async def no_sleep(_: float) -> None:
        return None

    s = GeminiOfficialSession(
        api_key="k",
        client=httpx.AsyncClient(transport=_mock_transport(handler)),
        max_attempts=1,
        sleeper=no_sleep,
        circuit_breaker_failures=2,
        circuit_breaker_reset_seconds=30,
        clock=clock,
    )
    try:
        with pytest.raises(UpstreamProtocolError):
            await s.generate("gemini-1.5-pro", "hi")
        with pytest.raises(UpstreamProtocolError):
            await s.generate("gemini-1.5-pro", "hi")
        with pytest.raises(CircuitBreakerOpenError) as exc:
            await s.generate("gemini-1.5-pro", "hi")
        assert exc.value.retry_after_seconds is not None
        assert calls["n"] == 2
    finally:
        await s.close()
