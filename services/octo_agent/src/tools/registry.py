# services/orchestrator/src/tools/registry.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: Dict[str, Any]  # JSON Schema
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def list_tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def list_tools_for_llm(self) -> List[Dict[str, Any]]:
        # OpenAI function tool schema
        out: List[Dict[str, Any]] = []
        for t in self._tools.values():
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema,
                    },
                }
            )
        return out

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return await self._tools[name].handler(**args)
