"""Shared fixtures: fake TTS/STT backends (torch/kokoro/faster-whisper are never imported here)."""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from shared_library.data_contracts import OCRResponse

from voice_service.core.config import VoiceConfig
from voice_service.core.errors import AudioDecodeError
from voice_service.models.schemas import (
    ModelManifest,
    SttManifestEntry,
    TranscriptionSegment,
    TtsManifestEntry,
)
from voice_service.services.backends import PhonemeToken, Transcript
from voice_service.services.gpu_gate import GpuGate

FAKE_SAMPLE_RATE = 24000
SAMPLES_PER_PHONEME = 10
UNDECODABLE_MARKER = b"UNDECODABLE"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeTts:
    """One token per character; synthesize returns a tone whose length tracks the phoneme count."""

    device = "cpu"  # the fake genuinely runs on the CPU
    sample_rate = FAKE_SAMPLE_RATE

    def __init__(self, max_phonemes: int = 510, gate: GpuGate | None = None) -> None:
        self.max_phonemes = max_phonemes
        self.gate = gate
        self.synthesize_calls: list[str] = []
        self.phonemize_calls: list[str] = []
        self.fail_on: Callable[[str], bool] | None = None

    def _assert_off_loop_under_gate(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # no running loop in this thread: we are in a worker thread, as required
        else:
            raise AssertionError("backend called on the event-loop thread")
        if self.gate is not None:
            assert self.gate._semaphore.locked()

    def phonemize(self, text: str) -> list[PhonemeToken]:
        self._assert_off_loop_under_gate()
        self.phonemize_calls.append(text)
        return [
            PhonemeToken(
                phonemes=None if ch == "~" else ch,
                whitespace=text[i + 1 : i + 2] == " ",
                is_punctuation=unicodedata.category(ch)[0] == "P",
            )
            for i, ch in enumerate(text)
            if ch != " "
        ]

    def synthesize(self, phonemes: str) -> np.ndarray:
        self._assert_off_loop_under_gate()
        if len(phonemes) > self.max_phonemes:
            raise ValueError("window exceeds max_phonemes")
        if self.fail_on is not None and self.fail_on(phonemes):
            raise RuntimeError("synthetic synthesis failure")
        self.synthesize_calls.append(phonemes)
        t = np.arange(len(phonemes) * SAMPLES_PER_PHONEME) / FAKE_SAMPLE_RATE
        return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class FakeStt:
    device = "cpu"
    supported_languages = frozenset({"en", "de"})  # test data

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str | None]] = []

    def transcribe(self, audio_path: Path, language: str | None) -> Transcript:
        self.calls.append((audio_path, language))
        if UNDECODABLE_MARKER in audio_path.read_bytes():
            raise AudioDecodeError("synthetic decode failure")
        return Transcript(
            text="hello world",
            language=language if language is not None else "en",
            language_probability=0.99,
            duration_seconds=1.5,
            segments=[TranscriptionSegment(start=0.0, end=1.5, text="hello world")],
        )


def make_manifest(tmp_path: Path) -> ModelManifest:
    tts_dir = tmp_path / "models" / "kokoro"
    stt_dir = tmp_path / "models" / "whisper"
    tts_dir.mkdir(parents=True, exist_ok=True)
    stt_dir.mkdir(parents=True, exist_ok=True)
    return ModelManifest(
        tts=TtsManifestEntry(repo_id="hexgrad/Kokoro-82M", revision="rev-tts", model_dir=tts_dir),
        stt=SttManifestEntry(
            repo_id="mobiuslabsgmbh/faster-whisper-large-v3-turbo",
            revision="rev-stt",
            model_dir=stt_dir,
            compute_type="int8_float16",
        ),
    )


def make_config(tmp_path: Path, **overrides: object) -> VoiceConfig:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    manifest_path = tmp_path / "voice-models.json"
    manifest_path.write_text("{}", encoding="utf-8")
    env = {
        "VOICE_OCR_BASE_URL": "http://ocr.test",
        "VOICE_OCR_TIMEOUT_SECONDS": "5",
        "VOICE_DATA_DIR": str(data_dir),
        "VOICE_MODELS_MANIFEST": str(manifest_path),
        "VOICE_TTS_VOICE": "af_heart",
        "VOICE_TTS_SPEED": "1.0",
        "VOICE_MAX_ACTIVE_STREAMS": "2",
        "VOICE_MAX_PENDING_TRANSCRIPTIONS": "2",
        "VOICE_RENDER_QUEUE_MAX": "4",
        "LOG_LEVEL": "INFO",
    }
    env.update({k: str(v) for k, v in overrides.items()})
    return VoiceConfig.from_mapping(env)


class ExitRecorder:
    """Stands in for os._exit: records the code instead of killing the test process."""

    def __init__(self) -> None:
        self.codes: list[int] = []

    def __call__(self, code: int) -> None:
        self.codes.append(code)


@pytest.fixture
def exit_recorder() -> ExitRecorder:
    return ExitRecorder()


def load_ocr_fixture() -> OCRResponse:
    path = Path(__file__).parent / "fixtures" / "ocr_response_small.json"
    return OCRResponse.model_validate_json(path.read_text(encoding="utf-8"))
