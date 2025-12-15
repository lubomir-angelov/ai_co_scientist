# services/orchestrator/src/runtime_config.py

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "http://localhost:8000")
    llm_api_key: str = os.environ.get("LLM_API_KEY", "local-llm")
    llm_model: str = os.environ.get(
        "LLM_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B-AWQ"
    )

    ocr_base_url: str = os.environ.get("OCR_BASE_URL", "http://localhost:8002")
    ocr_api_key: str = os.environ.get("OCR_API_KEY", "")

    #memory_base_url: str = os.environ.get("MEMORY_BASE_URL", "http://localhost:8001")
    #memory_api_key: str = os.environ.get("MEMORY_API_KEY", "")
