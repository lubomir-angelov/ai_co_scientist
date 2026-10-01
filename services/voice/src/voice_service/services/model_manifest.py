"""Loads and validates the manifest baked into the image at build time."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from voice_service.core.errors import ModelManifestError
from voice_service.models.schemas import ModelManifest


def load_manifest(path: Path) -> ModelManifest:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelManifestError(f"cannot read model manifest {path}: {exc}") from exc
    try:
        manifest = ModelManifest.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelManifestError(f"model manifest {path} is malformed: {exc}") from exc
    for label, directory in (("tts", manifest.tts.model_dir), ("stt", manifest.stt.model_dir)):
        if not directory.is_dir():
            raise ModelManifestError(f"model manifest {path}: {label} model_dir {directory} does not exist")
    return manifest
