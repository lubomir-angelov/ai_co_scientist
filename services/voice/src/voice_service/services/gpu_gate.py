"""GpuGate: the ONLY way to run backend inference; and SlotLimiter for bounded concurrency."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

GPU_INFERENCE_CONCURRENCY = 1


async def _wait_uncancellable(task: asyncio.Future[object]) -> None:
    """Wait until ``task`` is done even if this coroutine is cancelled again meanwhile.

    Further cancellations are absorbed here only because the caller re-raises CancelledError
    right after the wait, so none is dropped.
    """
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            continue


class GpuGate:
    """Serialises every backend call (phonemize, synthesize, transcribe) off the event loop.

    Acquired per call, not per stream, so a long stream interleaves fairly with renders and STT.
    Invariant: the gate is held for as long as ANY inference thread is resident. A caller that is
    cancelled while its worker thread runs keeps the gate until the thread actually finishes, so
    VRAM stays bounded to one inference even across client disconnects.
    """

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(GPU_INFERENCE_CONCURRENCY)

    async def run(self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        async with self._semaphore:
            task = asyncio.ensure_future(asyncio.to_thread(fn, *args, **kwargs))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await _wait_uncancellable(task)
                if not task.cancelled() and task.exception() is not None:
                    logger.error("gpu call failed after its caller was cancelled", exc_info=task.exception())
                raise


class SlotLimiter:
    """Non-blocking bounded concurrency: a full limiter refuses immediately (HTTP 429)."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity = capacity
        self._in_use = 0

    def try_acquire(self) -> bool:
        if self._in_use >= self._capacity:
            return False
        self._in_use += 1
        return True

    def release(self) -> None:
        if self._in_use == 0:
            raise RuntimeError("SlotLimiter.release without a matching acquire")
        self._in_use -= 1
