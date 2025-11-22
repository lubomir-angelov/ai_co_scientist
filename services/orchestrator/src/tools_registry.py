from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import httpx
import json


@dataclass
class ToolSchema:
    """Tool specification for agent"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON schema
    endpoint: str
    method: str = "POST"


class ToolsRegistry:
    """Registry for orchestrator tools (LLM, OCR, etc.)"""
    
    def __init__(self, llm_base_url: str, llm_api_key: str, ocr_base_url: str):
        self.llm_base_url = llm_base_url
        self.llm_api_key = llm_api_key
        self.ocr_base_url = ocr_base_url
        self.tools: Dict[str, ToolSchema] = {}
        self._register_tools()
    
    def _register_tools(self) -> None:
        """Register available tools"""
        self.register(
            ToolSchema(
                name="llm_chat",
                description="Call LLM for reasoning/text generation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                                    "content": {"type": "string"}
                                }
                            }
                        },
                        "temperature": {"type": "number", "default": 0.7}
                    },
                    "required": ["messages"]
                },
                endpoint=f"{self.llm_base_url}/chat/completions",
                method="POST"
            )
        )
        
        self.register(
            ToolSchema(
                name="ocr_process",
                description="Extract text from images via OCR",
                input_schema={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string"},
                        "language": {"type": "string", "default": "eng"}
                    },
                    "required": ["image_path"]
                },
                endpoint=f"{self.ocr_base_url}/process",
                method="POST"
            )
        )
    
    def register(self, tool: ToolSchema) -> None:
        """Register a tool"""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[ToolSchema]:
        """Get tool by name"""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools as dicts"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in self.tools.values()
        ]
    
    async def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool"""
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        headers = {}
        if tool_name == "llm_chat":
            headers["Authorization"] = f"Bearer {self.llm_api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=tool.method,
                url=tool.endpoint,
                json=kwargs,
                headers=headers,
                timeout=300.0
            )
            response.raise_for_status()
            return await response.json()