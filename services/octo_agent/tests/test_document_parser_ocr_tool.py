from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import requests

from service_errors import OCRServiceError
from tools.document_parser_ocr import tool as ocr_tool_module
from tools.document_parser_ocr.tool import Document_Parser_OCR_Tool

_VALID_RESPONSE_BODY = {
    "doc_id": "arxiv:2410.12345",
    "sections": [{"name": "Page 1", "text": "hello"}, {"name": "Page 2", "text": "world"}],
    "tables": [],
    "metadata": {"page_count": 2},
}


def _response(status: int, body=None, text: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    if text is not None:
        resp.text = text
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = body
    return resp


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("OCR_BASE_URL", "http://ocr:8002")
    mock = MagicMock(return_value=_response(200, _VALID_RESPONSE_BODY))
    monkeypatch.setattr(ocr_tool_module.requests, "post", mock)
    return mock


def test_execute_returns_validated_response_and_writes_atomic_cache(
    post: MagicMock, tmp_path
) -> None:
    tool = Document_Parser_OCR_Tool()
    tool.set_custom_output_dir(str(tmp_path))

    result = tool.execute(input_path_or_url=__file__, doc_id="arxiv:2410.12345")

    assert result["doc_id"] == "arxiv:2410.12345"
    assert result["sections"] == _VALID_RESPONSE_BODY["sections"]
    json_path = tmp_path / "arxiv:2410.12345.json"
    assert json_path.is_file()
    assert not (tmp_path / "arxiv:2410.12345.json.tmp").exists()
    on_disk = json.loads(json_path.read_text())
    assert on_disk == _VALID_RESPONSE_BODY


def test_missing_sections_raises_without_coalescing(post: MagicMock) -> None:
    post.return_value = _response(200, {"doc_id": "x", "tables": [], "metadata": {}})
    tool = Document_Parser_OCR_Tool()
    with pytest.raises(OCRServiceError, match="OCRResponse contract"):
        tool.execute(input_path_or_url=__file__, doc_id="x", save_artifacts=False)


def test_http_500_with_json_body_carries_full_detail_and_status_code(post: MagicMock) -> None:
    post.return_value = _response(500, {"detail": "GPU OOM " + "x" * 600})
    tool = Document_Parser_OCR_Tool()
    with pytest.raises(OCRServiceError) as excinfo:
        tool.execute(input_path_or_url=__file__, doc_id="x", save_artifacts=False)
    assert excinfo.value.status_code == 500
    assert "x" * 600 in str(excinfo.value)


def test_non_json_error_body_is_included_in_full(post: MagicMock) -> None:
    long_body = "server error " + "y" * 700
    post.return_value = _response(500, text=long_body)
    tool = Document_Parser_OCR_Tool()
    with pytest.raises(OCRServiceError) as excinfo:
        tool.execute(input_path_or_url=__file__, doc_id="x", save_artifacts=False)
    assert long_body in str(excinfo.value)


def test_timeout_raises_with_no_status_code(post: MagicMock) -> None:
    post.side_effect = requests.Timeout("timed out")
    tool = Document_Parser_OCR_Tool()
    with pytest.raises(OCRServiceError) as excinfo:
        tool.execute(input_path_or_url=__file__, doc_id="x", save_artifacts=False)
    assert excinfo.value.status_code is None


def test_explicit_timeout_reaches_requests_post(post: MagicMock) -> None:
    tool = Document_Parser_OCR_Tool()
    tool.execute(input_path_or_url=__file__, doc_id="x", timeout_s=12.5, save_artifacts=False)
    assert post.call_args.kwargs["timeout"] == 12.5


def test_timeout_none_uses_runtime_config(monkeypatch: pytest.MonkeyPatch, post: MagicMock) -> None:
    monkeypatch.setenv("OCR_REQUEST_TIMEOUT_SECONDS", "77")
    tool = Document_Parser_OCR_Tool()
    tool.execute(input_path_or_url=__file__, doc_id="x", save_artifacts=False)
    assert post.call_args.kwargs["timeout"] == 77.0


def test_infer_doc_id_empty_raises(post: MagicMock) -> None:
    tool = Document_Parser_OCR_Tool()
    with pytest.raises(ValueError, match="doc_id"):
        # URL tail is exactly the extension, so stripping it leaves nothing usable.
        tool.execute(input_path_or_url="https://example.com/.pdf", save_artifacts=False)
