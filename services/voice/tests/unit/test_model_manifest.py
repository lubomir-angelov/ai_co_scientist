import json
from pathlib import Path

import pytest

from voice_service.core.errors import ModelManifestError
from voice_service.services.model_manifest import load_manifest


def write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "m.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


def valid(tmp_path: Path) -> dict:
    (tmp_path / "k").mkdir()
    (tmp_path / "w").mkdir()
    return {
        "tts": {"repo_id": "a/b", "revision": "r1", "model_dir": str(tmp_path / "k")},
        "stt": {"repo_id": "c/d", "revision": "r2", "model_dir": str(tmp_path / "w"), "compute_type": "int8_float16"},
    }


def test_valid_manifest_loads(tmp_path: Path) -> None:
    manifest = load_manifest(write(tmp_path, valid(tmp_path)))
    assert manifest.tts.identity().revision == "r1" and manifest.stt.compute_type == "int8_float16"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelManifestError, match="cannot read"):
        load_manifest(tmp_path / "absent.json")


def test_malformed_json_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelManifestError, match="malformed"):
        load_manifest(write(tmp_path, "{not json"))


def test_missing_field_raises(tmp_path: Path) -> None:
    payload = valid(tmp_path)
    del payload["stt"]["compute_type"]
    with pytest.raises(ModelManifestError, match="malformed"):
        load_manifest(write(tmp_path, payload))


def test_missing_model_dir_raises(tmp_path: Path) -> None:
    payload = valid(tmp_path)
    payload["tts"]["model_dir"] = str(tmp_path / "absent")
    with pytest.raises(ModelManifestError, match="tts model_dir"):
        load_manifest(write(tmp_path, payload))
