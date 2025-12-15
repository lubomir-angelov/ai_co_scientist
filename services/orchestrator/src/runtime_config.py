import os
from dataclasses import dataclass

@dataclass
class RuntimeConfig:
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "local-llm")
    ocr_base_url: str = os.getenv("OCR_BASE_URL", "http://localhost:8001")