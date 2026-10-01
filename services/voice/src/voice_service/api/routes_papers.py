from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from shared_library.data_contracts import DocId

from voice_service.api.deps import Services, get_services
from voice_service.api.streaming import start_mp3_stream
from voice_service.models.schemas import (
    PaperListing,
    PaperScript,
    ScriptPrepareResponse,
    ScriptSummary,
    SectionSummary,
)
from voice_service.services.script_builder import (
    SCRIPT_BUILDER_VERSION,
    build_script,
    ocr_fingerprint,
    speakable_section,
)
from voice_service.services.synthesis import units_for_section

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/papers")

ServicesDep = Annotated[Services, Depends(get_services)]


def summarize(script: PaperScript) -> ScriptSummary:
    return ScriptSummary(
        script_sha256=script.script_sha256,
        built_at=script.built_at,
        sections=[
            SectionSummary(
                index=s.index,
                heading=s.heading,
                page_start=s.page_start,
                page_end=s.page_end,
                speakable=s.speakable,
                segment_count=len(s.segments),
                omitted_count=len(s.omitted),
                spoken_char_count=s.spoken_char_count,
            )
            for s in script.sections
        ],
    )


@router.post("/{doc_id}/script", response_model=ScriptPrepareResponse)
async def prepare_script(doc_id: DocId, services: ServicesDep) -> ScriptPrepareResponse:
    ocr_response = await services.ocr.fetch(doc_id)
    ocr_sha256 = ocr_fingerprint(ocr_response)
    existing = services.store.find_script(doc_id)
    if (
        existing is not None
        and existing.ocr_sha256 == ocr_sha256
        and existing.builder_version == SCRIPT_BUILDER_VERSION
    ):
        outcome, script = "unchanged", existing
    else:
        script = await asyncio.to_thread(build_script, ocr_response, datetime.now(UTC))
        services.store.save_script(script)
        outcome = "created" if existing is None else "rebuilt"
    logger.info(
        "script prepared",
        extra={"doc_id": doc_id, "outcome": outcome, "sections": len(script.sections)},
    )
    return ScriptPrepareResponse(doc_id=doc_id, outcome=outcome, script=summarize(script))


@router.get("", response_model=list[PaperListing])
async def list_papers(services: ServicesDep) -> list[PaperListing]:
    scripts = await asyncio.to_thread(services.store.list_scripts)
    return [
        PaperListing(
            doc_id=s.doc_id,
            script_sha256=s.script_sha256,
            built_at=s.built_at,
            section_count=len(s.sections),
        )
        for s in scripts
    ]


@router.get("/{doc_id}/script", response_model=PaperScript)
async def get_script(doc_id: DocId, services: ServicesDep) -> PaperScript:
    return services.store.load_script(doc_id)


@router.get("/{doc_id}/sections/{index}/stream")
async def stream_section(doc_id: DocId, index: int, services: ServicesDep) -> StreamingResponse:
    script = services.store.load_script(doc_id)
    section = speakable_section(script, index)
    return await start_mp3_stream(
        services,
        units_for_section(section),
        log_context={"doc_id": doc_id, "section": index},
        headers={"X-Voice-Render-Key": services.renders.render_key_for(script)},
    )
