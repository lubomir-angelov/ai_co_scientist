"""Whole-paper ingestion: OCR sections -> chunks -> idempotent section episodes."""

from __future__ import annotations

import logging

from shared_library.data_contracts import (
    PaperIngestRequest,
    PaperIngestResponse,
    PaperSectionEpisodeIn,
)
from shared_library.memory_interface import PaperMemoryBackend

from .chunking import chunk_text

logger = logging.getLogger(__name__)


async def ingest_paper(
    backend: PaperMemoryBackend, req: PaperIngestRequest, *, chunk_max_chars: int
) -> PaperIngestResponse:
    """
    Ingest sections sequentially, in reading order, so Graphiti sees earlier sections
    as context for later ones. Chunks already stored are skipped by the backend, so a
    failed ingest can be retried with the same request and resumes where it stopped.
    """
    episodes = []
    for section_index, section in enumerate(req.sections):
        chunks = chunk_text(section.text, chunk_max_chars)
        if not chunks:
            logger.info(
                "Skipping empty section: paper=%s section=%r", req.paper.paper_id, section.name
            )
            continue
        for chunk_index, chunk in enumerate(chunks):
            logger.info(
                "Paper %s: section %d/%d %r chunk %d/%d",
                req.paper.paper_id,
                section_index + 1,
                len(req.sections),
                section.name,
                chunk_index + 1,
                len(chunks),
            )
            ack = await backend.add_paper_section(
                PaperSectionEpisodeIn(
                    paper=req.paper,
                    section_name=section.name,
                    section_index=section_index,
                    chunk_index=chunk_index,
                    text=chunk,
                )
            )
            episodes.append(ack)

    created = sum(1 for ack in episodes if ack.created)
    logger.info(
        "Paper %s ingested: episodes=%d new=%d skipped=%d",
        req.paper.paper_id,
        len(episodes),
        created,
        len(episodes) - created,
    )
    return PaperIngestResponse(paper_id=req.paper.paper_id, episodes=episodes)
