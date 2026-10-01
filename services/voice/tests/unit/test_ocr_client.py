import httpx
import pytest
from conftest import load_ocr_fixture

from voice_service.core.errors import (
    OcrContractError,
    OcrDocumentNotFoundError,
    OcrServiceError,
    OcrTimeoutError,
)
from voice_service.services.ocr_client import OcrDocumentClient

pytestmark = pytest.mark.anyio


def client_for(handler) -> OcrDocumentClient:
    http = httpx.AsyncClient(base_url="http://ocr.test", transport=httpx.MockTransport(handler))
    return OcrDocumentClient(http)


async def test_200_valid_document() -> None:
    doc = load_ocr_fixture()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=doc.model_dump_json())

    assert await client_for(handler).fetch("paper-1") == doc
    assert seen == ["/ocr/documents/paper-1"]


async def test_doc_id_is_path_quoted() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        return httpx.Response(404)

    with pytest.raises(OcrDocumentNotFoundError):
        await client_for(handler).fetch("a?b#c")
    assert seen == ["/ocr/documents/a%3Fb%23c"]


async def test_404_maps_to_not_found() -> None:
    with pytest.raises(OcrDocumentNotFoundError):
        await client_for(lambda r: httpx.Response(404, json={"code": "document_not_found"})).fetch("x")


async def test_500_maps_to_service_error() -> None:
    with pytest.raises(OcrServiceError, match="500"):
        await client_for(lambda r: httpx.Response(500)).fetch("x")


async def test_timeout_maps_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OcrTimeoutError):
        await client_for(handler).fetch("x")


async def test_connect_error_maps_to_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OcrServiceError, match="unreachable"):
        await client_for(handler).fetch("x")


async def test_contract_violation() -> None:
    with pytest.raises(OcrContractError):
        await client_for(lambda r: httpx.Response(200, json={"doc_id": "x"})).fetch("x")


async def test_doc_id_mismatch_is_a_contract_violation() -> None:
    doc = load_ocr_fixture()
    with pytest.raises(OcrContractError, match="paper-1"):
        await client_for(lambda r: httpx.Response(200, content=doc.model_dump_json())).fetch("other")
