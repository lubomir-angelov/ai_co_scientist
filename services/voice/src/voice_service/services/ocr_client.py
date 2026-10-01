"""Thin typed client for the OCR service's stored documents (Customer/Conformist of OCRResponse)."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import httpx
from pydantic import ValidationError
from shared_library.data_contracts import OCRResponse

from voice_service.core.errors import (
    OcrContractError,
    OcrDocumentNotFoundError,
    OcrServiceError,
    OcrTimeoutError,
)

logger = logging.getLogger(__name__)


class OcrDocumentClient:
    """No retries: prepare is user-initiated and idempotent, so the caller retries.

    ``http`` carries the base URL and the timeout; its lifecycle belongs to the app lifespan.
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch(self, doc_id: str) -> OCRResponse:
        path = f"/ocr/documents/{quote(doc_id, safe='')}"
        started = time.perf_counter()
        try:
            response = await self._http.get(path)
        except httpx.TimeoutException as exc:
            logger.error("OCR document fetch timed out", extra={"doc_id": doc_id, "path": path})
            raise OcrTimeoutError(f"OCR service timed out fetching {doc_id!r}") from exc
        except httpx.TransportError as exc:
            logger.error("OCR document fetch failed", extra={"doc_id": doc_id, "path": path})
            raise OcrServiceError(f"OCR service unreachable fetching {doc_id!r}: {exc}") from exc

        logger.info(
            "OCR document fetch",
            extra={
                "doc_id": doc_id,
                "path": path,
                "status": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        if response.status_code == 404:
            raise OcrDocumentNotFoundError(f"OCR service has no stored document for {doc_id!r}")
        if response.status_code != 200:
            raise OcrServiceError(f"OCR service returned status {response.status_code} for {doc_id!r}")
        try:
            document = OCRResponse.model_validate_json(response.content)
        except ValidationError as exc:
            raise OcrContractError(f"OCR document {doc_id!r} violates the OCRResponse contract: {exc}") from exc
        if document.doc_id != doc_id:
            raise OcrContractError(f"OCR returned doc_id {document.doc_id!r} for request {doc_id!r}")
        return document
