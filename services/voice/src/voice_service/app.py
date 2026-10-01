"""create_app: wires the services; the real GPU backends are injected as loaders (DIP)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import NoReturn

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from voice_service.api import routes_health, routes_papers, routes_renders, routes_speech, routes_stt
from voice_service.api.deps import Services
from voice_service.core.config import VoiceConfig
from voice_service.core.errors import VoiceError
from voice_service.models.schemas import ErrorBody, ModelManifest
from voice_service.services.backends import SttBackend, TtsBackend
from voice_service.services.gpu_gate import GpuGate, SlotLimiter
from voice_service.services.model_registry import ModelRegistry
from voice_service.services.ocr_client import OcrDocumentClient
from voice_service.services.render_store import RenderStore
from voice_service.services.render_worker import RenderQueue

logger = logging.getLogger(__name__)


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorBody(code=code, message=message).model_dump())


def create_app(
    *,
    config: VoiceConfig,
    manifest: ModelManifest,
    tts_loader: Callable[[], TtsBackend],
    stt_loader: Callable[[], SttBackend],
    exit_process: Callable[[int], NoReturn],
    ocr_transport: httpx.AsyncBaseTransport | None,
) -> FastAPI:
    registry = ModelRegistry(manifest, tts_loader, stt_loader, exit_process)
    gate = GpuGate()
    store = RenderStore(config.data_dir)
    ocr_http = httpx.AsyncClient(
        base_url=config.ocr_documents_base_url, timeout=config.ocr_timeout_seconds, transport=ocr_transport
    )
    renders = RenderQueue(
        store=store,
        registry=registry,
        gate=gate,
        queue_max=config.render_queue_max,
        tts_model=manifest.tts.identity(),
        voice=config.tts_voice,
        speed=config.tts_speed,
        exit_process=exit_process,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "voice service starting",
            extra={
                "ocr_documents_base_url": config.ocr_documents_base_url,
                "data_dir": str(config.data_dir),
                "voice": config.tts_voice,
                "speed": config.tts_speed,
                "tts_model": manifest.tts.identity().model_dump(),
                "stt_model": manifest.stt.identity().model_dump(),
            },
        )
        renders.start()
        loader = asyncio.create_task(registry.load_all(), name="model-load")
        try:
            yield
        finally:
            loader.cancel()
            await asyncio.gather(loader, return_exceptions=True)
            await renders.stop()
            await ocr_http.aclose()

    app = FastAPI(title="Voice service", version="0.1.0", lifespan=lifespan)
    app.state.services = Services(
        registry=registry,
        gate=gate,
        store=store,
        ocr=OcrDocumentClient(ocr_http),
        renders=renders,
        streams=SlotLimiter(config.max_active_streams),
        transcriptions=SlotLimiter(config.max_pending_transcriptions),
    )
    for module in (routes_health, routes_papers, routes_renders, routes_speech, routes_stt):
        app.include_router(module.router)

    @app.exception_handler(VoiceError)
    async def _voice_error(request: Request, exc: VoiceError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("request failed", extra={"path": request.url.path, "code": exc.code}, exc_info=exc)
        return _error_response(exc.status_code, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # loc + msg only: pydantic's own rendering would echo the (possibly huge) request input.
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return _error_response(422, "request_validation_failed", problems)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", extra={"path": request.url.path}, exc_info=exc)
        return _error_response(500, "internal_error", "internal server error")

    return app
