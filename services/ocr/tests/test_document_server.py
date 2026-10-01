from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shared_library.data_contracts import (
    OCRBlock,
    OCRPage,
    OCRResponse,
    OCRSection,
    OcrDocumentError,
    OcrDocumentErrorCode,
)

from document_store import OcrDocumentReader, OcrDocumentWriter, document_path
from src import document_server


def _resp(doc_id: str = "doc-1") -> OCRResponse:
    return OCRResponse(
        doc_id=doc_id,
        sections=[OCRSection(name="Page 1", text="hello")],
        tables=[],
        pages=[
            OCRPage(
                page_number=1, blocks=[OCRBlock(ref="text", bbox=None, text="hello")]
            )
        ],
        metadata={"page_count": 1},
    )


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(document_server, "reader", OcrDocumentReader(tmp_path))
    return tmp_path


def _client() -> TestClient:
    return TestClient(document_server.app)


def test_get_document_roundtrip(root: Path) -> None:
    OcrDocumentWriter(root).save(_resp())
    resp = _client().get("/ocr/documents/doc-1")
    assert resp.status_code == 200
    assert resp.json() == _resp().model_dump(mode="json")


def test_get_document_404_when_absent(root: Path) -> None:
    resp = _client().get("/ocr/documents/absent")
    assert resp.status_code == 404
    assert resp.json() == OcrDocumentError(
        code=OcrDocumentErrorCode.NOT_FOUND, doc_id="absent"
    ).model_dump(mode="json")


def test_get_document_500_on_integrity_error(root: Path) -> None:
    document_path(root, "bad").write_text("{}", encoding="utf-8")
    resp = _client().get("/ocr/documents/bad")
    assert resp.status_code == 500
    assert resp.json() == OcrDocumentError(
        code=OcrDocumentErrorCode.INTEGRITY, doc_id="bad"
    ).model_dump(mode="json")


def test_illegal_doc_id_is_422(root: Path) -> None:
    assert _client().get("/ocr/documents/a%20b").status_code == 422


def test_healthz() -> None:
    assert _client().get("/healthz").json() == {
        "status": "ok",
        "service": "ocr-documents",
        "ready": True,
    }
