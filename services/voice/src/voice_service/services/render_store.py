"""RenderStore: the single owner of the on-disk layout (CLAUDE.md §6) and of every write.

VOICE_DATA_DIR/papers/<doc_key>/script.json
VOICE_DATA_DIR/papers/<doc_key>/renders/<render_key>/manifest.json
VOICE_DATA_DIR/papers/<doc_key>/renders/<render_key>/section-0003.mp3

All writes are atomic, through shared_library.atomic_files.atomic_replace (never a direct rename).
"""

from __future__ import annotations

import hashlib
from contextlib import AbstractContextManager
from pathlib import Path

from pydantic import ValidationError
from shared_library.atomic_files import atomic_replace

from voice_service.core.errors import ScriptNotPreparedError, StoreIntegrityError
from voice_service.models.schemas import (
    ModelIdentity,
    PaperScript,
    RenderManifest,
    SectionRenderRecord,
)
from voice_service.services.audio_encode import MP3_ENCODING_PARAMS
from voice_service.services.canonical import canonical_sha256

_SCRIPT_FILE = "script.json"
_MANIFEST_FILE = "manifest.json"


def doc_key(doc_id: str) -> str:
    return hashlib.sha256(doc_id.encode("utf-8")).hexdigest()


def section_file_name(index: int) -> str:
    return f"section-{index:04d}.mp3"


def render_key(script_sha256: str, tts_model: ModelIdentity, voice: str, speed: float, sample_rate: int) -> str:
    """Independent of the section selection: sections are individually addressable files."""
    return canonical_sha256(
        {
            "script_sha256": script_sha256,
            "tts": tts_model.model_dump(mode="json"),
            "voice": voice,
            "speed": speed,
            "sample_rate": sample_rate,
            "mp3": MP3_ENCODING_PARAMS,
        }
    )


def file_digest(path: Path) -> tuple[str, int]:
    """(sha256 hex, size in bytes) of ``path`` with bounded memory; the one hashing path."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest(), path.stat().st_size


class RenderStore:
    def __init__(self, root: Path) -> None:
        self._papers = root / "papers"

    def _doc_dir(self, doc_id: str) -> Path:
        return self._papers / doc_key(doc_id)

    def _render_dir(self, doc_id: str, key: str) -> Path:
        return self._doc_dir(doc_id) / "renders" / key

    def section_path(self, doc_id: str, key: str, index: int) -> Path:
        return self._render_dir(doc_id, key) / section_file_name(index)

    # ---- scripts --------------------------------------------------------------------------

    def save_script(self, script: PaperScript) -> None:
        with atomic_replace(self._doc_dir(script.doc_id) / _SCRIPT_FILE) as tmp:
            tmp.write_text(script.model_dump_json(), encoding="utf-8")

    def find_script(self, doc_id: str) -> PaperScript | None:
        path = self._doc_dir(doc_id) / _SCRIPT_FILE
        if not path.is_file():
            return None
        script = self._read_script(path)
        self._check_owner(path, script)
        return script

    def load_script(self, doc_id: str) -> PaperScript:
        script = self.find_script(doc_id)
        if script is None:
            raise ScriptNotPreparedError(f"no script prepared for doc_id {doc_id!r}; POST /v1/papers/{{doc_id}}/script first")
        return script

    def list_scripts(self) -> list[PaperScript]:
        if not self._papers.is_dir():
            return []
        scripts = []
        for path in sorted(self._papers.glob(f"*/{_SCRIPT_FILE}")):
            script = self._read_script(path)
            self._check_owner(path, script)
            scripts.append(script)
        return scripts

    @staticmethod
    def _check_owner(path: Path, script: PaperScript) -> None:
        """A script file must live in the directory derived from its own doc_id."""
        if doc_key(script.doc_id) != path.parent.name:
            raise StoreIntegrityError(
                f"{path} holds a script for doc_id {script.doc_id!r}, which belongs in "
                f"directory {doc_key(script.doc_id)}, not {path.parent.name}"
            )

    @staticmethod
    def _read_script(path: Path) -> PaperScript:
        try:
            return PaperScript.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreIntegrityError(f"{path} is not a valid PaperScript: {exc}") from exc

    # ---- renders --------------------------------------------------------------------------

    def find_manifest(self, doc_id: str, key: str) -> RenderManifest | None:
        path = self._render_dir(doc_id, key) / _MANIFEST_FILE
        if not path.is_file():
            return None
        try:
            manifest = RenderManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreIntegrityError(f"{path} is not a valid RenderManifest: {exc}") from exc
        if manifest.doc_id != doc_id or manifest.render_key != key:
            raise StoreIntegrityError(
                f"{path} holds doc_id {manifest.doc_id!r} / render_key {manifest.render_key!r}, "
                f"expected {doc_id!r} / {key!r}"
            )
        return manifest

    def save_manifest(self, manifest: RenderManifest) -> None:
        path = self._render_dir(manifest.doc_id, manifest.render_key) / _MANIFEST_FILE
        with atomic_replace(path) as tmp:
            tmp.write_text(manifest.model_dump_json(), encoding="utf-8")

    def section_output(self, doc_id: str, key: str, index: int) -> AbstractContextManager[Path]:
        """The only writer of section files: yields a temp path that is published atomically
        as the section file on clean exit and removed on error."""
        return atomic_replace(self.section_path(doc_id, key, index))

    def verify_rendered(self, doc_id: str, key: str, record: SectionRenderRecord) -> Path:
        """A 'rendered' record must be backed by its file with the recorded sha256."""
        path = self.section_path(doc_id, key, record.index)
        if not path.is_file():
            raise StoreIntegrityError(f"manifest says section {record.index} is rendered but {path} is missing")
        actual, _ = file_digest(path)
        if actual != record.sha256:
            raise StoreIntegrityError(
                f"{path} sha256 {actual} does not match the manifest's {record.sha256}"
            )
        return path
