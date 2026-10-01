"""VoiceConfig: the ONLY module that reads the process environment (enforced by a fitness guard).

Every variable is required. An unset or empty value raises ConfigError naming the variable;
local-dev defaults live in compose.yaml, never in Python.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from voice_service.core.errors import ConfigError

TTS_SPEED_MIN = 0.5
TTS_SPEED_MAX = 2.0


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None or not value.strip():
        raise ConfigError(f"{name} is required and must be non-empty")
    return value.strip()


def _parse(name: str, raw: str, cast: type[int] | type[float]) -> int | float:
    try:
        return cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid {cast.__name__}") from exc


@dataclass(frozen=True)
class VoiceConfig:
    ocr_base_url: str
    ocr_timeout_seconds: float
    data_dir: Path
    models_manifest: Path
    tts_voice: str
    tts_speed: float
    max_active_streams: int
    max_pending_transcriptions: int
    render_queue_max: int
    log_level: str

    @classmethod
    def from_env(cls) -> VoiceConfig:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, env: Mapping[str, str]) -> VoiceConfig:
        ocr_base_url = _required(env, "VOICE_OCR_BASE_URL")
        if not ocr_base_url.startswith(("http://", "https://")):
            raise ConfigError(f"VOICE_OCR_BASE_URL={ocr_base_url!r} must start with http:// or https://")

        ocr_timeout = float(_parse("VOICE_OCR_TIMEOUT_SECONDS", _required(env, "VOICE_OCR_TIMEOUT_SECONDS"), float))
        if ocr_timeout <= 0:
            raise ConfigError(f"VOICE_OCR_TIMEOUT_SECONDS={ocr_timeout} must be > 0")

        data_dir = Path(_required(env, "VOICE_DATA_DIR"))
        if not data_dir.is_dir():
            raise ConfigError(f"VOICE_DATA_DIR={str(data_dir)!r} does not exist or is not a directory")
        if not os.access(data_dir, os.W_OK):
            raise ConfigError(f"VOICE_DATA_DIR={str(data_dir)!r} is not writable")

        models_manifest = Path(_required(env, "VOICE_MODELS_MANIFEST"))
        if not models_manifest.is_file():
            raise ConfigError(f"VOICE_MODELS_MANIFEST={str(models_manifest)!r} does not exist")

        speed = float(_parse("VOICE_TTS_SPEED", _required(env, "VOICE_TTS_SPEED"), float))
        if not TTS_SPEED_MIN <= speed <= TTS_SPEED_MAX:
            raise ConfigError(f"VOICE_TTS_SPEED={speed} must be within [{TTS_SPEED_MIN}, {TTS_SPEED_MAX}]")

        log_level = _required(env, "LOG_LEVEL")
        level_names = {name for name in logging.getLevelNamesMapping() if name != "NOTSET"}
        if log_level not in level_names:
            raise ConfigError(f"LOG_LEVEL={log_level!r} must be one of {sorted(level_names)}")

        return cls(
            ocr_base_url=ocr_base_url.rstrip("/"),
            ocr_timeout_seconds=ocr_timeout,
            data_dir=data_dir,
            models_manifest=models_manifest,
            tts_voice=_required(env, "VOICE_TTS_VOICE"),
            tts_speed=speed,
            max_active_streams=_positive_int(env, "VOICE_MAX_ACTIVE_STREAMS"),
            max_pending_transcriptions=_positive_int(env, "VOICE_MAX_PENDING_TRANSCRIPTIONS"),
            render_queue_max=_positive_int(env, "VOICE_RENDER_QUEUE_MAX"),
            log_level=log_level,
        )


def _positive_int(env: Mapping[str, str], name: str) -> int:
    value = int(_parse(name, _required(env, name), int))
    if value < 1:
        raise ConfigError(f"{name}={value} must be >= 1")
    return value
