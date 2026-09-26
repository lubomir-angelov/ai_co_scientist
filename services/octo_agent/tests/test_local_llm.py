from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from engine import local_llm as local_llm_module
from engine.factory import create_llm_engine
from engine.local_llm import ChatLocalLLM
from service_errors import LLMEngineError


class Answer(BaseModel):
    value: str


def _httpx_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    resp.text = json.dumps(body)

    def _raise_for_status() -> None:
        if status >= 400:
            request = httpx.Request("POST", "http://gateway/chat/completions")
            raise httpx.HTTPStatusError(f"HTTP {status}", request=request, response=resp)

    resp.raise_for_status.side_effect = _raise_for_status
    return resp


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(
        return_value=_httpx_response(200, {"choices": [{"message": {"content": "hi"}}]})
    )
    monkeypatch.setattr(local_llm_module.httpx, "post", mock)
    return mock


def _engine(timeout_s: float = 45.0) -> ChatLocalLLM:
    return ChatLocalLLM(
        model_string="test-model",
        base_url="http://gateway:9000/v1",
        api_key="k",
        is_multimodal=False,
        timeout_s=timeout_s,
    )


def test_response_format_sends_json_schema_and_returns_model_instance(post: MagicMock) -> None:
    post.return_value = _httpx_response(
        200, {"choices": [{"message": {"content": json.dumps({"value": "ok"})}}]}
    )
    result = _engine().generate("prompt", response_format=Answer)

    assert result == Answer(value="ok")
    schema_block = post.call_args.kwargs["json"]["response_format"]
    assert schema_block["type"] == "json_schema"
    assert schema_block["json_schema"]["name"] == "Answer"
    assert schema_block["json_schema"]["strict"] is True


def test_invalid_json_content_raises_validation_error(post: MagicMock) -> None:
    post.return_value = _httpx_response(200, {"choices": [{"message": {"content": "not json"}}]})
    with pytest.raises(ValidationError):
        _engine().generate("prompt", response_format=Answer)


def test_empty_content_raises_llm_engine_error(post: MagicMock) -> None:
    post.return_value = _httpx_response(200, {"choices": [{"message": {"content": ""}}]})
    with pytest.raises(LLMEngineError, match="no content"):
        _engine().generate("prompt")


def test_http_503_raises_with_status_code(post: MagicMock) -> None:
    post.return_value = _httpx_response(503, {"error": "overloaded"})
    with pytest.raises(LLMEngineError) as excinfo:
        _engine().generate("prompt")
    assert excinfo.value.status_code == 503


def test_transport_error_raises_with_no_status_code(post: MagicMock) -> None:
    post.side_effect = httpx.ConnectError("refused")
    with pytest.raises(LLMEngineError) as excinfo:
        _engine().generate("prompt")
    assert excinfo.value.status_code is None


def test_without_response_format_returns_str(post: MagicMock) -> None:
    result = _engine().generate("prompt")
    assert result == "hi"


def test_timeout_s_reaches_httpx_post(post: MagicMock) -> None:
    _engine(timeout_s=45.0).generate("prompt")
    assert post.call_args.kwargs["timeout"] == 45.0


def test_create_llm_engine_uses_runtime_config_with_no_alias_coercion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "Qwen3.8-27B-UD-Q4_K_XL")
    monkeypatch.setenv("LLM_BASE_URL", "http://gateway:9000/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "45")

    engine = create_llm_engine(is_multimodal=True)

    assert engine.model_string == "Qwen3.8-27B-UD-Q4_K_XL"
    assert engine.base_url == "http://gateway:9000/v1"
    assert engine.api_key == "secret"
    assert engine.timeout_s == 45.0
