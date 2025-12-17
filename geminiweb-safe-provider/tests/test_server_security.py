import pytest
import httpx

from geminiweb_provider.config import GeminiProviderConfig


def _fake_provider(content: str = "ok"):
    class FakeProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def create_async(self, model, messages, **kwargs):
            return content

    return FakeProvider()


@pytest.mark.asyncio
async def test_server_requires_bearer_token_when_configured():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    cfg = GeminiProviderConfig(enable_metrics=False, server_auth_token="sekret")
    app = create_app(cfg=cfg, provider=_fake_provider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gemini-1.5-pro", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate", "").lower().startswith("bearer")

        resp_ok = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sekret"},
            json={"model": "gemini-1.5-pro", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp_ok.status_code == 200


@pytest.mark.asyncio
async def test_server_enforces_max_body_size_413():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    cfg = GeminiProviderConfig(enable_metrics=False, max_request_body_bytes=60)
    app = create_app(cfg=cfg, provider=_fake_provider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = b'{"model":"m","messages":[{"role":"user","content":"' + (b"x" * 200) + b'"}]}'
        resp = await client.post(
            "/v1/chat/completions",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_server_sets_security_headers_and_request_id():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    cfg = GeminiProviderConfig(enable_metrics=False)
    app = create_app(cfg=cfg, provider=_fake_provider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz", headers={"X-Request-Id": "req_12345678"})
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-Id") == "req_12345678"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"

        resp2 = await client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp2.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_server_cors_allowlist_applies():
    pytest.importorskip("fastapi")
    from geminiweb_provider.server import create_app

    cfg = GeminiProviderConfig(enable_metrics=False, cors_allow_origins=["https://example.com"])
    app = create_app(cfg=cfg, provider=_fake_provider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/v1/chat/completions",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code in (200, 204)
        assert resp.headers.get("access-control-allow-origin") == "https://example.com"

