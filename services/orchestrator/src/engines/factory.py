# services/orchestrator/src/engines/factory.py

from __future__ import annotations

from typing import Any, Optional

from .local_llm import ChatLocalLLM


def create_llm_engine(
    model_string: str,
    *,
    base_url: str,
    api_key: Optional[str] = None,
    timeout_s: float = 120.0,
    **_: Any,
) -> ChatLocalLLM:
    """
    For orchestrator: always return ChatLocalLLM (OpenAI-compatible gateway).
    If/when you need additional engines, branch here on an explicit engine type.
    """
    if not base_url:
        raise ValueError("base_url is required for ChatLocalLLM")

    return ChatLocalLLM(
        model_string=model_string,
        base_url=base_url,
        api_key=api_key,
        timeout_s=timeout_s,
    )
