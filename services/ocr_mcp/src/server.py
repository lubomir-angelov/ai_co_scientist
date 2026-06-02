from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Defaults - overridden by env vars at runtime
_DEFAULT_OCR_BASE_URL = "http://localhost:8002"
_DEFAULT_TIMEOUT = 300.0


def _get_ocr_base_url() -> str:
    """Return the OCR service base URL from environment or default."""
    return os.environ.get("OCR_BASE_URL", _DEFAULT_OCR_BASE_URL)


def _get_timeout() -> float:
    """Return the request timeout from environment or default."""
    return float(os.environ.get("OCR_REQUEST_TIMEOUT", str(_DEFAULT_TIMEOUT)))


async def _call_ocr(content_b64: str, doc_id: str) -> dict[str, Any]:
    """Call the underlying OCR service extract endpoint."""
    url = f"{_get_ocr_base_url()}/ocr/extract"
    payload = {"doc_id": doc_id, "content_b64": content_b64}

    async with httpx.AsyncClient(timeout=_get_timeout()) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def create_app() -> FastMCP:
    """Create and configure the MCP server instance."""
    mcp = FastMCP(
        "ocr-mcp",
        instructions=(
            "DeepSeek OCR MCP server. Exposes document OCR capabilities "
            "(PDFs and images) to MCP-compatible clients. "
            "Uses the underlying DeepSeek-OCR service for extraction."
        ),
    )

    @mcp.tool()
    async def ocr_extract_pdf(
        pdf_b64: str,
        doc_id: str = "unknown",
    ) -> str:
        """Extract text from a PDF document given as base64-encoded bytes.

        Returns a markdown-formatted string with the full document text
        and per-page sections.

        Args:
            pdf_b64: Base64-encoded PDF file bytes.
            doc_id: Optional identifier for the document (used in response metadata).

        Returns:
            Markdown text extracted from the PDF.
        """
        result = await _call_ocr(content_b64=pdf_b64, doc_id=doc_id)
        sections = result.get("sections", [])
        combined = ""
        for s in sections:
            name = s.get("name", "Section")
            text = s.get("text", "")
            combined += f"## {name}\n\n{text}\n\n"
        return combined.strip()

    @mcp.tool()
    async def ocr_extract_image(
        image_b64: str,
        doc_id: str = "unknown",
    ) -> str:
        """Extract text from an image (PNG, JPEG, etc.) given as base64-encoded bytes.

        Returns a markdown-formatted string with the extracted text.

        Args:
            image_b64: Base64-encoded image file bytes.
            doc_id: Optional identifier for the document (used in response metadata).

        Returns:
            Markdown text extracted from the image.
        """
        result = await _call_ocr(content_b64=image_b64, doc_id=doc_id)
        sections = result.get("sections", [])
        combined = ""
        for s in sections:
            name = s.get("name", "Section")
            text = s.get("text", "")
            combined += f"## {name}\n\n{text}\n\n"
        return combined.strip()

    @mcp.tool()
    async def ocr_extract_file(
        file_path: str,
        doc_id: str | None = None,
    ) -> str:
        """Extract text from a PDF or image file on disk.

        Automatically detects PDF vs image based on file extension and
        file content.

        Args:
            file_path: Absolute or relative path to the PDF or image file.
            doc_id: Optional document identifier. Defaults to the filename.

        Returns:
            Markdown text extracted from the file.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = path.read_bytes()
        file_doc_id = doc_id or path.name

        # Detect PDF by magic bytes first, then extension fallback
        is_pdf = raw.startswith(b"%PDF-") or path.suffix.lower() == ".pdf"

        if is_pdf:
            return await ocr_extract_pdf(
                pdf_b64=base64.b64encode(raw).decode("ascii"),
                doc_id=file_doc_id,
            )
        else:
            return await ocr_extract_image(
                image_b64=base64.b64encode(raw).decode("ascii"),
                doc_id=file_doc_id,
            )

    @mcp.tool()
    async def ocr_health() -> dict[str, Any]:
        """Check the health of the underlying OCR service.

        Returns:
            JSON object with service health status.
        """
        url = f"{_get_ocr_base_url()}/healthz"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return {"status": "ok", "service": "ocr", "ready": True}
            except httpx.HTTPError as e:
                logger.warning("OCR health check failed: %s", e)
                return {"status": "error", "service": "ocr", "ready": False, "detail": str(e)}

    @mcp.resource("ocr://config")
    async def get_ocr_config() -> str:
        """Return the current OCR service configuration as text."""
        return (
            f"OCR_BASE_URL={_get_ocr_base_url()}\n"
            f"REQUEST_TIMEOUT={_get_timeout()}s\n"
        )

    return mcp


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8003"))
    mcp = create_app()
    # Override settings after creation since env vars may differ from defaults
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport=transport)
