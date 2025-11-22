# memory_service/graphiti_client.py
from graphiti_core import Graphiti

class GraphitiClient:
    def __init__(
        self,
        uri: str = "falkor://localhost:6379",
        graph_name: str = "photonic_memory",
        llm_provider: str = "openai",
        embedding_provider: str = "openai",
    ):
        self._graphiti = Graphiti(
            uri=uri,
            graph_name=graph_name,
            llm_provider=llm_provider,
            embedding_provider=embedding_provider,
        )
        self._initialized = False

    async def init(self):
        if not self._initialized:
            await self._graphiti.build_indices_and_constraints()
            self._initialized = True

    @property
    def client(self) -> Graphiti:
        return self._graphiti

    async def close(self):
        await self._graphiti.close()
