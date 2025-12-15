# services/orchestrator/src/tools/ocr.py

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from typing import Any, Dict, Optional

from .registry import ToolSpec

logger = logging.getLogger(__name__)


def make_ocr_tool(*, base_url: str, api_key: Optional[str] = None) -> ToolSpec:
    async def _extract_ocr(doc_id: str, content_b64: str) -> Dict[str, Any]:
        url = base_url.rstrip("/") + "/extract/ocr"
        payload = {"doc_id": doc_id, "content_b64": content_b64}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        def _do() -> Dict[str, Any]:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)

        try:
            return await asyncio.to_thread(_do)
        except Exception:
            logger.exception("OCR extract failed")
            raise

    return ToolSpec(
        name="ocr_extract",
        description="Extract text from a base64-encoded PDF document using the OCR service.",
        parameters_schema={
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document identifier"},
                "content_b64": {
                    "type": "string",
                    "description": "Base64-encoded PDF bytes",
                },
            },
            "required": ["doc_id", "content_b64"],
            "additionalProperties": False,
        },
        handler=_extract_ocr,
    )
