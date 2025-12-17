import pytest

from geminiweb_provider import GeminiProvider, GeminiProviderConfig


@pytest.mark.asyncio
async def test_provider_scaffold_uses_official_session_interface():
    class FakeSession:
        async def generate_chat(self, **kwargs):
            return "ok"

        async def close(self):
            return None

    cfg = GeminiProviderConfig(google_api_key="dummy", fernet_key="dummy")
    p = GeminiProvider(cfg, session=FakeSession())
    out = await p.create_async("gemini-1.5-pro", [{"role": "user", "content": "hi"}])
    assert out == "ok"
