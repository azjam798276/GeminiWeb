from __future__ import annotations

import asyncio
import re
import secrets as secrets_module
import uuid
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SecurityHeadersConfig:
    enable_cache_control_no_store: bool = True


def _norm(s: str) -> str:
    return s.strip()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [piece for piece in (_norm(v) for v in value.split(",")) if piece]


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def coerce_request_id(value: str | None) -> str:
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex


def parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip(), parts[1].strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def constant_time_equals(a: str, b: str) -> bool:
    return secrets_module.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _is_protected_path(path: str) -> bool:
    return path.startswith("/v1/")


def _should_set_no_store(path: str) -> bool:
    return path.startswith("/v1/")


def install_middlewares(app, *, cfg) -> None:
    """
    Install security middleware and optional hardening based on cfg.

    Kept as a helper to keep `server.py` lean and tests isolated.
    """
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    from .openai_compat import make_openai_error_response

    class RequestIdMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            request_id = coerce_request_id(request.headers.get("x-request-id"))
            request.state.request_id = request_id
            try:
                import structlog

                structlog.contextvars.bind_contextvars(request_id=request_id)
            except Exception:  # pragma: no cover
                pass
            response = None
            try:
                response = await call_next(request)
            finally:
                try:
                    import structlog

                    structlog.contextvars.clear_contextvars()
                except Exception:  # pragma: no cover
                    pass
            if response is not None:
                response.headers.setdefault("X-Request-Id", request_id)
            return response

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
            response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
            if getattr(cfg, "enable_api_docs", True) is False:
                response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
            if _should_set_no_store(request.url.path):
                response.headers.setdefault("Cache-Control", "no-store")
                response.headers.setdefault("Pragma", "no-cache")
            return response

    class MaxBodySizeMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            limit = int(getattr(cfg, "max_request_body_bytes", 0) or 0)
            if limit > 0 and request.method in ("POST", "PUT", "PATCH") and _is_protected_path(
                request.url.path
            ):
                content_length = request.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > limit:
                    return JSONResponse(
                        status_code=413,
                        content=make_openai_error_response(
                            message="Request body too large.",
                            type="invalid_request_error",
                            code=getattr(request.state, "request_id", None),
                        ).model_dump(),
                    )
                body = await request.body()
                if len(body) > limit:
                    return JSONResponse(
                        status_code=413,
                        content=make_openai_error_response(
                            message="Request body too large.",
                            type="invalid_request_error",
                            code=getattr(request.state, "request_id", None),
                        ).model_dump(),
                    )
            return await call_next(request)

    class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
        def __init__(self, app_):
            super().__init__(app_)
            self._sem = asyncio.Semaphore(max(1, int(getattr(cfg, "max_inflight_requests", 1) or 1)))

        async def dispatch(self, request: Request, call_next):
            if not _is_protected_path(request.url.path):
                return await call_next(request)
            if self._sem.locked():
                return JSONResponse(
                    status_code=429,
                    content=make_openai_error_response(
                        message="Server is busy. Try again later.",
                        type="rate_limit_error",
                        code=getattr(request.state, "request_id", None),
                    ).model_dump(),
                )
            await self._sem.acquire()
            try:
                return await call_next(request)
            finally:
                self._sem.release()

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            expected = getattr(cfg, "server_auth_token", None)
            if not expected or not _is_protected_path(request.url.path) or request.method == "OPTIONS":
                return await call_next(request)

            token = parse_bearer_token(request.headers.get("authorization")) or request.headers.get(
                "x-api-key"
            )
            if not token or not constant_time_equals(token, expected):
                return JSONResponse(
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="geminiweb-safe-provider"'},
                    content=make_openai_error_response(
                        message="Missing or invalid authentication token.",
                        type="authentication_error",
                        code=getattr(request.state, "request_id", None),
                    ).model_dump(),
                )
            return await call_next(request)

    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(ConcurrencyLimitMiddleware)
    app.add_middleware(BearerAuthMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    # Must be outermost to ensure `X-Request-Id` is set even when inner middleware short-circuits.
    app.add_middleware(RequestIdMiddleware)

    allowed_hosts: list[str] = list(getattr(cfg, "allowed_hosts", []) or [])
    if allowed_hosts:
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    cors_allow_origins: list[str] = list(getattr(cfg, "cors_allow_origins", []) or [])
    if cors_allow_origins:
        from fastapi.middleware.cors import CORSMiddleware

        allow_credentials = bool(getattr(cfg, "cors_allow_credentials", False))
        if allow_credentials and "*" in cors_allow_origins:
            raise ValueError("CORS_ALLOW_ORIGINS cannot include '*' when CORS_ALLOW_CREDENTIALS=true.")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allow_origins,
            allow_credentials=allow_credentials,
            allow_methods=["POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-Id", "X-API-Key"],
            max_age=600,
        )
