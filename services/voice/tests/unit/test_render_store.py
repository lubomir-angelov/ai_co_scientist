import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import load_ocr_fixture
from pydantic import ValidationError

from voice_service.core.errors import ScriptNotPreparedError, StoreIntegrityError
from voice_service.models.schemas import ModelIdentity, RenderManifest, SectionRenderRecord
from voice_service.services.render_store import RenderStore, doc_key, file_digest, render_key, section_file_name
from voice_service.services.script_builder import build_script

TTS = ModelIdentity(repo_id="r", revision="1")
KEY = "a" * 64
OTHER_KEY = "b" * 64
SCRIPT_SHA = "c" * 64


def write_section(store: RenderStore, doc_id: str, key: str, index: int, data: bytes) -> None:
    with store.section_output(doc_id, key, index) as tmp:
        tmp.write_bytes(data)


def rendered(index: int, data: bytes) -> SectionRenderRecord:
    return SectionRenderRecord(
        index=index, status="rendered", file_name=section_file_name(index),
        sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), audio_seconds=1.0, windows=1,
        unspoken_tokens=0, synth_seconds=0.1, phonemize_seconds=0.01, error=None, finished_at=datetime.now(UTC),
    )


def test_doc_key_is_full_sha256_and_deterministic() -> None:
    assert doc_key("a") == doc_key("a") != doc_key("b")
    assert len(doc_key("a")) == 64


def test_render_key_changes_when_any_input_changes() -> None:
    base = render_key("s", TTS, "af_heart", 1.0, 24000)
    assert base == render_key("s", TTS, "af_heart", 1.0, 24000)
    assert base != render_key("s2", TTS, "af_heart", 1.0, 24000)
    assert base != render_key("s", ModelIdentity(repo_id="r", revision="2"), "af_heart", 1.0, 24000)
    assert base != render_key("s", TTS, "am_adam", 1.0, 24000)
    assert base != render_key("s", TTS, "af_heart", 1.1, 24000)
    assert base != render_key("s", TTS, "af_heart", 1.0, 16000)


def test_section_file_name_is_zero_padded() -> None:
    assert section_file_name(3) == "section-0003.mp3"


def test_script_roundtrip_and_atomic_write(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    script = build_script(load_ocr_fixture(), datetime.now(UTC))
    store.save_script(script)
    assert store.load_script("paper-1") == script
    assert [p.name for p in tmp_path.rglob("*.tmp")] == []
    assert store.list_scripts() == [script]


def test_missing_script_raises_not_prepared(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    assert store.find_script("nope") is None and store.list_scripts() == []
    with pytest.raises(ScriptNotPreparedError):
        store.load_script("nope")


def test_script_doc_id_mismatch_raises_integrity(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    script = build_script(load_ocr_fixture(), datetime.now(UTC))
    store.save_script(script)
    (tmp_path / "papers" / doc_key("paper-1") / "script.json").rename(
        tmp_path / "papers" / doc_key("paper-1") / "other.json"
    )
    other_dir = tmp_path / "papers" / doc_key("someone-else")
    other_dir.mkdir()
    (other_dir / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    with pytest.raises(StoreIntegrityError, match="belongs in directory"):
        store.find_script("someone-else")


def test_corrupt_script_raises_integrity(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    path = tmp_path / "papers" / doc_key("d")
    path.mkdir(parents=True)
    (path / "script.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StoreIntegrityError):
        store.find_script("d")


def test_manifest_roundtrip_and_verify(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    data = b"mp3-bytes"
    record = rendered(3, data)
    manifest = RenderManifest(
        doc_id="d", render_key=KEY, script_sha256=SCRIPT_SHA, voice="v", speed=1.0, tts_model=TTS, sections={3: record}
    )
    write_section(store, "d", KEY, 3, data)
    store.save_manifest(manifest)

    assert store.find_manifest("d", KEY) == manifest
    assert store.verify_rendered("d", KEY, record) == store.section_path("d", KEY, 3)
    assert store.find_manifest("d", OTHER_KEY) is None


def test_verify_detects_missing_and_tampered_files(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    record = rendered(1, b"orig")
    with pytest.raises(StoreIntegrityError, match="missing"):
        store.verify_rendered("d", KEY, record)
    write_section(store, "d", KEY, 1, b"tampered")
    with pytest.raises(StoreIntegrityError, match="does not match"):
        store.verify_rendered("d", KEY, record)


def test_manifest_validator_rejects_inconsistent_records() -> None:
    base = dict(
        index=0, file_name=None, sha256=None, bytes=None, audio_seconds=None, windows=None,
        unspoken_tokens=None, synth_seconds=None, phonemize_seconds=None, error=None, finished_at=datetime.now(UTC),
    )
    with pytest.raises(ValidationError):
        SectionRenderRecord(status="rendered", **base)  # rendered with nothing set
    with pytest.raises(ValidationError):
        SectionRenderRecord(status="failed", **base)  # failed without an error
    with pytest.raises(ValidationError):
        SectionRenderRecord(status="failed", **{**base, "error": "x", "windows": 1})
    assert SectionRenderRecord(status="failed", **{**base, "error": "boom"}).error == "boom"


def test_list_scripts_rejects_a_script_stored_under_the_wrong_directory(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    script = build_script(load_ocr_fixture(), datetime.now(UTC))
    wrong = tmp_path / "papers" / doc_key("someone-else")
    wrong.mkdir(parents=True)
    (wrong / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    with pytest.raises(StoreIntegrityError, match="belongs in directory"):
        store.list_scripts()


def test_file_digest_matches_sha256_of_the_bytes(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"x" * 3_000_000)
    assert file_digest(path) == (hashlib.sha256(b"x" * 3_000_000).hexdigest(), 3_000_000)


def test_failed_section_write_leaves_no_file_or_tmp(tmp_path: Path) -> None:
    store = RenderStore(tmp_path)
    with pytest.raises(RuntimeError, match="boom"), store.section_output("d", KEY, 1) as tmp:
        tmp.write_bytes(b"partial")
        raise RuntimeError("boom")
    assert not store.section_path("d", KEY, 1).exists()
    assert list(tmp_path.rglob("*.tmp")) == []
