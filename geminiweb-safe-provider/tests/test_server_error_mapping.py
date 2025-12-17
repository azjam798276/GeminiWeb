import pytest

import httpx

from geminiweb_provider.config import GeminiProviderConfig
from geminiweb_provider.errors import AuthenticationError, RateLimitError


@pytest.mark.asyncio
async def test_server_maps_authentication_error_to_401():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    class FakeProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def create_async(self, model, messages, **kwargs):
            raise AuthenticationError("bad key")

    app = create_app(cfg=GeminiProviderConfig(enable_metrics=False), provider=FakeProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gemini-1.5-pro", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "authentication_error"


@pytest.mark.asyncio
async def test_server_maps_rate_limit_error_to_429_and_retry_after():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    class FakeProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def create_async(self, model, messages, **kwargs):
            raise RateLimitError(retry_after_seconds=7)

    app = create_app(cfg=GeminiProviderConfig(enable_metrics=False), provider=FakeProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gemini-1.5-pro", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "7"
    assert resp.json()["error"]["type"] == "rate_limit_error"


@pytest.mark.asyncio
async def test_server_rejects_tool_messages_as_400_invalid_request():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    app = create_app(cfg=GeminiProviderConfig(enable_metrics=False))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gemini-1.5-pro", "messages": [{"role": "tool", "content": "x"}]},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request_error"
