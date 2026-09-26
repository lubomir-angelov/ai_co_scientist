"""Read endpoints: time-aware fact retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shared_library.data_contracts import ConceptQuery, FactChanges, FactChangesQuery, MemoryFact
from shared_library.memory_interface import PaperMemoryBackend

from ..dependencies import get_backend

router = APIRouter(tags=["queries"])


@router.post("/concepts/search", response_model=list[MemoryFact])
async def search_concepts_endpoint(
    q: ConceptQuery, backend: PaperMemoryBackend = Depends(get_backend)
) -> list[MemoryFact]:
    return await backend.search_concepts(q)


@router.post("/facts/changes", response_model=FactChanges)
async def fact_changes_endpoint(
    q: FactChangesQuery, backend: PaperMemoryBackend = Depends(get_backend)
) -> FactChanges:
    return await backend.fact_changes(q)
