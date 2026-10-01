from __future__ import annotations

import re
from pathlib import Path

import pytest

from runtime_config import _DEFAULT_LLM_API_KEY, RuntimeConfig

_ENV_VARS = (
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_REQUEST_TIMEOUT_SECONDS",
    "OCR_BASE_URL",
    "OCR_DOCUMENTS_BASE_URL",
    "OCR_AUTH_HEADER",
    "OCR_REQUEST_TIMEOUT_SECONDS",
    "MEMORY_BASE_URL",
    "MEMORY_REQUEST_TIMEOUT_SECONDS",
)


def test_defaults_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    cfg = RuntimeConfig.from_env()

    assert cfg.llm_base_url == "http://localhost:9000/v1"
    assert cfg.llm_api_key == "local-llm"
    assert cfg.llm_model == "Qwen3.8-27B-UD-Q4_K_XL"
    assert cfg.llm_request_timeout_seconds == 300.0
    assert cfg.ocr_base_url == "http://localhost:8002"
    assert cfg.ocr_documents_base_url == "http://localhost:8008"
    assert cfg.ocr_auth_header is None
    assert cfg.ocr_request_timeout_seconds == 3600.0
    assert cfg.memory_base_url == "http://localhost:8005"
    assert cfg.memory_request_timeout_seconds == 600.0


def test_llm_request_timeout_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "45")
    assert RuntimeConfig.from_env().llm_request_timeout_seconds == 45.0


@pytest.mark.parametrize(
    "var,value",
    [
        ("LLM_API_KEY", ""),
        ("LLM_MODEL", "  "),
        ("OCR_AUTH_HEADER", ""),
        ("OCR_DOCUMENTS_BASE_URL", ""),
    ],
)
def test_set_but_empty_string_field_raises(
    monkeypatch: pytest.MonkeyPatch, var: str, value: str
) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValueError, match=f"{var} is set but empty"):
        RuntimeConfig.from_env()


def test_makefile_llm_api_key_default_matches_runtime_config_default() -> None:
    """One mechanical check tying `make papers-ingest`'s exported key to the value
    RuntimeConfig defaults to when the operator doesn't override it (CLAUDE.md §6)."""
    makefile_path = Path(__file__).resolve().parents[3] / "Makefile"
    text = makefile_path.read_text(encoding="utf-8")
    match = re.search(r"^LLM_API_KEY \?= (.+)$", text, flags=re.MULTILINE)
    assert match is not None, f"no 'LLM_API_KEY ?= ...' line found in {makefile_path}"
    assert match.group(1) == _DEFAULT_LLM_API_KEY


def test_reads_env_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://gateway:9000/v1")
    monkeypatch.setenv("OCR_AUTH_HEADER", "Bearer secret")
    monkeypatch.setenv("OCR_REQUEST_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OCR_DOCUMENTS_BASE_URL", "http://ocr-documents:8008")

    cfg = RuntimeConfig.from_env()

    assert cfg.llm_base_url == "http://gateway:9000/v1"
    assert cfg.ocr_auth_header == "Bearer secret"
    assert cfg.ocr_documents_base_url == "http://ocr-documents:8008"
    assert cfg.ocr_request_timeout_seconds == 45.0

    monkeypatch.setenv("LLM_BASE_URL", "http://other:9000/v1")
    assert RuntimeConfig.from_env().llm_base_url == "http://other:9000/v1"


def test_non_numeric_timeout_raises_naming_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_REQUEST_TIMEOUT_SECONDS", "not-a-number")
    with pytest.raises(ValueError, match="OCR_REQUEST_TIMEOUT_SECONDS"):
        RuntimeConfig.from_env()
