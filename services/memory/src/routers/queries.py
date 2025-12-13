# memory_service/routers/queries.py

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from shared_library.data_contracts import ConceptQuery, MemoryFact
from shared_library.memory_interface import PaperMemoryBackend
from ..graphiti_client import GraphitiClient
from ..graphiti_paper_backend import GraphitiPaperMemoryBackend

router = APIRouter(tags=["queries"])

_graphiti_client: GraphitiClient | None = None
_backend: GraphitiPaperMemoryBackend | None = None


async def get_backend() -> PaperMemoryBackend:
    global _graphiti_client, _backend
    if _graphiti_client is None:
        _graphiti_client = GraphitiClient()
    if _backend is None:
        _backend = GraphitiPaperMemoryBackend(_graphiti_client)
        await _backend.init()
    return _backend


@router.post("/concepts/search", response_model=List[MemoryFact])
async def search_concepts_endpoint(
    q: ConceptQuery,
    backend: PaperMemoryBackend = Depends(get_backend),
) -> List[MemoryFact]:
    return await backend.search_concepts(q)
