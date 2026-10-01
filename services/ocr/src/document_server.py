"""GPU-free reader app: the only process that serves ``GET /ocr/documents/{doc_id}``.

Runs from the same image as the GPU ``ocr`` server but mounts the document volume read-only and
loads no model, so it stays up while the GPU is tenanted by the LLM. It must import nothing from
``server`` or the GPU stack (pinned by ``tests/test_document_server_is_gpu_free.py``).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from shared_library.data_contracts import (
    OCR_DOCUMENTS_ROUTE,
    DocId,
    OCRResponse,
    OcrDocumentError,
    OcrDocumentErrorCode,
)

from document_store import (
    DocumentIntegrityError,
    DocumentNotFoundError,
    OcrDocumentReader,
    documents_dir_from_env,
)

logger = logging.getLogger(__name__)

# Built at import so a missing/unset documents dir fails the service at startup.
reader = OcrDocumentReader(documents_dir_from_env())

app = FastAPI(title="OCR document reader", version="0.1.0")


@app.get("/healthz")
async def healthz():
    # Honestly ready: this module only imports after the reader validated its root.
    return {"status": "ok", "service": "ocr-documents", "ready": True}


def _error(status: int, code: OcrDocumentErrorCode, doc_id: str) -> JSONResponse:
    body = OcrDocumentError(code=code, doc_id=doc_id)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.get(OCR_DOCUMENTS_ROUTE, response_model=OCRResponse)
async def get_document(doc_id: DocId):
    try:
        return reader.load(doc_id)
    except DocumentNotFoundError:
        return _error(404, OcrDocumentErrorCode.NOT_FOUND, doc_id)
    except DocumentIntegrityError:
        logger.exception(
            "stored OCR document failed integrity check", extra={"doc_id": doc_id}
        )
        return _error(500, OcrDocumentErrorCode.INTEGRITY, doc_id)
