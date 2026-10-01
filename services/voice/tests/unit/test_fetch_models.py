"""Drift checks between model_pins.json, scripts/fetch_models.py and the runtime ModelManifest."""

import importlib.util
from pathlib import Path

import pytest

from voice_service.models.schemas import ModelManifest

SERVICE_DIR = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("fetch_models", SERVICE_DIR / "scripts" / "fetch_models.py")
assert _spec is not None and _spec.loader is not None
fetch_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_models)


def test_real_pins_file_is_valid() -> None:
    pins = fetch_models.load_pins(SERVICE_DIR / "model_pins.json")
    assert pins["stt"]["compute_type"] == "int8_float16"


def test_built_manifest_validates_against_the_runtime_schema(tmp_path: Path) -> None:
    pins = fetch_models.load_pins(SERVICE_DIR / "model_pins.json")
    manifest = ModelManifest.model_validate(fetch_models.build_manifest(pins, tmp_path))
    assert manifest.tts.revision == pins["tts"]["revision"]
    assert manifest.stt.compute_type == pins["stt"]["compute_type"]
    assert manifest.tts.model_dir == tmp_path / "kokoro" and manifest.stt.model_dir == tmp_path / "whisper"


def test_revision_must_be_an_exact_commit_sha(tmp_path: Path) -> None:
    path = tmp_path / "pins.json"
    path.write_text(
        '{"tts":{"repo_id":"a/b","revision":"main"},"stt":{"repo_id":"c/d","revision":"x","compute_type":"int8"},'
        '"g2p":{"spacy_model_wheel":"u","sha256":null}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="40-hex"):
        fetch_models.load_pins(path)


def test_shipped_pins_are_buildable_with_a_pinned_g2p_wheel() -> None:
    pins = fetch_models.load_pins(SERVICE_DIR / "model_pins.json")
    requirement = fetch_models.g2p_requirement(pins)
    assert requirement == f"{pins['g2p']['spacy_model_wheel']}#sha256={pins['g2p']['sha256']}"


def test_g2p_requirement_fails_fast_until_pinned() -> None:
    pins = {"g2p": {"spacy_model_wheel": "https://x/y.whl", "sha256": None}}
    with pytest.raises(RuntimeError, match="pin-g2p"):
        fetch_models.g2p_requirement(pins)
    pins["g2p"]["sha256"] = "a" * 64
    assert fetch_models.g2p_requirement(pins) == "https://x/y.whl#sha256=" + "a" * 64
    pins["g2p"]["sha256"] = "abc"
    with pytest.raises(ValueError, match="64 hex"):
        fetch_models.g2p_requirement(pins)
