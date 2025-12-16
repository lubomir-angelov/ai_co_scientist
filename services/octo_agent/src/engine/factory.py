"""
Engine factory - adapted from octotools
Creates LLM engine instances
For our services, we default to ChatLocalLLM (via gateway)
"""

import sys
from pathlib import Path
from typing import Any

from .local_llm import ChatLocalLLM  # noqa: F401

def create_llm_engine(
    model_string: str,
    use_cache: bool = False,
    is_multimodal: bool = True,
    base_url: str = None,
    api_key: str = None,
    **kwargs
) -> Any:
    """
    Factory function to create LLM engine instance.
    
    For the orchestrator service, we primarily use ChatLocalLLM (gateway).
    Can be extended to support other engines from vendor/octotools.
    
    Args:
        model_string: Model identifier (e.g., "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B")
        use_cache: Enable caching
        is_multimodal: Support multimodal input
        base_url: LLM Gateway base URL
        api_key: API key for authentication
        **kwargs: Additional arguments
    
    Returns:
        LLM engine instance
    """
    
    # Default to local LLM gateway
    if "local" in model_string.lower() or "vllm" in model_string.lower():
        from .local_llm import ChatLocalLLM
        return ChatLocalLLM(
            model_string=model_string,
            base_url=base_url,
            api_key=api_key,
            use_cache=use_cache,
            is_multimodal=is_multimodal,
            **kwargs
        )
    
    # For other models, could import from vendor engines
    # This allows fallback to vendor implementations if needed
    else:
        raise ValueError(
            f"Engine {model_string} not supported in orchestrator. "
            "For now, use 'local' or 'vllm' prefix for local LLM gateway. "
            "Other engines can be added from vendor/octotools/engine/"
        )
