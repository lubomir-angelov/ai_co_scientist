"""Build-time model tooling; never imported by the service. SSOT for model identity: model_pins.json.

fetch_models.py models   download the pinned Kokoro / faster-whisper revisions into /opt/models,
                         verify the required files and write the runtime manifest
fetch_models.py g2p      print the pip requirement (URL#sha256=...) for the pinned spaCy model wheel
fetch_models.py pin-g2p  developer command: download the spaCy wheel once and record its sha256
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

PINS_PATH = Path(__file__).resolve().parents[1] / "model_pins.json"
MODELS_ROOT = Path("/opt/models")
MANIFEST_PATH = MODELS_ROOT / "voice-models.json"

TTS_ALLOW_PATTERNS = ["config.json", "kokoro-v1_0.pth", "voices/*.pt"]
TTS_REQUIRED_FILES = ["config.json", "kokoro-v1_0.pth"]
STT_ALLOW_PATTERNS = ["config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"]
STT_REQUIRED_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.json"]
REVISION_LENGTH = 40  # an exact git commit sha, never a branch name
SHA256_HEX_LENGTH = 64


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ValueError(f"{PINS_PATH}: {where}.{key} is required")
    return mapping[key]


def load_pins(path: Path) -> dict[str, Any]:
    pins = json.loads(path.read_text(encoding="utf-8"))
    for section, fields in (
        ("tts", ("repo_id", "revision")),
        ("stt", ("repo_id", "revision", "compute_type")),
        ("g2p", ("spacy_model_wheel", "sha256")),
    ):
        block = _require(pins, section, "pins")
        for field in fields:
            _require(block, field, section)
    for section in ("tts", "stt"):
        revision = pins[section]["revision"]
        if len(revision) != REVISION_LENGTH or not all(c in "0123456789abcdef" for c in revision):
            raise ValueError(f"{path}: {section}.revision must be an exact 40-hex commit sha, got {revision!r}")
    return pins


def build_manifest(pins: dict[str, Any], models_root: Path) -> dict[str, Any]:
    """The runtime manifest: voice_service.models.schemas.ModelManifest (drift-checked by a unit test)."""
    return {
        "tts": {**pins["tts"], "model_dir": str(models_root / "kokoro")},
        "stt": {**pins["stt"], "model_dir": str(models_root / "whisper")},
    }


def _verify_files(directory: Path, required: list[str]) -> None:
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise RuntimeError(f"{directory}: missing required files after download: {missing}")


def fetch_models() -> None:
    pins = load_pins(PINS_PATH)
    tts_dir, stt_dir = MODELS_ROOT / "kokoro", MODELS_ROOT / "whisper"
    snapshot_download(
        pins["tts"]["repo_id"], revision=pins["tts"]["revision"], local_dir=tts_dir, allow_patterns=TTS_ALLOW_PATTERNS
    )
    snapshot_download(
        pins["stt"]["repo_id"], revision=pins["stt"]["revision"], local_dir=stt_dir, allow_patterns=STT_ALLOW_PATTERNS
    )
    _verify_files(tts_dir, TTS_REQUIRED_FILES)
    if not any((tts_dir / "voices").glob("*.pt")):
        raise RuntimeError(f"{tts_dir}/voices: no voice packs downloaded")
    _verify_files(stt_dir, STT_REQUIRED_FILES)
    MANIFEST_PATH.write_text(json.dumps(build_manifest(pins, MODELS_ROOT), indent=2), encoding="utf-8")
    print(f"wrote {MANIFEST_PATH}")


def g2p_requirement(pins: dict[str, Any]) -> str:
    digest = pins["g2p"]["sha256"]
    if digest is None:
        raise RuntimeError("g2p.sha256 is not pinned in model_pins.json: run `make -C services/voice pin-g2p` once")
    if len(digest) != SHA256_HEX_LENGTH:
        raise ValueError(f"g2p.sha256 must be {SHA256_HEX_LENGTH} hex characters, got {digest!r}")
    return f"{pins['g2p']['spacy_model_wheel']}#sha256={digest}"


def pin_g2p() -> None:
    pins = load_pins(PINS_PATH)
    digest = hashlib.sha256()
    with urllib.request.urlopen(pins["g2p"]["spacy_model_wheel"], timeout=120) as response:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
    pins["g2p"]["sha256"] = digest.hexdigest()
    PINS_PATH.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    print(f"pinned g2p.sha256 = {pins['g2p']['sha256']}")


def main(argv: list[str]) -> None:
    commands = {
        "models": fetch_models,
        "g2p": lambda: print(g2p_requirement(load_pins(PINS_PATH))),
        "pin-g2p": pin_g2p,
    }
    if len(argv) != 2 or argv[1] not in commands:
        raise SystemExit(f"usage: fetch_models.py {{{'|'.join(commands)}}}")
    commands[argv[1]]()


if __name__ == "__main__":
    main(sys.argv)
