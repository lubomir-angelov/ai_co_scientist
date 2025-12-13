# memory_service/routers/episodes.py

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from shared_library.data_contracts import (
    PaperSectionEpisodeIn,
    PaperNoteEpisodeIn,
)
from shared_library.memory_interface import PaperMemoryBackend
from ..graphiti_client import GraphitiClient
from ..graphiti_paper_backend import GraphitiPaperMemoryBackend

router = APIRouter(tags=["episodes"])

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


@router.post("/paper/sections")
async def ingest_paper_section(
    ep: PaperSectionEpisodeIn,
    backend: PaperMemoryBackend = Depends(get_backend),
) -> Dict[str, str]:
    episode_id = await backend.add_paper_section(ep)
    return {"episode_id": episode_id}


@router.post("/paper/notes")
async def ingest_paper_note(
    ep: PaperNoteEpisodeIn,
    backend: PaperMemoryBackend = Depends(get_backend),
) -> Dict[str, str]:
    episode_id = await backend.add_paper_note(ep)
    return {"episode_id": episode_id}
