from pathlib import Path

import pytest
from conftest import make_config

from voice_service.core.config import VoiceConfig
from voice_service.core.errors import ConfigError

REQUIRED = [
    "VOICE_OCR_DOCUMENTS_BASE_URL",
    "VOICE_OCR_TIMEOUT_SECONDS",
    "VOICE_DATA_DIR",
    "VOICE_MODELS_MANIFEST",
    "VOICE_TTS_VOICE",
    "VOICE_TTS_SPEED",
    "VOICE_MAX_ACTIVE_STREAMS",
    "VOICE_MAX_PENDING_TRANSCRIPTIONS",
    "VOICE_RENDER_QUEUE_MAX",
    "LOG_LEVEL",
]


def _env(tmp_path: Path) -> dict[str, str]:
    data = tmp_path / "data"
    data.mkdir()
    manifest = tmp_path / "m.json"
    manifest.write_text("{}")
    return {
        "VOICE_OCR_DOCUMENTS_BASE_URL": "http://ocr-documents:8008/",
        "VOICE_OCR_TIMEOUT_SECONDS": "60",
        "VOICE_DATA_DIR": str(data),
        "VOICE_MODELS_MANIFEST": str(manifest),
        "VOICE_TTS_VOICE": "af_heart",
        "VOICE_TTS_SPEED": "1.0",
        "VOICE_MAX_ACTIVE_STREAMS": "2",
        "VOICE_MAX_PENDING_TRANSCRIPTIONS": "2",
        "VOICE_RENDER_QUEUE_MAX": "16",
        "LOG_LEVEL": "INFO",
    }


def test_valid_env_parses(tmp_path: Path) -> None:
    cfg = VoiceConfig.from_mapping(_env(tmp_path))
    assert cfg.ocr_documents_base_url == "http://ocr-documents:8008"
    assert cfg.tts_speed == 1.0 and cfg.render_queue_max == 16


@pytest.mark.parametrize("name", REQUIRED)
@pytest.mark.parametrize("blank", [None, "", "  "])
def test_missing_or_empty_var_raises_and_names_it(tmp_path: Path, name: str, blank: str | None) -> None:
    env = _env(tmp_path)
    if blank is None:
        del env[name]
    else:
        env[name] = blank
    with pytest.raises(ConfigError, match=name):
        VoiceConfig.from_mapping(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VOICE_OCR_DOCUMENTS_BASE_URL", "ocr-documents:8008"),
        ("VOICE_OCR_TIMEOUT_SECONDS", "0"),
        ("VOICE_OCR_TIMEOUT_SECONDS", "abc"),
        ("VOICE_TTS_SPEED", "0.4"),
        ("VOICE_TTS_SPEED", "2.1"),
        ("VOICE_MAX_ACTIVE_STREAMS", "0"),
        ("VOICE_RENDER_QUEUE_MAX", "1.5"),
        ("LOG_LEVEL", "LOUD"),
        ("LOG_LEVEL", "NOTSET"),
    ],
)
def test_out_of_range_values_raise(tmp_path: Path, name: str, value: str) -> None:
    env = _env(tmp_path)
    env[name] = value
    with pytest.raises(ConfigError, match=name):
        VoiceConfig.from_mapping(env)


def test_missing_data_dir_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    env["VOICE_DATA_DIR"] = str(tmp_path / "absent")
    with pytest.raises(ConfigError, match="VOICE_DATA_DIR"):
        VoiceConfig.from_mapping(env)


def test_unwritable_data_dir_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _env(tmp_path)
    monkeypatch.setattr("voice_service.core.config.os.access", lambda *_: False)
    with pytest.raises(ConfigError, match="not writable"):
        VoiceConfig.from_mapping(env)


def test_make_config_helper_is_valid(tmp_path: Path) -> None:
    assert make_config(tmp_path).tts_voice == "af_heart"
