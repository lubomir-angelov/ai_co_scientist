from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from voice_service.api.deps import Services, get_services
from voice_service.models.schemas import HealthModels, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(services: Annotated[Services, Depends(get_services)]) -> HealthResponse:
    registry = services.registry
    return HealthResponse(
        status="ok",
        service="voice",
        ready=registry.tts_loaded and registry.stt_loaded,
        tts_loaded=registry.tts_loaded,
        stt_loaded=registry.stt_loaded,
        models=HealthModels(tts=registry.manifest.tts.identity(), stt=registry.manifest.stt.identity()),
    )
