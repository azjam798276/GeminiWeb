import asyncio

import httpx
import pytest

from geminiweb_provider.config import GeminiProviderConfig
from geminiweb_provider.errors import CircuitBreakerOpenError


@pytest.mark.asyncio
async def test_server_error_responses_include_error_code_matching_request_id():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    cfg = GeminiProviderConfig(enable_metrics=False, server_auth_token="sekret")
    app = create_app(cfg=cfg)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"X-Request-Id": "req_12345678"},
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 401
    assert resp.headers.get("X-Request-Id") == "req_12345678"
    assert resp.json()["error"]["code"] == "req_12345678"


@pytest.mark.asyncio
async def test_server_request_timeout_maps_to_504_with_error_code():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    class SlowProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def create_async(self, model, messages, **kwargs):
            await asyncio.sleep(0.05)
            return "ok"

    cfg = GeminiProviderConfig(enable_metrics=False, chat_completions_timeout_seconds=0.01)
    app = create_app(cfg=cfg, provider=SlowProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"X-Request-Id": "req_timeout_01"},
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 504
    assert resp.headers.get("X-Request-Id") == "req_timeout_01"
    assert resp.json()["error"]["code"] == "req_timeout_01"


@pytest.mark.asyncio
async def test_server_circuit_breaker_open_maps_to_503_and_retry_after():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    class FakeProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def create_async(self, model, messages, **kwargs):
            raise CircuitBreakerOpenError(retry_after_seconds=3)

    cfg = GeminiProviderConfig(enable_metrics=False)
    app = create_app(cfg=cfg, provider=FakeProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"X-Request-Id": "req_cb_01"},
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "3"
    assert resp.json()["error"]["code"] == "req_cb_01"

