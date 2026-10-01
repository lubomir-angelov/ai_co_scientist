"""Incremental MP3 encoding via soundfile's bundled libsndfile (no ffmpeg dependency).

ONE continuous encoder session per response (``Mp3StreamEncoder``) or per file
(``Mp3FileWriter``); encoded chunks are never concatenated. Independently encoded chunks each
carry their own Info/Xing frame and encoder delay/padding, so a player decodes only the first
chunk. A seekable sink gets its Xing header rewritten at close (a streamed copy would keep a
zero-filled placeholder), so streams write to the write end of an OS pipe: libsndfile detects the
pipe, writes no Xing/Info tag, and the bytes appear incrementally after each write.
"""

from __future__ import annotations

import fcntl
import math
import os
import threading
from pathlib import Path
from types import TracebackType

import numpy as np
import soundfile as sf

MP3_CHANNELS = 1
MP3_BITRATE_MODE = "CONSTANT"
MP3_COMPRESSION_LEVEL = 0.6  # libsndfile scale (0 = best quality); about 64 kbps at 24 kHz mono

# Identifies the encoder settings inside render keys (§6: one definition). The sample rate is the
# backend's (TtsBackend.sample_rate) and is added to the render key separately.
MP3_ENCODING_PARAMS = {
    "channels": MP3_CHANNELS,
    "bitrate_mode": MP3_BITRATE_MODE,
    "compression_level": MP3_COMPRESSION_LEVEL,
}

# Named bound that makes the single-threaded pipe deadlock-free: PCM is fed to the encoder in
# blocks of at most ENCODER_FEED_SECONDS and the read end is drained after EACH block, so the
# pipe never holds more than one block's output. MPEG Layer III's spec ceiling (320 kbps) bounds
# that output independent of the configured compression level.
ENCODER_FEED_SECONDS = 0.5
MPEG_LAYER3_MAX_BITRATE_BPS = 320_000
_MAX_FEED_BYTES = math.ceil(MPEG_LAYER3_MAX_BITRATE_BPS / 8 * ENCODER_FEED_SECONDS)
_READ_BYTES = 65536


def _check_pcm(pcm: np.ndarray) -> None:
    if pcm.ndim != 1 or pcm.dtype != np.float32:
        raise ValueError(f"expected 1-D float32 PCM, got shape {pcm.shape} dtype {pcm.dtype}")


def _open_mp3_writer(target: int | Path, sample_rate: int) -> sf.SoundFile:
    """The only place the MP3 format arguments appear (§6)."""
    options: dict[str, object] = {"closefd": True} if isinstance(target, int) else {}
    return sf.SoundFile(
        target,
        "w",
        samplerate=sample_rate,
        channels=MP3_CHANNELS,
        format="MP3",
        subtype="MPEG_LAYER_III",
        bitrate_mode=MP3_BITRATE_MODE,
        compression_level=MP3_COMPRESSION_LEVEL,
        **options,
    )


class Mp3FileWriter:
    """Write PCM incrementally into one seekable MP3 file; closing finalizes its Info tag.

    A call whose awaiting coroutine was cancelled keeps running in its worker thread, so every
    operation takes the lock: ``close`` never races an in-flight ``write``.
    """

    def __init__(self, path: Path, sample_rate: int) -> None:
        self._writer = _open_mp3_writer(path, sample_rate)
        self._lock = threading.Lock()

    def write(self, pcm: np.ndarray) -> None:
        _check_pcm(pcm)
        with self._lock:
            self._writer.write(pcm)

    def close(self) -> None:
        with self._lock:
            self._writer.close()

    def __enter__(self) -> Mp3FileWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class Mp3StreamEncoder:
    """One incremental MP3 session over an OS pipe. Every method is synchronous: call each through
    ``asyncio.to_thread``. ``encode`` feeds bounded blocks and drains after each (see
    ``ENCODER_FEED_SECONDS``), which is what keeps the single-threaded pipe deadlock-free. A call
    whose awaiting coroutine was cancelled keeps running in its worker thread, so every operation
    takes the lock: ``abort`` never races an in-flight ``encode``."""

    def __init__(self, sample_rate: int) -> None:
        self._feed_samples = math.ceil(ENCODER_FEED_SECONDS * sample_rate)
        read_fd, write_fd = os.pipe()
        try:
            capacity = fcntl.fcntl(write_fd, fcntl.F_GETPIPE_SZ)
            if capacity < 2 * _MAX_FEED_BYTES:
                raise RuntimeError(
                    f"OS pipe capacity {capacity} bytes is below the required {2 * _MAX_FEED_BYTES}"
                )
            os.set_blocking(read_fd, False)
            self._writer: sf.SoundFile | None = _open_mp3_writer(write_fd, sample_rate)
        except BaseException:
            os.close(read_fd)
            os.close(write_fd)
            raise
        self._read_fd: int | None = read_fd
        self._lock = threading.Lock()

    def encode(self, pcm: np.ndarray) -> bytes:
        """Feed ``pcm`` and return whatever encoded bytes are available now (may be empty)."""
        _check_pcm(pcm)
        with self._lock:
            writer = self._open_writer("encode")
            parts: list[bytes] = []
            for block in np.array_split(pcm, max(1, math.ceil(len(pcm) / self._feed_samples))):
                writer.write(block)
                parts.append(self._drain())
            return b"".join(parts)

    def finish(self) -> bytes:
        """Flush the encoder tail, drain to EOF and release the pipe; valid exactly once."""
        with self._lock:
            writer = self._open_writer("finish")
            self._writer = None
            writer.close()
            tail = self._drain()
            self._close_read_end()
            return tail

    def abort(self) -> None:
        """Release both pipe ends without producing output; idempotent."""
        with self._lock:
            writer, self._writer = self._writer, None
            try:
                if writer is not None:
                    writer.close()
            finally:
                self._close_read_end()

    def _open_writer(self, operation: str) -> sf.SoundFile:
        if self._writer is None:
            raise RuntimeError(f"{operation} on an encoder that is already finished or aborted")
        return self._writer

    def _close_read_end(self) -> None:
        fd, self._read_fd = self._read_fd, None
        if fd is not None:
            os.close(fd)

    def _drain(self) -> bytes:
        """Read everything currently buffered in the pipe (until empty-for-now or EOF)."""
        if self._read_fd is None:
            raise RuntimeError("drain on a released pipe")
        chunks: list[bytes] = []
        while True:
            try:
                data = os.read(self._read_fd, _READ_BYTES)
            except BlockingIOError:
                break
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)
