"""KokoroTts: the real TTS backend. Imports torch/kokoro/misaki at module level; GPU image only.

We never call ``KPipeline.__call__`` on paper text: its internal chunker truncates over-long
phoneme strings with only a warning. Windowing is owned by phoneme_windows.pack_phoneme_windows.
"""

from __future__ import annotations

import unicodedata

import numpy as np
import torch
from kokoro import KModel, KPipeline
from misaki import en as misaki_en

from voice_service.core.errors import ModelLoadError
from voice_service.models.schemas import ModelManifest
from voice_service.services.backends import CUDA_DEVICE, PhonemeToken
from voice_service.services.phoneme_windows import KOKORO_MAX_PHONEMES

KOKORO_SAMPLE_RATE = 24000
_WEIGHTS_FILE = "kokoro-v1_0.pth"
_CONFIG_FILE = "config.json"
_VOICES_DIR = "voices"


class KokoroTts:
    sample_rate = KOKORO_SAMPLE_RATE
    max_phonemes = KOKORO_MAX_PHONEMES

    def __init__(self, model: KModel, pipeline: KPipeline, voice_pack: torch.Tensor, speed: float) -> None:
        self._model = model
        self._pipeline = pipeline
        self._voice_pack = voice_pack
        self._speed = speed
        self.device = str(next(model.parameters()).device)

    @classmethod
    def load(cls, manifest: ModelManifest, voice_id: str, speed: float) -> KokoroTts:
        if not torch.cuda.is_available():
            raise ModelLoadError("CUDA requested but unavailable")
        model_dir = manifest.tts.model_dir
        voice_path = model_dir / _VOICES_DIR / f"{voice_id}.pt"
        for required in (model_dir / _WEIGHTS_FILE, model_dir / _CONFIG_FILE, voice_path):
            if not required.is_file():
                raise ModelLoadError(f"Kokoro artifact missing: {required}")

        # Paths (not names) are passed so neither KModel nor KPipeline can reach the hub.
        model = KModel(
            repo_id=manifest.tts.repo_id,
            config=str(model_dir / _CONFIG_FILE),
            model=str(model_dir / _WEIGHTS_FILE),
        )
        model = model.to(CUDA_DEVICE).eval()
        pipeline = KPipeline(lang_code=voice_id[0], repo_id=manifest.tts.repo_id, model=model)
        if not isinstance(pipeline.g2p, misaki_en.G2P):
            raise ModelLoadError(f"voice {voice_id!r} does not select the English G2P this service bakes")
        if pipeline.g2p.fallback is None:
            raise ModelLoadError("misaki espeak fallback is not active: OOV tokens would silently vanish")
        voice_pack = torch.load(voice_path, weights_only=True).to(CUDA_DEVICE)
        return cls(model, pipeline, voice_pack, speed)

    def phonemize(self, text: str) -> list[PhonemeToken]:
        _, tokens = self._pipeline.g2p(text)
        return [
            PhonemeToken(
                phonemes=token.phonemes,
                whitespace=bool(token.whitespace),
                is_punctuation=bool(token.text) and all(unicodedata.category(c)[0] == "P" for c in token.text),
            )
            for token in tokens
        ]

    def synthesize(self, phonemes: str) -> np.ndarray:
        if len(phonemes) > self.max_phonemes:
            raise ValueError(f"{len(phonemes)} phonemes exceed the Kokoro window of {self.max_phonemes}")
        with torch.inference_mode():
            audio = self._model(phonemes, self._voice_pack[len(phonemes) - 1], self._speed)
        return audio.cpu().numpy().astype(np.float32)
