from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from voice_service.api.deps import Services, get_services
from voice_service.core.errors import (
    InvalidContentLengthError,
    TooManyTranscriptionsError,
    UnsupportedLanguageError,
    UnsupportedMediaTypeError,
    UploadTooLargeError,
)
from voice_service.models.schemas import (
    MAX_TRANSCRIPTION_UPLOAD_BYTES,
    TranscriptionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Phone recorders produce audio/* or webm/mp4 containers; decodability (PyAV) is the real check.
_ACCEPTED_VIDEO_CONTAINERS = ("video/webm", "video/mp4")


def _media_type_accepted(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";")[0].strip().casefold()
    return media_type.startswith("audio/") or media_type in _ACCEPTED_VIDEO_CONTAINERS


def _reject_oversized_declaration(content_length: str | None) -> None:
    """413 before any byte is read when the client declares an over-limit body."""
    if content_length is None:
        return
    if not (content_length.isascii() and content_length.isdigit()):
        raise InvalidContentLengthError(f"Content-Length {content_length!r} is not a non-negative integer")
    if int(content_length) > MAX_TRANSCRIPTION_UPLOAD_BYTES:
        raise UploadTooLargeError(f"upload exceeds {MAX_TRANSCRIPTION_UPLOAD_BYTES} bytes")


async def _spool_request(request: Request) -> Path:
    """Stream the request body to a temp file, counting bytes as they arrive (a real bound: at
    most one chunk beyond the cap is ever held); the caller deletes the file."""
    with tempfile.NamedTemporaryFile(prefix="voice_stt_", delete=False) as tmp:
        path = Path(tmp.name)
        try:
            total = 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_TRANSCRIPTION_UPLOAD_BYTES:
                    raise UploadTooLargeError(f"upload exceeds {MAX_TRANSCRIPTION_UPLOAD_BYTES} bytes")
                await asyncio.to_thread(tmp.write, chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return path


@router.post("/v1/transcriptions", response_model=TranscriptionResponse)
async def transcribe(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
    language: Annotated[str | None, Query()] = None,
) -> TranscriptionResponse:
    """The request body is the raw audio (not multipart): a streaming byte bound can be real."""
    stt = services.registry.require_stt()
    content_type = request.headers.get("content-type")
    if not _media_type_accepted(content_type):
        raise UnsupportedMediaTypeError(f"content type {content_type!r} is not audio")
    if language is not None and language not in stt.supported_languages:
        raise UnsupportedLanguageError(f"language {language!r} is not supported by the speech model")
    _reject_oversized_declaration(request.headers.get("content-length"))
    if not services.transcriptions.try_acquire():
        raise TooManyTranscriptionsError("too many concurrent transcriptions; retry later")
    try:
        path = await _spool_request(request)
        try:
            transcript = await services.gate.run(stt.transcribe, path, language)
        finally:
            path.unlink(missing_ok=True)
    finally:
        services.transcriptions.release()

    logger.info(
        "transcription finished",
        extra={
            "duration_seconds": transcript.duration_seconds,
            "language": transcript.language,
            "segments": len(transcript.segments),
        },
    )
    return TranscriptionResponse(
        text=transcript.text,
        language=transcript.language,
        language_probability=transcript.language_probability,
        duration_seconds=transcript.duration_seconds,
        segments=transcript.segments,
        model=services.registry.manifest.stt.identity(),
    )
