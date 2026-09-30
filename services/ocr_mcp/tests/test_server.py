"""Unit tests for the OCR MCP server; the OCR service is replaced by httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from src import server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def ocr_requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Route every httpx.AsyncClient to a fake OCR service and record the requests."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/healthz":
            return httpx.Response(503)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "doc_id": body["doc_id"],
                "sections": [{"name": "FullText", "text": "hello"}],
                "tables": [],
                "metadata": {"page_count": 1},
            },
        )

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(server.httpx, "AsyncClient", fake_client)
    monkeypatch.setenv("OCR_BASE_URL", "http://ocr-test:8002")
    return seen


async def test_expected_tools_are_registered() -> None:
    tools = {t.name for t in await server.create_app().list_tools()}
    assert {"ocr_extract_pdf", "ocr_health"} <= tools


async def test_call_ocr_posts_to_configured_service(ocr_requests: list[httpx.Request]) -> None:
    result = await server._call_ocr("ZmFrZQ==", "doc-1")

    assert result["doc_id"] == "doc-1"
    [request] = ocr_requests
    assert str(request.url) == "http://ocr-test:8002/ocr/extract"
    assert json.loads(request.content) == {"doc_id": "doc-1", "content_b64": "ZmFrZQ=="}


async def test_health_tool_reports_unhealthy_ocr(ocr_requests: list[httpx.Request]) -> None:
    app = server.create_app()
    result = await app.call_tool("ocr_health", {})

    # FastMCP returns (content blocks, structured result) for dict-returning tools.
    structured = result[1] if isinstance(result, tuple) else result
    assert structured["ready"] is False
    assert structured["status"] == "error"
