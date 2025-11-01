# services/ocr/tests/test_server.py
import base64
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.server import app
import src.server as server  # we'll patch globals on this


class FakeModel:
    def infer(
        self,
        tokenizer,
        prompt: str,
        image_file: str,
        output_path: str,
        base_size: int,
        image_size: int,
        crop_mode: bool,
        save_results: bool,
        test_compress: bool,
    ):
        # mimic real DeepSeek-OCR return shape
        return {"text": "hello from fake ocr"}


class FakeTokenizer:
    pass


@patch("src.server.lifespan")  # don't run real startup
@patch("src.server._bytes_to_image_path", return_value="/tmp/fake.jpg")
def test_ocr_endpoint_returns_200(_mock_path, _mock_load):
    client = TestClient(app)

    # inject fake globals that the endpoint uses
    server.model = FakeModel()
    server.tokenizer = FakeTokenizer()

    content_b64 = base64.b64encode(b"fake-image").decode()

    resp = client.post(
        "/ocr/extract",
        json={"doc_id": "doc-123", "content_b64": content_b64},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == "doc-123"
    assert data["sections"][0]["text"] == "hello from fake ocr"


@patch("src.server.lifespan")
def test_ocr_endpoint_rejects_bad_base64(_mock_load):
    client = TestClient(app)
    resp = client.post(
        "/ocr/extract",
        json={"doc_id": "doc-123", "content_b64": "!!not base64!!"},
    )
    assert resp.status_code == 400
    assert "Invalid base64" in resp.json()["detail"]
