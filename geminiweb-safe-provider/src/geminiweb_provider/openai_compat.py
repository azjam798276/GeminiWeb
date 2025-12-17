from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class ChatCompletionMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatCompletionMessage]
    stream: bool = False

    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    user: str | None = None

    @model_validator(mode="after")
    def _validate_max_tokens_alias(self) -> "ChatCompletionRequest":
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            if self.max_tokens != self.max_completion_tokens:
                raise ValueError("Provide only one of max_tokens or max_completion_tokens.")
        return self

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not (0.0 <= v <= 2.0):
            raise ValueError("temperature must be between 0 and 2.")
        return v

    @field_validator("top_p")
    @classmethod
    def _validate_top_p(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not (0.0 < v <= 1.0):
            raise ValueError("top_p must be > 0 and <= 1.")
        return v

    @field_validator("max_tokens")
    @classmethod
    def _validate_max_tokens(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("max_tokens must be > 0.")
        return v

    @field_validator("max_completion_tokens")
    @classmethod
    def _validate_max_completion_tokens(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("max_completion_tokens must be > 0.")
        return v

    @field_validator("stop")
    @classmethod
    def _validate_stop(cls, v: str | list[str] | None) -> str | list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            if not v:
                raise ValueError("stop must be non-empty.")
            return v
        if not v:
            raise ValueError("stop list must be non-empty.")
        if any((not isinstance(s, str) or not s) for s in v):
            raise ValueError("stop sequences must be non-empty strings.")
        return v

    @field_validator("presence_penalty", "frequency_penalty")
    @classmethod
    def _validate_penalties(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not (-2.0 <= v <= 2.0):
            raise ValueError("penalty must be between -2 and 2.")
        return v

    def effective_max_tokens(self) -> int | None:
        return self.max_tokens if self.max_tokens is not None else self.max_completion_tokens


class ChatCompletionAssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionAssistantMessage
    finish_reason: Literal["stop"] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]


def make_chat_completion_response(*, model: str, content: str) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        model=model,
        choices=[ChatCompletionChoice(message=ChatCompletionAssistantMessage(content=content))],
    )


class OpenAIError(BaseModel):
    message: str
    type: str = "api_error"
    param: str | None = None
    code: str | None = None


class OpenAIErrorResponse(BaseModel):
    error: OpenAIError


def make_openai_error_response(
    *,
    message: str,
    type: str = "api_error",
    param: str | None = None,
    code: str | None = None,
) -> OpenAIErrorResponse:
    return OpenAIErrorResponse(error=OpenAIError(message=message, type=type, param=param, code=code))


def messages_to_provider_messages(messages: list[ChatCompletionMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def extract_generation_params(req: ChatCompletionRequest) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if req.temperature is not None:
        out["temperature"] = req.temperature
    if req.top_p is not None:
        out["top_p"] = req.top_p
    effective_max_tokens = req.effective_max_tokens()
    if effective_max_tokens is not None:
        out["max_tokens"] = effective_max_tokens
    if req.stop is not None:
        out["stop"] = req.stop
    if req.presence_penalty is not None:
        out["presence_penalty"] = req.presence_penalty
    if req.frequency_penalty is not None:
        out["frequency_penalty"] = req.frequency_penalty
    return out
