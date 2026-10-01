import io
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from voice_service.services.audio_encode import Mp3FileWriter, Mp3StreamEncoder

SAMPLE_RATE = 24000
EXPECTED_SECONDS = 6.5  # 3 s tone + 0.5 s silence + 3 s tone
TOLERANCE_SECONDS = 0.1


def _tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def _chunks() -> list[np.ndarray]:
    return [_tone(3.0), np.zeros(SAMPLE_RATE // 2, dtype=np.float32), _tone(3.0)]


def _duration(mp3: bytes) -> float:
    decoded, rate = sf.read(io.BytesIO(mp3), dtype="float32")
    assert rate == SAMPLE_RATE and decoded.ndim == 1
    return len(decoded) / rate


def test_stream_encoder_body_decodes_to_the_full_duration_without_xing_or_info() -> None:
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    body = b"".join(encoder.encode(chunk) for chunk in _chunks()) + encoder.finish()
    assert abs(_duration(body) - EXPECTED_SECONDS) <= TOLERANCE_SECONDS
    assert b"Xing" not in body[:400] and b"Info" not in body[:400]


def test_encode_returns_bytes_before_finish() -> None:
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    assert len(encoder.encode(_tone(3.0))) > 0
    encoder.abort()


def test_constant_bitrate_is_roughly_64kbps() -> None:
    rng = np.random.default_rng(0)
    pcm = (0.1 * rng.standard_normal(SAMPLE_RATE * 5)).astype(np.float32)
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    body = encoder.encode(pcm) + encoder.finish()
    assert 40 < len(body) * 8 / 5 / 1000 < 90


def test_encode_or_finish_after_finish_raises() -> None:
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    encoder.encode(_tone(0.5))
    encoder.finish()
    with pytest.raises(RuntimeError, match="already finished"):
        encoder.encode(_tone(0.5))
    with pytest.raises(RuntimeError, match="already finished"):
        encoder.finish()


def test_abort_closes_the_pipe_fds_and_is_idempotent() -> None:
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    read_fd = encoder._read_fd
    assert read_fd is not None
    encoder.encode(_tone(0.5))
    encoder.abort()
    encoder.abort()
    with pytest.raises(OSError):
        os.fstat(read_fd)


@pytest.mark.parametrize("bad", [np.zeros((2, 10), dtype=np.float32), np.zeros(10, dtype=np.float64)])
def test_rejects_wrong_shape_or_dtype(bad: np.ndarray, tmp_path: Path) -> None:
    encoder = Mp3StreamEncoder(SAMPLE_RATE)
    with pytest.raises(ValueError):
        encoder.encode(bad)
    encoder.abort()
    with Mp3FileWriter(tmp_path / "a.mp3", SAMPLE_RATE) as writer, pytest.raises(ValueError):
        writer.write(bad)


def test_file_writer_decodes_to_the_full_duration(tmp_path: Path) -> None:
    path = tmp_path / "section.mp3"
    with Mp3FileWriter(path, SAMPLE_RATE) as writer:
        for chunk in _chunks():
            writer.write(chunk)
    assert abs(_duration(path.read_bytes()) - EXPECTED_SECONDS) <= TOLERANCE_SECONDS
