"""ASGI entry point: imports the REAL GPU backends and wires them into create_app.

Unit tests never import this module (torch/kokoro/faster-whisper are GPU-image only).
"""

from __future__ import annotations

import os

from voice_service.app import create_app
from voice_service.core.config import VoiceConfig
from voice_service.core.logging import configure_logging
from voice_service.services.model_manifest import load_manifest
from voice_service.services.stt_whisper import WhisperStt
from voice_service.services.tts_kokoro import KokoroTts

config = VoiceConfig.from_env()
configure_logging(config.log_level)
manifest = load_manifest(config.models_manifest)

app = create_app(
    config=config,
    manifest=manifest,
    tts_loader=lambda: KokoroTts.load(manifest, config.tts_voice, config.tts_speed),
    stt_loader=lambda: WhisperStt.load(manifest),
    exit_process=os._exit,
    ocr_transport=None,
)
