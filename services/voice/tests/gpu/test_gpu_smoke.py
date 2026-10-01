"""GPU smoke test: real models, VRAM budget, TTS -> STT roundtrip. Run inside the voice container:
`make -C services/voice test-gpu`. Imports of the real backends are inside the test so collection
works in the light venv."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytestmark = pytest.mark.gpu

VRAM_BUDGET_MIB = 3000
SENTENCE = "The quick brown fox jumps over the lazy dog."
STT_CLIP_SECONDS = 60


def _process_vram_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows = [line.split(",") for line in out.strip().splitlines()]
    return sum(int(mem) for pid, mem in rows if int(pid) == os.getpid())


def test_roundtrip_and_vram_budget() -> None:
    from voice_service.core.config import VoiceConfig
    from voice_service.services.model_manifest import load_manifest
    from voice_service.services.phoneme_windows import pack_phoneme_windows
    from voice_service.services.stt_whisper import WhisperStt
    from voice_service.services.tts_kokoro import KokoroTts

    config = VoiceConfig.from_env()
    manifest = load_manifest(config.models_manifest)
    tts = KokoroTts.load(manifest, config.tts_voice, config.tts_speed)
    stt = WhisperStt.load(manifest)

    windows = pack_phoneme_windows(tts.phonemize(SENTENCE), tts.max_phonemes)
    started = time.perf_counter()
    pcm = np.concatenate([tts.synthesize(w.phonemes) for w in windows if w.phonemes.strip()])
    synth_seconds = time.perf_counter() - started
    audio_seconds = len(pcm) / tts.sample_rate
    print(json.dumps({"tts_realtime_factor": audio_seconds / synth_seconds}))

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "roundtrip.wav"
        sf.write(wav, pcm, tts.sample_rate)
        transcript = stt.transcribe(wav, None)
        assert transcript.text.strip() != "" and transcript.language != ""

        clip = np.tile(pcm, int(np.ceil(STT_CLIP_SECONDS / audio_seconds)))[: STT_CLIP_SECONDS * tts.sample_rate]
        long_wav = Path(tmp) / "long.wav"
        sf.write(long_wav, clip, tts.sample_rate)
        started = time.perf_counter()
        stt.transcribe(long_wav, None)
        print(json.dumps({"stt_seconds_for_60s": time.perf_counter() - started}))

    assert _process_vram_mib() <= VRAM_BUDGET_MIB
