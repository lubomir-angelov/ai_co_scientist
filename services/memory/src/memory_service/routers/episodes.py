"""Write endpoints: every call becomes one (or, for whole papers, several) Graphiti episodes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shared_library.data_contracts import (
    AgentStepEpisodeIn,
    EpisodeAck,
    HypothesisEpisodeIn,
    PaperIngestRequest,
    PaperIngestResponse,
    PaperNoteEpisodeIn,
    PaperSectionEpisodeIn,
)
from shared_library.memory_interface import PaperMemoryBackend

from ..config import Settings
from ..dependencies import get_backend, get_settings
from ..ingest import ingest_paper

router = APIRouter(tags=["episodes"])


@router.post("/paper/sections", response_model=EpisodeAck)
async def ingest_paper_section(
    ep: PaperSectionEpisodeIn, backend: PaperMemoryBackend = Depends(get_backend)
) -> EpisodeAck:
    return await backend.add_paper_section(ep)


@router.post("/paper/notes", response_model=EpisodeAck)
async def ingest_paper_note(
    ep: PaperNoteEpisodeIn, backend: PaperMemoryBackend = Depends(get_backend)
) -> EpisodeAck:
    return await backend.add_paper_note(ep)


@router.post("/paper/ingest", response_model=PaperIngestResponse)
async def ingest_whole_paper(
    req: PaperIngestRequest,
    backend: PaperMemoryBackend = Depends(get_backend),
    settings: Settings = Depends(get_settings),
) -> PaperIngestResponse:
    return await ingest_paper(backend, req, chunk_max_chars=settings.chunk_max_chars)


@router.post("/agent/steps", response_model=EpisodeAck)
async def record_agent_step(
    ep: AgentStepEpisodeIn, backend: PaperMemoryBackend = Depends(get_backend)
) -> EpisodeAck:
    return await backend.add_agent_step(ep)


@router.post("/hypotheses", response_model=EpisodeAck)
async def record_hypothesis(
    ep: HypothesisEpisodeIn, backend: PaperMemoryBackend = Depends(get_backend)
) -> EpisodeAck:
    return await backend.add_hypothesis(ep)
