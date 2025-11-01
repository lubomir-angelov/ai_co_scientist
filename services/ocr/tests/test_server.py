# services/ocr/tests/test_server.py
import base64
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.server import app


class FakePipeline:
    def process_bytes(self, data: bytes, doc_id: str):
        return {
            "sections": [{"name": "FullText", "text": "hello from fake ocr"}],
            "tables": [],
            "metadata": {"doc_id": doc_id},
        }


def _fake_load_deepseek_ocr():
    return FakePipeline()


@patch("src.server.load_model")  # prevent real startup load
def test_ocr_endpoint_returns_200(mock_startup):
    client = TestClient(app)

    # fake base64 image
    content_b64 = base64.b64encode(b"fake-image").decode()

    # manually inject fake pipeline (startup was patched)
    app.dependency_overrides = {}
    # server.py keeps global ocr_pipeline; set it:
    import src.server as server  # noqa

    server.ocr_pipeline = FakePipeline()

    resp = client.post(
        "/ocr/extract",
        json={"doc_id": "doc-123", "content_b64": content_b64},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == "doc-123"
    assert len(data["sections"]) == 1
    assert data["sections"][0]["text"] == "hello from fake ocr"


@patch("src.server.load_model")
def test_ocr_endpoint_rejects_bad_base64(mock_startup):
    client = TestClient(app)

    resp = client.post(
        "/ocr/extract",
        json={"doc_id": "doc-123", "content_b64": "!!not base64!!"},
    )
    assert resp.status_code == 400
    assert "Invalid base64" in resp.json()["detail"]
