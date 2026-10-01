"""WhisperStt: the real STT backend (faster-whisper on CUDA). GPU image only."""

from __future__ import annotations

from pathlib import Path

import av
import torch
from faster_whisper import WhisperModel

from voice_service.core.errors import AudioDecodeError, ModelLoadError
from voice_service.models.schemas import ModelManifest, TranscriptionSegment
from voice_service.services.backends import CUDA_DEVICE, Transcript

WHISPER_BEAM_SIZE = 5
WHISPER_VAD_FILTER = True


class WhisperStt:
    def __init__(self, model: WhisperModel) -> None:
        self._model = model
        self.device = model.model.device
        self.supported_languages = frozenset(model.supported_languages)

    @classmethod
    def load(cls, manifest: ModelManifest) -> WhisperStt:
        if not torch.cuda.is_available():
            raise ModelLoadError("CUDA requested but unavailable")
        model = WhisperModel(
            str(manifest.stt.model_dir), device=CUDA_DEVICE, compute_type=manifest.stt.compute_type
        )
        return cls(model)

    def transcribe(self, audio_path: Path, language: str | None) -> Transcript:
        try:
            segments, info = self._model.transcribe(
                str(audio_path),
                language=language,
                beam_size=WHISPER_BEAM_SIZE,
                vad_filter=WHISPER_VAD_FILTER,
            )
            consumed = [
                TranscriptionSegment(start=seg.start, end=seg.end, text=seg.text) for seg in segments
            ]
        except av.error.FFmpegError as exc:
            raise AudioDecodeError(f"audio could not be decoded: {exc}") from exc
        return Transcript(
            text="".join(seg.text for seg in consumed).strip(),
            language=info.language,
            language_probability=info.language_probability,
            duration_seconds=info.duration,
            segments=consumed,
        )
