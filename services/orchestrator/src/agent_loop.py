import logging
from typing import Any, Dict, List
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .tools_registry import ToolsRegistry
from .runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)

# Initialize config
config = RuntimeConfig()

# Create FastAPI app
app = FastAPI(title="AI Co-Scientist Orchestrator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize tools registry
registry = ToolsRegistry(
    llm_base_url=config.llm_base_url,
    llm_api_key=config.llm_api_key,
    ocr_base_url=config.ocr_base_url
)


class AgentLoop:
    def __init__(self, llm, registry, max_steps: int = 8) -> None:
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps

    async def run(self, task: str) -> str:
        tools = self.registry.list_tools_for_llm()

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are the orchestrator agent. Use tools when needed. "
                    "When you call tools, keep arguments minimal and valid."
                ),
            },
            {"role": "user", "content": task},
        ]

        for step in range(self.max_steps):
            resp = await self.llm.chat_completions(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.0,
                max_tokens=512,
            )

            choice = resp["choices"][0]
            msg = choice["message"]

            # If the model requests tool calls (OpenAI-style)
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )

                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                    except Exception:
                        args = {}
                    tool_call_id = tc.get("id", "")

                    logger.info("Calling tool=%s args=%s", tool_name, args)
                    result = await self.registry.call_tool(tool_name, args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

                continue

            # No tool calls: treat as final/normal assistant response
            content = msg.get("content") or ""
            if content.strip():
                return content

            # Defensive fallback
            return json.dumps(resp)

        return "Max steps reached without a final answer."


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    """List available tools"""
    return {"tools": registry.list_tools()}


@app.post("/run")
async def run_agent(task: str):
    """Run the agent loop with a task"""
    agent = AgentLoop(registry)
    await agent.run(task)
    return {"status": "running", "task": task}