# services/octo_agent/src/runtime_config.py
"""The single source of environment configuration for octo_agent.

``RuntimeConfig.from_env()`` reads ``os.environ`` at call time (never at import time), so
tests can ``monkeypatch.setenv`` and get honest values. Every module that needs one of these
settings goes through here — no other module reads these environment variables directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_LLM_BASE_URL = "http://localhost:9000/v1"
_DEFAULT_LLM_API_KEY = "local-llm"
_DEFAULT_LLM_MODEL = "Qwen3.8-27B-UD-Q4_K_XL"
_DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 300.0
_DEFAULT_OCR_BASE_URL = "http://localhost:8002"
_DEFAULT_OCR_DOCUMENTS_BASE_URL = "http://localhost:8008"
_DEFAULT_OCR_REQUEST_TIMEOUT_SECONDS = 3600.0
_DEFAULT_MEMORY_BASE_URL = "http://localhost:8005"
_DEFAULT_MEMORY_REQUEST_TIMEOUT_SECONDS = 600.0


def _read_float(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {env_var}={raw!r} is not a number") from exc


def _read_str(env_var: str, default: str) -> str:
    """Unset -> default. Set-but-empty (after stripping) -> raise; a variable that is
    exported but empty is a misconfiguration, not "use the default" (CLAUDE.md §1/§2)."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"Environment variable {env_var} is set but empty")
    return stripped


def _read_optional_str(env_var: str) -> str | None:
    """Unset -> None (genuine absence). Set-but-empty -> raise, for the same reason as
    ``_read_str``."""
    raw = os.environ.get(env_var)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"Environment variable {env_var} is set but empty")
    return stripped


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime configuration for every local service octo_agent talks to."""

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_request_timeout_seconds: float
    ocr_base_url: str
    ocr_documents_base_url: str
    ocr_auth_header: str | None
    ocr_request_timeout_seconds: float
    memory_base_url: str
    memory_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            llm_base_url=_read_str("LLM_BASE_URL", _DEFAULT_LLM_BASE_URL),
            llm_api_key=_read_str("LLM_API_KEY", _DEFAULT_LLM_API_KEY),
            llm_model=_read_str("LLM_MODEL", _DEFAULT_LLM_MODEL),
            llm_request_timeout_seconds=_read_float(
                "LLM_REQUEST_TIMEOUT_SECONDS", _DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
            ),
            ocr_base_url=_read_str("OCR_BASE_URL", _DEFAULT_OCR_BASE_URL),
            ocr_documents_base_url=_read_str(
                "OCR_DOCUMENTS_BASE_URL", _DEFAULT_OCR_DOCUMENTS_BASE_URL
            ),
            ocr_auth_header=_read_optional_str("OCR_AUTH_HEADER"),
            ocr_request_timeout_seconds=_read_float(
                "OCR_REQUEST_TIMEOUT_SECONDS", _DEFAULT_OCR_REQUEST_TIMEOUT_SECONDS
            ),
            memory_base_url=_read_str("MEMORY_BASE_URL", _DEFAULT_MEMORY_BASE_URL),
            memory_request_timeout_seconds=_read_float(
                "MEMORY_REQUEST_TIMEOUT_SECONDS", _DEFAULT_MEMORY_REQUEST_TIMEOUT_SECONDS
            ),
        )
