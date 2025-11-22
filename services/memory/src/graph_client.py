from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.openai_client import OpenAILLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedderClient
from openai import AsyncOpenAI

from .config import settings

_graphiti: Graphiti | None = None

def get_graphiti() -> Graphiti:
    global _graphiti
    if _graphiti is not None:
        return _graphiti

    driver = FalkorDriver(
        host=settings.falkor_host,
        port=settings.falkor_port,
    )

    openai_client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
    )

    llm_client = OpenAILLMClient(
        client=openai_client,
        config=LLMConfig(model="gpt-5.1-mini", small_model="gpt-5.1-mini"),
    )
    embedder = OpenAIEmbedderClient(
        client=openai_client,
        model="text-embedding-3-small",
    )

    _graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
    )
    return _graphiti
