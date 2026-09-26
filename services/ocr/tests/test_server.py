# services/ocr/tests/test_server.py
import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.server import app


def _client() -> TestClient:
    # Not used as a context manager, so the model-loading lifespan never runs.
    return TestClient(app)


@patch("src.server._infer_one_page", return_value=("hello from fake ocr", {"page": 1}))
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


def test_ocr_endpoint_rejects_bad_base64():
    resp = _client().post("/ocr/extract", json={"doc_id": "doc-123", "content_b64": "!!not base64!!"})
    assert resp.status_code == 400
    assert "Invalid base64" in resp.json()["detail"]


def test_healthz_reports_not_ready_before_model_load():
    body = _client().get("/healthz").json()
    assert body["service"] == "ocr"
    assert body["ready"] is False
