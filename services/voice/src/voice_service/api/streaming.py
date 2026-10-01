"""Shared chunked MP3 streaming (section stream and free-text speech).

Every resource of a stream (slot, synthesis generator, encoder) is owned by a ``_StreamSession``
whose ``close`` is tied to the ASGI RESPONSE lifecycle, not to the body generator: Starlette
cancels the body task on client disconnect and never closes the body iterator.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, MutableMapping, Sequence
from typing import Any

import numpy as np
from fastapi.responses import StreamingResponse

from voice_service.api.deps import Services
from voice_service.core.errors import TooManyStreamsError
from voice_service.services.audio_encode import Mp3StreamEncoder
from voice_service.services.backends import TtsBackend
from voice_service.services.synthesis import SpeechUnit, SynthesisStats, synthesize_units

logger = logging.getLogger(__name__)


class _StreamSession:
    """Owns the stream slot, the synthesis generator and the encoder; ``close`` is idempotent."""

    def __init__(
        self,
        services: Services,
        backend: TtsBackend,
        units: Sequence[SpeechUnit],
        log_context: Mapping[str, object],
    ) -> None:
        self._slots = services.streams
        self._log_context = log_context
        self.stats = SynthesisStats(sample_rate=backend.sample_rate)
        self.chunks: AsyncGenerator[np.ndarray, None] = synthesize_units(backend, services.gate, units, self.stats)
        self.encoder: Mp3StreamEncoder | None = None
        self.finished = False
        self._closed = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.chunks.aclose()
            if self.encoder is not None and not self.finished:
                await asyncio.to_thread(self.encoder.abort)
        finally:
            self._slots.release()
        if not self.finished:
            logger.info(
                "stream closed before completion",
                extra={
                    **self._log_context,
                    "windows": self.stats.windows,
                    "audio_seconds": round(self.stats.audio_seconds, 2),
                },
            )


class _SessionStreamingResponse(StreamingResponse):
    """Releases the session on completion, error, cancellation and disconnect-before-first-byte."""

    def __init__(self, session: _StreamSession, body: AsyncIterator[bytes], headers: Mapping[str, str]) -> None:
        super().__init__(body, media_type="audio/mpeg", headers=dict(headers))
        self._session = session

    async def __call__(
        self, scope: MutableMapping[str, Any], receive: Any, send: Any
    ) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._session.close()


async def start_mp3_stream(
    services: Services,
    units: Sequence[SpeechUnit],
    log_context: Mapping[str, object],
    headers: Mapping[str, str],
) -> StreamingResponse:
    """Synthesize and encode the FIRST window before returning, so model/OOM/G2P failures and
    ``NothingToSpeakError`` become proper 4xx/5xx responses. A failure after headers are sent logs
    ``stream aborted`` and re-raises inside the generator: the transfer ends incomplete, never
    padded or ended "successfully". The stream starts at the first spoken window."""
    backend = services.registry.require_tts()
    if not services.streams.try_acquire():
        raise TooManyStreamsError("too many concurrent streams; retry later")

    session = _StreamSession(services, backend, units, log_context)
    try:
        first_pcm = await anext(session.chunks)
        encoder = await asyncio.to_thread(Mp3StreamEncoder, backend.sample_rate)
        session.encoder = encoder
        first_mp3 = await asyncio.to_thread(encoder.encode, first_pcm)
    except BaseException:
        await session.close()
        raise

    async def body() -> AsyncIterator[bytes]:
        try:
            if first_mp3:  # LAME may buffer: an empty first read is not an error
                yield first_mp3
            async for pcm in session.chunks:
                encoded = await asyncio.to_thread(encoder.encode, pcm)
                if encoded:
                    yield encoded
            tail = await asyncio.to_thread(encoder.finish)
            session.finished = True
            yield tail
            logger.info(
                "stream finished",
                extra={
                    **log_context,
                    "windows": session.stats.windows,
                    "unspoken_tokens": session.stats.unspoken_tokens,
                    "audio_seconds": round(session.stats.audio_seconds, 2),
                    "synth_seconds": round(session.stats.synth_seconds, 2),
                    "phonemize_seconds": round(session.stats.phonemize_seconds, 2),
                },
            )
        except Exception:
            logger.exception("stream aborted", extra=dict(log_context))
            raise

    return _SessionStreamingResponse(session, body(), headers)
