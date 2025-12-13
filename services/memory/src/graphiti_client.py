# memory_service/graphiti_client.py

from __future__ import annotations

from graphiti_core import Graphiti

from .config import settings


class GraphitiClient:
    """
    Thin wrapper around Graphiti for the memory service.
    """

    def __init__(self) -> None:
        self._graphiti = Graphiti(
            uri=settings.graphiti_uri,
            graph_name=settings.graph_name,
            llm_provider=settings.llm_provider,
            embedding_provider=settings.embedding_provider,
            # If needed, Graphiti can read API keys from env or you can
            # pass settings.openai_api_key / base_url into provider config.
        )
        self._initialized: bool = False

    async def init(self) -> None:
        if not self._initialized:
            await self._graphiti.build_indices_and_constraints()
            self._initialized = True

    @property
    def client(self) -> Graphiti:
        return self._graphiti

    async def close(self) -> None:
        await self._graphiti.close()
