# services/ocr/tests/test_server.py
import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from document_store import OcrDocumentStore
from src import server
from src.server import app
from utils import ParsedBlock


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OcrDocumentStore:
    store = OcrDocumentStore(tmp_path)
    monkeypatch.setattr(server, "document_store", store)
    return store


def _client() -> TestClient:
    # Not used as a context manager, so the model-loading lifespan never runs.
    return TestClient(app)


_BLOCKS = [
    ParsedBlock(ref="title", bbox=(1, 2, 3, 4), text="A title"),
    ParsedBlock(ref="text", bbox=None, text="x" * 500),
]


@patch("src.server._infer_one_page", return_value=("hello from fake ocr", _BLOCKS))
@patch(
    "src.server._bytes_to_image_paths_async",
    new_callable=AsyncMock,
    return_value=(["/tmp/fake-page-1.jpg"], []),
)
def test_ocr_endpoint_returns_200(_mock_paths, _mock_infer):
    content_b64 = base64.b64encode(b"fake-image").decode()

    resp = _client().post("/ocr/extract", json={"doc_id": "doc-123", "content_b64": content_b64})

    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == "doc-123"
    assert [s["name"] for s in data["sections"]] == ["FullText", "Page 1"]
    assert data["sections"][1]["text"] == "hello from fake ocr"
    assert data["metadata"]["page_count"] == 1
    assert "layout_blocks" not in data["metadata"] and "pages" not in data["metadata"]
    assert data["pages"] == [
        {
            "page_number": 1,
            "blocks": [
                {"ref": "title", "bbox": [1, 2, 3, 4], "text": "A title"},
                {"ref": "text", "bbox": None, "text": "x" * 500},  # full text, never capped
            ],
        }
    ]
    # extract persisted the document before returning it
    stored = _client().get("/ocr/documents/doc-123")
    assert stored.status_code == 200
    assert stored.json() == data


def test_ocr_endpoint_rejects_bad_base64():
    resp = _client().post("/ocr/extract", json={"doc_id": "doc-123", "content_b64": "!!not base64!!"})
    assert resp.status_code == 400
    assert "Invalid base64" in resp.json()["detail"]


def test_healthz_reports_not_ready_before_model_load():
    body = _client().get("/healthz").json()
    assert body["service"] == "ocr"
    assert body["ready"] is False


def test_get_document_404_when_absent():
    resp = _client().get("/ocr/documents/absent")
    assert resp.status_code == 404
    assert resp.json() == {"code": "document_not_found", "doc_id": "absent"}


def test_get_document_500_on_integrity_error(_isolated_store: OcrDocumentStore):
    _isolated_store.path_for("bad").write_text("{}", encoding="utf-8")
    resp = _client().get("/ocr/documents/bad")
    assert resp.status_code == 500
    assert resp.json() == {"code": "document_integrity_error", "doc_id": "bad"}


@patch("src.server._infer_one_page", return_value=("t", _BLOCKS))
@patch(
    "src.server._bytes_to_image_paths_async",
    new_callable=AsyncMock,
    return_value=(["/tmp/fake-page-1.jpg"], []),
)
def test_extract_fails_when_store_write_fails(_mock_paths, _mock_infer, monkeypatch):
    failing = MagicMock()
    failing.save.side_effect = OSError("disk full")
    monkeypatch.setattr(server, "document_store", failing)
    content_b64 = base64.b64encode(b"fake-image").decode()

    resp = _client().post("/ocr/extract", json={"doc_id": "doc-1", "content_b64": content_b64})

    assert resp.status_code == 500
    assert resp.json() == {"code": "ocr_store_write_failed", "doc_id": "doc-1"}


def test_extract_rejects_illegal_doc_id():
    resp = _client().post("/ocr/extract", json={"doc_id": "a b", "content_b64": "eA=="})
    assert resp.status_code == 422


def test_infer_one_page_raises_on_non_str_result(tmp_path: Path, monkeypatch):
    fake_model = MagicMock()
    fake_model.infer.return_value = None
    monkeypatch.setattr(server, "model", fake_model)
    monkeypatch.setattr(server, "tokenizer", object())
    with pytest.raises(RuntimeError, match="expected str"):
        server._infer_one_page("/tmp/p.jpg", str(tmp_path / "out"))
