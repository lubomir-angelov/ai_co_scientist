# services/orchestrator/src/app_wiring.py

from __future__ import annotations

from .engines.factory import create_llm_engine
from .runtime_config import RuntimeConfig
#from .tools.memory import make_memory_tools
from .tools.ocr import make_ocr_tool
from .tools_registry import ToolRegistry


def build_registry(cfg: RuntimeConfig) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(make_ocr_tool(base_url=cfg.ocr_base_url, api_key=cfg.ocr_api_key or None))
#    for t in make_memory_tools(base_url=cfg.memory_base_url, api_key=cfg.memory_api_key or None):
#        reg.register(t)
    return reg


def build_llm(cfg: RuntimeConfig):
    return create_llm_engine(
        model_string=cfg.llm_model,
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        timeout_s=120.0,
    )
