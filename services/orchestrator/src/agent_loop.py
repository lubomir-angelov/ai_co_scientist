from tools_registry import ToolsRegistry

class AgentLoop:
    def __init__(self, config):
        self.registry = ToolsRegistry(
            llm_base_url=config.llm_base_url,
            llm_api_key=config.llm_api_key,
            ocr_base_url=config.ocr_base_url
        )
    
    async def run(self, task: str):
        """Main agent loop"""
        tools = self.registry.list_tools()
        # Pass tools to LLM for planning
        # Call tools as needed via self.registry.call_tool(name, **args)
        pass