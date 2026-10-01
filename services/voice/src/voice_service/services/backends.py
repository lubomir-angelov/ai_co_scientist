"""Backend Protocols (Strategy / ports): the real GPU engines and the test fakes both satisfy these."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from voice_service.models.schemas import TranscriptionSegment

# The one requested inference device (both real loaders use it); backends report the ACTUAL
# placement through their ``device`` attribute.
CUDA_DEVICE = "cuda"


@dataclass(frozen=True)
class PhonemeToken:
    phonemes: str | None  # None = G2P could not pronounce this token (counted, never faked)
    whitespace: bool  # token is followed by whitespace in the source
    is_punctuation: bool  # every char of the token text is Unicode category P*


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    segments: list[TranscriptionSegment]


class DeviceBackend(Protocol):
    device: str  # the ACTUAL placement the loaded model reports


class TtsBackend(DeviceBackend, Protocol):
    sample_rate: int
    max_phonemes: int

    def phonemize(self, text: str) -> list[PhonemeToken]: ...

    def synthesize(self, phonemes: str) -> np.ndarray:
        """float32 mono samples; raises if ``len(phonemes) > max_phonemes``."""
        ...


class SttBackend(DeviceBackend, Protocol):
    supported_languages: frozenset[str]

    def transcribe(self, audio_path: Path, language: str | None) -> Transcript: ...
