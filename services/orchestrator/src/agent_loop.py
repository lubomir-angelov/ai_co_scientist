from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .tools_registry import ToolsRegistry
from .runtime_config import RuntimeConfig

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
    def __init__(self, registry):
        self.registry = registry
    
    async def run(self, task: str):
        """Main agent loop"""
        tools = self.registry.list_tools()
        # Pass tools to LLM for planning
        # Call tools as needed via self.registry.call_tool(name, **args)
        pass


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