"""Request-scoped access to the memory backend, with lazy readiness recovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import Request

from shared_library.memory_interface import PaperMemoryBackend

from .config import Settings

logger = logging.getLogger(__name__)


class BackendUnavailableError(RuntimeError):
    """The graph backend could not be initialised (e.g. FalkorDB is unreachable)."""


@dataclass
class MemoryRuntime:
    """Backend plus readiness state, stored on ``app.state.memory``."""

    backend: PaperMemoryBackend
    settings: Settings
    ready: bool = False
    _init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def ensure_ready(self) -> None:
        if self.ready:
            return
        async with self._init_lock:
            if self.ready:
                return
            try:
                await self.backend.init()
            except Exception as exc:
                logger.exception("Memory backend initialisation failed")
                raise BackendUnavailableError("memory graph backend is not available") from exc
            self.ready = True


def get_runtime(request: Request) -> MemoryRuntime:
    return request.app.state.memory


async def get_backend(request: Request) -> PaperMemoryBackend:
    runtime = get_runtime(request)
    await runtime.ensure_ready()
    return runtime.backend


def get_settings(request: Request) -> Settings:
    return get_runtime(request).settings
