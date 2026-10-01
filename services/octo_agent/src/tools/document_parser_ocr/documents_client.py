"""Thin typed HTTP client for the OCR document reader (``GET /ocr/documents/{doc_id}``).

The reader is the GPU-free ``ocr-documents`` process; it is the only server of that route and
the OCR store is the only copy of a finished ``OCRResponse`` (CLAUDE.md §6).
"""

from __future__ import annotations

import logging
import time

import requests
from pydantic import ValidationError
from shared_library.data_contracts import (
    OcrDocumentError,
    OcrDocumentErrorCode,
    OCRResponse,
    ocr_document_path,
)

from service_errors import OCRServiceError

logger = logging.getLogger(__name__)


class OcrDocumentsClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def fetch(self, doc_id: str) -> OCRResponse | None:
        """The stored document, or None iff the reader answered 404 with code NOT_FOUND for ``doc_id``.

        Any other 404 (e.g. a wrong base URL pointing at the GPU server, which has no such
        route), any non-200, a transport error or a contract violation raises OCRServiceError.
        """
        url = f"{self._base_url}{ocr_document_path(doc_id)}"
        started = time.monotonic()
        try:
            resp = requests.get(url, timeout=self._timeout_s)
        except requests.RequestException as exc:
            raise OCRServiceError(
                f"OCR document reader unreachable at {url} (timeout={self._timeout_s}s): {exc}",
                status_code=None,
            ) from exc
        logger.info(
            "OCR document fetch",
            extra={
                "doc_id": doc_id,
                "status": resp.status_code,
                "elapsed_s": time.monotonic() - started,
            },
        )

        error = None if resp.status_code == 200 else _error_body(resp)
        if (
            resp.status_code == 404
            and error is not None
            and error.code is OcrDocumentErrorCode.NOT_FOUND
            and error.doc_id == doc_id
        ):
            return None
        if (
            resp.status_code == 500
            and error is not None
            and error.code is OcrDocumentErrorCode.INTEGRITY
        ):
            raise OCRServiceError(
                f"stored OCR document for {doc_id!r} fails the OCRResponse contract "
                f"({error.code.value}); re-OCR it with: "
                f"make papers-ocr INPUT_DIR=<dir> REOCR={doc_id}",
                status_code=resp.status_code,
            )
        if resp.status_code != 200:
            raise OCRServiceError(
                f"OCR document reader error {resp.status_code} on GET {url}: {resp.text}",
                status_code=resp.status_code,
            )
        try:
            doc = OCRResponse.model_validate_json(resp.content)
        except ValidationError as exc:
            raise OCRServiceError(
                f"OCR document for {doc_id!r} violates the OCRResponse contract: {exc}",
                status_code=resp.status_code,
            ) from exc
        if doc.doc_id != doc_id:
            raise OCRServiceError(
                f"OCR document reader returned doc_id {doc.doc_id!r} for requested {doc_id!r}",
                status_code=resp.status_code,
            )
        return doc


def _error_body(resp: requests.Response) -> OcrDocumentError | None:
    """The reader's typed error body, or None iff the body is not that model (e.g. a wrong base URL)."""
    try:
        return OcrDocumentError.model_validate_json(resp.content)
    except ValidationError:
        return None
