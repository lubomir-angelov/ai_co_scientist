from __future__ import annotations

import asyncio
import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from shared_library.data_contracts import DocId

from voice_service.api.deps import Services, get_services
from voice_service.core.errors import RenderNotFoundError, RenderStaleError, SectionNotRenderedError
from voice_service.models.schemas import RenderRequest, RenderStatus, SectionRenderStatus, Sha256Hex

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/papers/{doc_id}/renders")

ServicesDep = Annotated[Services, Depends(get_services)]


def _section_url(doc_id: str, key: str, index: int) -> str:
    return f"/v1/papers/{quote(doc_id)}/renders/{key}/sections/{index}.mp3"


def _status(services: Services, doc_id: str, key: str) -> RenderStatus:
    job = services.renders.find_active(doc_id, key)
    manifest = services.store.find_manifest(doc_id, key)
    if job is None and manifest is None:
        raise RenderNotFoundError(f"no render {key} for doc_id {doc_id!r}")
    records = [] if manifest is None else [manifest.sections[i] for i in sorted(manifest.sections)]
    return RenderStatus(
        doc_id=doc_id,
        render_key=key,
        active=job is not None,
        queued_position=None if job is None else services.renders.queued_position(job),
        current_index=None if job is None else job.current_index,
        requested=None if job is None else list(job.requested),
        sections=[
            SectionRenderStatus(
                **record.model_dump(),
                download_url=_section_url(doc_id, key, record.index) if record.status == "rendered" else None,
            )
            for record in records
        ],
    )


@router.post("", status_code=202, response_model=RenderStatus)
async def submit_render(doc_id: DocId, request: RenderRequest, services: ServicesDep) -> RenderStatus:
    services.registry.require_tts()
    job = await services.renders.submit(doc_id, request.section_indices)
    logger.info(
        "render submitted",
        extra={"doc_id": doc_id, "render_key": job.render_key, "sections": request.section_indices},
    )
    return _status(services, doc_id, job.render_key)


@router.get("/{render_key}", response_model=RenderStatus)
async def render_status(doc_id: DocId, render_key: Sha256Hex, services: ServicesDep) -> RenderStatus:
    return _status(services, doc_id, render_key)


@router.get("/{render_key}/sections/{index}.mp3")
async def download_section(doc_id: DocId, render_key: Sha256Hex, index: int, services: ServicesDep) -> FileResponse:
    manifest = services.store.find_manifest(doc_id, render_key)
    record = None if manifest is None else manifest.sections.get(index)
    if record is None or record.status != "rendered":
        raise SectionNotRenderedError(f"section {index} of render {render_key} is not rendered")
    path = await asyncio.to_thread(services.store.verify_rendered, doc_id, render_key, record)
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/{render_key}/playlist.m3u")
async def playlist(doc_id: DocId, render_key: Sha256Hex, services: ServicesDep) -> Response:
    manifest = services.store.find_manifest(doc_id, render_key)
    if manifest is None:
        raise RenderNotFoundError(f"no render {render_key} for doc_id {doc_id!r}")
    script = services.store.load_script(doc_id)
    if manifest.script_sha256 != script.script_sha256:
        raise RenderStaleError(
            f"render {render_key} was made from script {manifest.script_sha256}; "
            f"the current script is {script.script_sha256}"
        )
    lines = ["#EXTM3U"]
    for index in sorted(manifest.sections):
        record = manifest.sections[index]
        if record.status != "rendered" or record.audio_seconds is None:
            continue
        heading = script.sections[index].heading
        lines.append(f"#EXTINF:{record.audio_seconds:.3f},{'' if heading is None else heading}")
        lines.append(f"sections/{index}.mp3")
    return Response("\n".join(lines) + "\n", media_type="audio/x-mpegurl")
