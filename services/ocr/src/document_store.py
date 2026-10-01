"""OCR-owned persistent store of finished OCRResponse documents, addressed by doc id.

Repository pattern: the OCR service owns its artifacts (AGENTS: "keep OCR artifacts inside
OCR-owned storage"); other services read them through ``GET /ocr/documents/{doc_id}``.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from pydantic import ValidationError
from shared_library.atomic_files import atomic_replace
from shared_library.data_contracts import OCRResponse

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    """No OCRResponse is stored for the requested doc id."""

    def __init__(self, doc_id: str) -> None:
        super().__init__(f"no stored OCR document for doc_id {doc_id!r}")
        self.doc_id = doc_id


class DocumentIntegrityError(Exception):
    """The stored file does not hold a valid OCRResponse for the requested doc id."""


class OcrDocumentStore:
    def __init__(self, root: Path) -> None:
        if not root.is_dir():
            raise RuntimeError(f"OCR documents dir {str(root)!r} does not exist or is not a directory")
        if not os.access(root, os.W_OK):
            raise RuntimeError(f"OCR documents dir {str(root)!r} is not writable")
        self._root = root

    def path_for(self, doc_id: str) -> Path:
        """The single deriver of the on-disk layout: full sha256 hex of the doc id."""
        return self._root / f"{hashlib.sha256(doc_id.encode('utf-8')).hexdigest()}.json"

    def save(self, resp: OCRResponse) -> None:
        """Atomically persist ``resp``; a re-OCR of the same doc id replaces the old document."""
        path = self.path_for(resp.doc_id)
        replaced = path.exists()
        with atomic_replace(path) as tmp:
            tmp.write_text(resp.model_dump_json(), encoding="utf-8")
        logger.info(
            "stored OCR document",
            extra={"doc_id": resp.doc_id, "replaced_existing": replaced, "pages": len(resp.pages)},
        )

    def load(self, doc_id: str) -> OCRResponse:
        path = self.path_for(doc_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise DocumentNotFoundError(doc_id) from None
        try:
            resp = OCRResponse.model_validate_json(raw)
        except ValidationError as exc:
            raise DocumentIntegrityError(
                f"stored OCR document for doc_id {doc_id!r} violates the OCRResponse contract: {exc}"
            ) from exc
        if resp.doc_id != doc_id:
            raise DocumentIntegrityError(
                f"stored OCR document at {path.name} has doc_id {resp.doc_id!r}, requested {doc_id!r}"
            )
        return resp
