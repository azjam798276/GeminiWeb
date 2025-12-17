import json

import pytest


@pytest.mark.asyncio
async def test_openai_sse_generator_emits_done_and_consistent_id():
    from geminiweb_provider.streaming import openai_sse_from_text_stream

    async def gen():
        yield "he"
        yield "llo"

    chunks = []
    async for b in openai_sse_from_text_stream(model="m", text_stream=gen()):
        chunks.append(b.decode("utf-8"))

    data_lines = [c for c in chunks if c.startswith("data: ") and "[DONE]" not in c]
    assert chunks[-1] == "data: [DONE]\n\n"

    payloads = [json.loads(line[len("data: ") :]) for line in data_lines]
    ids = {p["id"] for p in payloads}
    assert len(ids) == 1
    assert payloads[0]["choices"][0]["delta"] == {"role": "assistant"}


@pytest.mark.asyncio
async def test_server_streams_sse_when_enabled():
    pytest.importorskip("fastapi")
    import httpx

    from geminiweb_provider.config import GeminiProviderConfig
    from geminiweb_provider.server import create_app

    class FakeProvider:
        def __init__(self):
            async def _close() -> None:
                return None

            self.session = type("S", (), {"close": _close})()

        async def stream(self, _intent):
            yield "a"
            yield "b"

    app = create_app(cfg=GeminiProviderConfig(enable_metrics=False, enable_streaming=True), provider=FakeProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = ""
            async for line in resp.aiter_lines():
                body += line + "\n"

    assert "data: [DONE]" in body

