from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from .config import GeminiProviderConfig
from .errors import (
    AuthenticationError,
    CircuitBreakerOpenError,
    ConfigurationError,
    ProviderError,
    RateLimitError,
    RequestTimeoutError,
    UpstreamProtocolError,
    UnsupportedFeatureError,
)
from .logging import configure_logging
from .metrics import maybe_start_metrics, server_errors_total, server_request_latency_seconds, server_requests_total
from .openai_compat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    extract_generation_params,
    make_chat_completion_response,
    make_openai_error_response,
    messages_to_provider_messages,
)
from .provider import GeminiProvider
from .router_contracts import CompletionIntent
from .streaming import openai_sse_from_text_stream
from .http_security import install_middlewares


def create_app(cfg: GeminiProviderConfig | None = None, provider: GeminiProvider | None = None):
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('Install the "server" extra: pip install -e ".[server]"') from e

    cfg = cfg or GeminiProviderConfig()
    configure_logging(
        level=cfg.log_level,
        fmt=cfg.log_format,
        secrets=[s for s in (cfg.google_api_key, cfg.fernet_key, cfg.server_auth_token) if s],
    )
    provider = provider or GeminiProvider(cfg)

    def _request_id(request) -> str | None:
        return getattr(getattr(request, "state", None), "request_id", None)

    def _observe(path: str, status_code: int, started_at: float) -> None:
        server_requests_total.labels(path=path, status=str(status_code)).inc()
        server_request_latency_seconds.labels(path=path).observe(max(0.0, time.monotonic() - started_at))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        maybe_start_metrics(enable=cfg.enable_metrics, bind=cfg.metrics_bind, port=cfg.metrics_port)
        try:
            yield
        finally:
            await provider.session.close()

    app = FastAPI(
        title="geminiweb-safe-provider",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if cfg.enable_api_docs else None,
        redoc_url="/redoc" if cfg.enable_api_docs else None,
        openapi_url="/openapi.json" if cfg.enable_api_docs else None,
    )
    install_middlewares(app, cfg=cfg)

    @app.exception_handler(AuthenticationError)
    async def _auth_error_handler(_request, exc: AuthenticationError):
        server_errors_total.labels(type="authentication_error").inc()
        return JSONResponse(
            status_code=401,
            content=make_openai_error_response(
                message=str(exc),
                type="authentication_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.exception_handler(RateLimitError)
    async def _rate_limit_error_handler(_request, exc: RateLimitError):
        server_errors_total.labels(type="rate_limit_error").inc()
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=429,
            content=make_openai_error_response(
                message=str(exc),
                type="rate_limit_error",
                code=_request_id(_request),
            ).model_dump(),
            headers=headers,
        )

    @app.exception_handler(CircuitBreakerOpenError)
    async def _circuit_open_handler(_request, exc: CircuitBreakerOpenError):
        server_errors_total.labels(type="circuit_breaker_open").inc()
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=503,
            content=make_openai_error_response(
                message=str(exc),
                type="upstream_error",
                code=_request_id(_request),
            ).model_dump(),
            headers=headers,
        )

    @app.exception_handler(ConfigurationError)
    async def _config_error_handler(_request, exc: ConfigurationError):
        server_errors_total.labels(type="invalid_request_error").inc()
        return JSONResponse(
            status_code=400,
            content=make_openai_error_response(
                message=str(exc),
                type="invalid_request_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.exception_handler(UpstreamProtocolError)
    async def _upstream_error_handler(_request, exc: UpstreamProtocolError):
        server_errors_total.labels(type="upstream_error").inc()
        return JSONResponse(
            status_code=502,
            content=make_openai_error_response(
                message=str(exc),
                type="upstream_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.exception_handler(RequestTimeoutError)
    async def _timeout_error_handler(_request, exc: RequestTimeoutError):
        server_errors_total.labels(type="timeout").inc()
        return JSONResponse(
            status_code=504,
            content=make_openai_error_response(
                message=str(exc) or "Request timed out.",
                type="upstream_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.exception_handler(UnsupportedFeatureError)
    async def _unsupported_feature_handler(_request, exc: UnsupportedFeatureError):
        server_errors_total.labels(type="invalid_request_error").inc()
        return JSONResponse(
            status_code=400,
            content=make_openai_error_response(
                message=str(exc),
                type="invalid_request_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.exception_handler(ProviderError)
    async def _provider_error_handler(_request, exc: ProviderError):
        server_errors_total.labels(type="api_error").inc()
        return JSONResponse(
            status_code=500,
            content=make_openai_error_response(
                message=str(exc),
                type="api_error",
                code=_request_id(_request),
            ).model_dump(),
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(req: ChatCompletionRequest):
        started_at = time.monotonic()
        if len(req.messages) > cfg.max_messages:
            raise ConfigurationError("Too many messages.")
        total_chars = sum(len(m.content) for m in req.messages)
        if total_chars > cfg.max_total_message_chars:
            raise ConfigurationError("Message content too large.")

        if req.stream:
            if not cfg.enable_streaming:
                raise UnsupportedFeatureError("Streaming is disabled (set ENABLE_STREAMING=true).")
            try:
                from fastapi.responses import StreamingResponse
            except ImportError as e:  # pragma: no cover
                raise RuntimeError('Install the "server" extra: pip install -e ".[server]"') from e

            intent = CompletionIntent(
                logical_model=req.model,
                messages=messages_to_provider_messages(req.messages),
                extra=extract_generation_params(req),
            )
            text_stream = provider.stream(intent)

            async def _deadline_stream():
                it = text_stream.__aiter__()
                try:
                    loop = asyncio.get_running_loop()
                    total_deadline = max(0.0, float(cfg.chat_completions_stream_total_timeout_seconds or 0))
                    idle_timeout = max(0.0, float(cfg.chat_completions_stream_idle_timeout_seconds or 0))
                    started = loop.time()

                    while True:
                        remaining_total: float | None = None
                        if total_deadline > 0:
                            remaining_total = total_deadline - (loop.time() - started)
                            if remaining_total <= 0:
                                raise RequestTimeoutError("Streaming request timed out.")

                        timeout: float | None = None
                        if idle_timeout > 0:
                            timeout = idle_timeout
                        if remaining_total is not None:
                            timeout = remaining_total if timeout is None else min(timeout, remaining_total)

                        try:
                            piece = await asyncio.wait_for(anext(it), timeout=timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError as e:
                            raise RequestTimeoutError("Streaming request timed out.") from e
                        yield piece
                finally:
                    aclose = getattr(it, "aclose", None)
                    if callable(aclose):
                        await aclose()

            byte_stream = openai_sse_from_text_stream(model=req.model, text_stream=_deadline_stream())
            resp = StreamingResponse(byte_stream, media_type="text/event-stream")
            _observe("/v1/chat/completions", 200, started_at)
            return resp

        try:
            content = await asyncio.wait_for(
                provider.create_async(
                    req.model,
                    messages_to_provider_messages(req.messages),
                    **extract_generation_params(req),
                ),
                timeout=max(0.0, float(cfg.chat_completions_timeout_seconds or 0)) or None,
            )
        except asyncio.TimeoutError as e:
            raise RequestTimeoutError("Request timed out.") from e

        _observe("/v1/chat/completions", 200, started_at)
        return make_chat_completion_response(model=req.model, content=content)

    return app


app = create_app()


def main() -> None:  # pragma: no cover
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError('Install the "server" extra: pip install -e ".[server]"') from e

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("geminiweb_provider.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
