import pytest
from pydantic import ValidationError

from geminiweb_provider.openai_compat import ChatCompletionMessage, ChatCompletionRequest, extract_generation_params


def test_openai_request_model_roundtrip():
    req = ChatCompletionRequest(
        model="gemini-1.5-pro",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        stream=False,
    )
    dumped = req.model_dump()
    assert dumped["model"] == "gemini-1.5-pro"
    assert dumped["messages"][0]["role"] == "user"


def test_openai_request_validates_temperature_range():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatCompletionMessage(role="user", content="hi")], temperature=3.0)


def test_openai_request_validates_top_p_range():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatCompletionMessage(role="user", content="hi")], top_p=0.0)


def test_openai_request_validates_max_tokens_positive():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            max_tokens=0,
        )


def test_openai_request_validates_stop_sequences():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            stop=["", "ok"],
        )


def test_openai_request_validates_presence_penalty_range():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            presence_penalty=3.0,
        )


def test_openai_request_validates_frequency_penalty_range():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            frequency_penalty=-3.0,
        )


def test_openai_request_validates_max_completion_tokens_positive():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            max_completion_tokens=0,
        )


def test_openai_request_rejects_conflicting_max_tokens_fields():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            max_tokens=10,
            max_completion_tokens=11,
        )


def test_extract_generation_params_uses_max_completion_tokens_alias():
    req = ChatCompletionRequest(
        model="m",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        max_completion_tokens=99,
    )
    assert extract_generation_params(req)["max_tokens"] == 99
