"""Service container shared by the routers (built once in create_app)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from voice_service.services.gpu_gate import GpuGate, SlotLimiter
from voice_service.services.model_registry import ModelRegistry
from voice_service.services.ocr_client import OcrDocumentClient
from voice_service.services.render_store import RenderStore
from voice_service.services.render_worker import RenderQueue


@dataclass(frozen=True)
class Services:
    registry: ModelRegistry
    gate: GpuGate
    store: RenderStore
    ocr: OcrDocumentClient
    renders: RenderQueue
    streams: SlotLimiter
    transcriptions: SlotLimiter


def get_services(request: Request) -> Services:
    return request.app.state.services
