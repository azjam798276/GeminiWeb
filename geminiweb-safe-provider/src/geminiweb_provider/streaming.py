from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator


def sse_encode(data: str) -> bytes:
    return f"data: {data}\n\n".encode("utf-8")


def openai_chunk(
    *,
    chunk_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return chunk


async def openai_sse_from_text_stream(
    *,
    model: str,
    text_stream: AsyncIterator[str],
) -> AsyncIterator[bytes]:
    chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    yield sse_encode(json.dumps(openai_chunk(chunk_id=chunk_id, created=created, model=model, delta={"role": "assistant"})))
    async for piece in text_stream:
        if not piece:
            continue
        yield sse_encode(
            json.dumps(openai_chunk(chunk_id=chunk_id, created=created, model=model, delta={"content": piece}))
        )
    yield sse_encode(json.dumps(openai_chunk(chunk_id=chunk_id, created=created, model=model, delta={}, finish_reason="stop")))
    yield sse_encode("[DONE]")
