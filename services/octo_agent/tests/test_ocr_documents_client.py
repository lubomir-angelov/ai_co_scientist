from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import requests
from shared_library.data_contracts import (
    OCRBlock,
    OcrDocumentError,
    OcrDocumentErrorCode,
    OCRPage,
    OCRResponse,
    OCRSection,
)

from service_errors import OCRServiceError
from tools.document_parser_ocr import documents_client
from tools.document_parser_ocr.documents_client import OcrDocumentsClient


def _doc(doc_id: str = "file:a") -> OCRResponse:
    return OCRResponse(
        doc_id=doc_id,
        sections=[OCRSection(name="Page 1", text="hi")],
        tables=[],
        pages=[OCRPage(page_number=1, blocks=[OCRBlock(ref="text", bbox=None, text="hi")])],
        metadata={"page_count": 1},
    )


def _resp(status: int, *, body: str | None = None, json_body: object = None) -> MagicMock:
    if body is None and json_body is not None:
        body = json.dumps(json_body)
    resp = MagicMock()
    resp.status_code = status
    resp.content = (body if body is not None else "").encode()
    resp.text = body if body is not None else ""
    return resp


def _error_body(code: OcrDocumentErrorCode, doc_id: str = "file:a") -> dict:
    return OcrDocumentError(code=code, doc_id=doc_id).model_dump(mode="json")


@pytest.fixture
def get(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(documents_client.requests, "get", mock)
    return mock


def _client() -> OcrDocumentsClient:
    return OcrDocumentsClient("http://reader:8008/", 5.0)


def test_200_returns_document(get: MagicMock) -> None:
    get.return_value = _resp(200, body=_doc().model_dump_json())
    assert _client().fetch("file:a") == _doc()
    assert get.call_args.kwargs["timeout"] == 5.0


def test_doc_id_is_quoted_in_path(get: MagicMock) -> None:
    get.return_value = _resp(200, body=_doc().model_dump_json())
    _client().fetch("file:a")
    assert get.call_args.args[0] == "http://reader:8008/ocr/documents/file%3Aa"


def test_404_with_document_not_found_code_is_none(get: MagicMock) -> None:
    get.return_value = _resp(404, json_body=_error_body(OcrDocumentErrorCode.NOT_FOUND))
    assert _client().fetch("file:a") is None


def test_404_for_another_doc_id_raises(get: MagicMock) -> None:
    get.return_value = _resp(
        404, json_body=_error_body(OcrDocumentErrorCode.NOT_FOUND, "file:other")
    )
    with pytest.raises(OCRServiceError) as exc:
        _client().fetch("file:a")
    assert exc.value.status_code == 404


@pytest.mark.parametrize("json_body", [None, {"detail": "Not Found"}, ["document_not_found"]])
def test_404_without_the_code_raises(get: MagicMock, json_body: object) -> None:
    get.return_value = _resp(404, body="Not Found", json_body=json_body)
    with pytest.raises(OCRServiceError) as exc:
        _client().fetch("file:a")
    assert exc.value.status_code == 404


def test_500_raises_with_status_code(get: MagicMock) -> None:
    get.return_value = _resp(500, body="boom")
    with pytest.raises(OCRServiceError) as exc:
        _client().fetch("file:a")
    assert exc.value.status_code == 500


def test_500_integrity_error_names_the_reocr_remedy(get: MagicMock) -> None:
    get.return_value = _resp(500, json_body=_error_body(OcrDocumentErrorCode.INTEGRITY))
    with pytest.raises(OCRServiceError) as exc:
        _client().fetch("file:a")
    assert exc.value.status_code == 500
    assert "REOCR=file:a" in str(exc.value)


def test_connection_error_raises_with_no_status_code(get: MagicMock) -> None:
    get.side_effect = requests.ConnectionError("refused")
    with pytest.raises(OCRServiceError) as exc:
        _client().fetch("file:a")
    assert exc.value.status_code is None


def test_invalid_body_raises(get: MagicMock) -> None:
    get.return_value = _resp(200, body='{"doc_id": "file:a"}')
    with pytest.raises(OCRServiceError, match="contract"):
        _client().fetch("file:a")


def test_doc_id_mismatch_raises(get: MagicMock) -> None:
    get.return_value = _resp(200, body=_doc("file:other").model_dump_json())
    with pytest.raises(OCRServiceError, match="file:other"):
        _client().fetch("file:a")
