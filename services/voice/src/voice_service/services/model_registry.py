"""ModelRegistry: models are loaded once, in the background, with observable readiness.

A load failure is fatal (the process exits): a service that cannot load its models is broken,
not degraded, and there is no partially-ready mode.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import NoReturn

from voice_service.core.errors import ModelsLoadingError
from voice_service.models.schemas import ModelManifest
from voice_service.services.backends import DeviceBackend, SttBackend, TtsBackend

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(
        self,
        manifest: ModelManifest,
        tts_loader: Callable[[], TtsBackend],
        stt_loader: Callable[[], SttBackend],
        exit_process: Callable[[int], NoReturn],
    ) -> None:
        self.manifest = manifest
        self._tts_loader = tts_loader
        self._stt_loader = stt_loader
        self._exit_process = exit_process
        self._tts: TtsBackend | None = None
        self._stt: SttBackend | None = None

    @property
    def tts_loaded(self) -> bool:
        return self._tts is not None

    @property
    def stt_loaded(self) -> bool:
        return self._stt is not None

    async def load_all(self) -> None:
        """Load TTS then STT sequentially so peak VRAM is predictable."""
        try:
            self._tts = await self._load("tts", self._tts_loader)
            self._stt = await self._load("stt", self._stt_loader)
        except Exception:
            self._exit_process(1)

    @staticmethod
    async def _load[T: DeviceBackend](name: str, loader: Callable[[], T]) -> T:
        logger.info("model load started", extra={"model": name})
        started = time.perf_counter()
        try:
            backend = await asyncio.to_thread(loader)
        except Exception:
            logger.exception("model load failed", extra={"model": name})
            raise
        logger.info(
            "model load finished",
            extra={"model": name, "seconds": round(time.perf_counter() - started, 2), "device": backend.device},
        )
        return backend

    def require_tts(self) -> TtsBackend:
        if self._tts is None:
            raise ModelsLoadingError("TTS model is still loading")
        return self._tts

    def require_stt(self) -> SttBackend:
        if self._stt is None:
            raise ModelsLoadingError("STT model is still loading")
        return self._stt
