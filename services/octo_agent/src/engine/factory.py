"""
Engine factory - adapted from octotools.
Creates the local LLM engine instance from RuntimeConfig.
"""

from __future__ import annotations

from engine.local_llm import ChatLocalLLM
from runtime_config import RuntimeConfig


def create_llm_engine(*, is_multimodal: bool, use_cache: bool = False, **kwargs) -> ChatLocalLLM:
    """
    Factory function to create the local LLM engine instance.

    Model, base URL, API key and request timeout come from ``RuntimeConfig.from_env()`` — the
    one source of that configuration — so every caller talks to the same gateway with the same
    model id and timeout.

    Args:
        is_multimodal: Support multimodal input.
        use_cache: Enable caching.
        **kwargs: Passed through to ``ChatLocalLLM``.

    Returns:
        ChatLocalLLM engine instance.
    """
    cfg = RuntimeConfig.from_env()
    return ChatLocalLLM(
        model_string=cfg.llm_model,
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        is_multimodal=is_multimodal,
        timeout_s=cfg.llm_request_timeout_seconds,
        use_cache=use_cache,
        **kwargs,
    )
