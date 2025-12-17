import pytest

from geminiweb_provider import GeminiProvider, GeminiProviderConfig
from geminiweb_provider.errors import ConfigurationError


@pytest.mark.asyncio
async def test_provider_maps_system_and_chat_to_generate_chat():
    observed = {}

    class FakeSession:
        async def generate_chat(self, **kwargs):
            observed.update(kwargs)
            return "ok"

        async def close(self):
            return None

    cfg = GeminiProviderConfig(google_api_key="dummy", fernet_key="dummy")
    p = GeminiProvider(cfg, session=FakeSession())
    out = await p.create_async(
        "gemini-1.5-pro",
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "How are you?"},
        ],
        temperature=0.2,
        top_p=0.9,
        max_tokens=10,
        stop=["\n\n"],
        presence_penalty=1.0,
        frequency_penalty=-0.25,
    )

    assert out == "ok"
    assert observed["model"] == "gemini-1.5-pro"
    assert observed["system_instruction"] == "You are helpful."
    assert observed["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]
    assert observed["temperature"] == 0.2
    assert observed["top_p"] == 0.9
    assert observed["max_tokens"] == 10
    assert observed["stop"] == ["\n\n"]
    assert observed["presence_penalty"] == 1.0
    assert observed["frequency_penalty"] == -0.25


@pytest.mark.asyncio
async def test_provider_rejects_tool_messages():
    class FakeSession:
        async def generate_chat(self, **kwargs):
            return "ok"

        async def close(self):
            return None

    cfg = GeminiProviderConfig(google_api_key="dummy", fernet_key="dummy")
    p = GeminiProvider(cfg, session=FakeSession())
    with pytest.raises(ConfigurationError):
        await p.create_async("gemini-1.5-pro", [{"role": "tool", "content": "x"}])
