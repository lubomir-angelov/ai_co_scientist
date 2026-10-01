from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from voice_service.api.deps import Services, get_services
from voice_service.api.streaming import start_mp3_stream
from voice_service.models.schemas import SpeechRequest
from voice_service.services.synthesis import SEGMENT_PAUSE_SECONDS, SpeechUnit

router = APIRouter()


@router.post("/v1/speech")
async def speech(
    request: SpeechRequest, services: Annotated[Services, Depends(get_services)]
) -> StreamingResponse:
    """Free-text speech: the text is spoken as given (no paper normalisation); never logged."""
    return await start_mp3_stream(
        services,
        [SpeechUnit(request.text, SEGMENT_PAUSE_SECONDS)],
        log_context={"text_chars": len(request.text)},
        headers={},
    )
