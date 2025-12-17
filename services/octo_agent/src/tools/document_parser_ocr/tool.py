"""
Document Parser Tool:
 - Usees DeepSeek OCR Server Client to parse documents (PDF/images).

Calls a local/remote FastAPI OCR server:
  POST {base_url}/ocr/extract
with payload:
  {"doc_id": "...", "content_b64": "..."}

Returns a structured dict and (optionally) writes artifacts to output_dir.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from tools.base import BaseTool


_URL_RE = re.compile(r"^(http|https|ftp)://", re.IGNORECASE)


@dataclass(frozen=True)
class _ToolConfig:
    base_url: str
    timeout_s: int
    verify_tls: bool
    auth_header: Optional[str]


class Document_Parser_OCR_Tool(BaseTool):
    """
    OctoTools tool that sends a document (PDF/image) to the user's OCR server and returns OCR results.
    """

    require_llm_engine = False

    def __init__(self) -> None:
        super().__init__(
            tool_name="Document_Parser_OCR_Tool",
            tool_description=(
                "Client tool for a FastAPI DeepSeek OCR server. "
                "Accepts a local file path or URL (PDF/image), base64-encodes the bytes, "
                "calls /ocr/extract, and returns extracted markdown plus sections/tables/metadata."
            ),
            tool_version="1.0.0",
            input_types={
                "input_path_or_url": "str - Local file path or URL to a PDF/image.",
                "doc_id": "str - Optional document id; defaults to filename-derived id.",
                "base_url": "str - OCR server base URL (default: env OCR_BASE_URL or http://localhost:8002).",
                "timeout_s": "int - Request timeout in seconds (default: 120).",
                "save_artifacts": "bool - Save markdown/json outputs to output_dir (default: True).",
                "verify_tls": "bool - Verify TLS certificates for HTTPS URLs (default: True).",
                "auth_header": "str - Optional Authorization header value, e.g. 'Bearer ...'.",
            },
            output_type=(
                "dict - {doc_id, markdown, sections, tables, metadata, "
                "artifacts:{markdown_path,json_path}, timings_ms:{...}}"
            ),
            demo_commands=[
                {
                    "command": (
                        "tool = Document_Parser_OCR_Tool(); "
                        "tool.set_custom_output_dir('ocr_outputs'); "
                        "tool.execute(input_path_or_url='docs/sample.pdf')"
                    ),
                    "description": "Run OCR on a local PDF and save artifacts to ocr_outputs/.",
                },
                {
                    "command": (
                        "tool = Document_Parser_OCR_Tool(); "
                        "tool.execute(input_path_or_url='https://example.com/file.png', save_artifacts=False)"
                    ),
                    "description": "Run OCR on an image URL without saving artifacts.",
                },
            ],
            user_metadata={
                "server_contract": "POST /ocr/extract accepts OCRRequest {doc_id, content_b64} and returns OCRResponse.",
                "recommended_server_fix": "Use filename_hint=req.doc_id (not f'{req.doc_id}.pdf') to avoid forcing PDF parsing.",
            },
        )

    def execute(
        self,
        input_path_or_url: str,
        doc_id: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: int = 120,
        save_artifacts: bool = True,
        verify_tls: bool = True,
        auth_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        cfg = _ToolConfig(
            base_url=(base_url or os.environ.get("OCR_BASE_URL", "http://localhost:8002")).rstrip("/"),
            timeout_s=int(timeout_s),
            verify_tls=bool(verify_tls),
            auth_header=auth_header or os.environ.get("OCR_AUTH_HEADER"),
        )

        started = time.time()
        doc_id_final = doc_id or self._infer_doc_id(input_path_or_url)

        content_bytes, source_kind = self._load_bytes(input_path_or_url, cfg)
        content_b64 = base64.b64encode(content_bytes).decode("utf-8")

        payload = {"doc_id": doc_id_final, "content_b64": content_b64}

        t0 = time.time()
        response_json = self._post_ocr(cfg, payload)
        t1 = time.time()

        sections = response_json.get("sections", []) or []
        tables = response_json.get("tables", []) or []
        metadata = response_json.get("metadata", {}) or {}

        markdown = self._combine_sections_to_markdown(sections)

        artifacts: Dict[str, Optional[str]] = {"markdown_path": None, "json_path": None}
        if save_artifacts:
            artifacts = self._write_artifacts(doc_id_final, markdown, response_json)

        finished = time.time()
        return {
            "doc_id": response_json.get("doc_id", doc_id_final),
            "source": {"kind": source_kind, "input": input_path_or_url},
            "markdown": markdown,
            "sections": sections,
            "tables": tables,
            "metadata": metadata,
            "artifacts": artifacts,
            "timings_ms": {
                "ocr_request_ms": int((t1 - t0) * 1000),
                "total_ms": int((finished - started) * 1000),
            },
        }

    def _infer_doc_id(self, input_path_or_url: str) -> str:
        if _URL_RE.match(input_path_or_url):
            # Try to derive from URL path; fallback to "document"
            tail = input_path_or_url.split("?")[0].rstrip("/").split("/")[-1]
            base = tail or "document"
        else:
            base = os.path.basename(input_path_or_url) or "document"

        # Strip common extensions for nicer ids
        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif"):
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break

        # keep it filesystem-friendly
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", base).strip("_")
        return safe or "document"

    def _load_bytes(self, input_path_or_url: str, cfg: _ToolConfig) -> Tuple[bytes, str]:
        if _URL_RE.match(input_path_or_url):
            resp = requests.get(input_path_or_url, timeout=cfg.timeout_s, verify=cfg.verify_tls)
            resp.raise_for_status()
            return resp.content, "url"

        if not os.path.isfile(input_path_or_url):
            raise ValueError(f"Input path does not exist or is not a file: {input_path_or_url}")

        with open(input_path_or_url, "rb") as f:
            return f.read(), "file"

    def _post_ocr(self, cfg: _ToolConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{cfg.base_url}/ocr/extract"
        headers = {"Content-Type": "application/json"}
        if cfg.auth_header:
            headers["Authorization"] = cfg.auth_header

        resp = requests.post(url, json=payload, headers=headers, timeout=cfg.timeout_s, verify=cfg.verify_tls)
        if resp.status_code >= 400:
            # Try to surface FastAPI detail payloads cleanly
            try:
                err = resp.json()
            except Exception:
                err = {"detail": resp.text}
            raise RuntimeError(f"OCR server error {resp.status_code}: {err}")

        return resp.json()

    def _combine_sections_to_markdown(self, sections: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for sec in sections:
            name = (sec.get("name") or "").strip()
            text = (sec.get("text") or "").rstrip()
            if name:
                parts.append(f"## {name}\n\n{text}\n")
            else:
                parts.append(f"{text}\n")
        return "\n".join(parts).strip() + "\n" if parts else ""

    def _write_artifacts(self, doc_id: str, markdown: str, response_json: Dict[str, Any]) -> Dict[str, Optional[str]]:
        out_dir = self.output_dir or os.path.join(os.getcwd(), "ocr_outputs")
        os.makedirs(out_dir, exist_ok=True)

        md_path = os.path.join(out_dir, f"{doc_id}.md")
        json_path = os.path.join(out_dir, f"{doc_id}.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(response_json, f, ensure_ascii=False, indent=2)

        return {"markdown_path": md_path, "json_path": json_path}


if __name__ == "__main__":
    # Minimal manual test:
    #   python tool.py
    #   (expects OCR server at http://localhost:8002)
    tool = Document_Parser_OCR_Tool()
    tool.set_custom_output_dir("detected_ocr")

    # Change this to a real file in your environment.
    sample = os.environ.get("OCR_SAMPLE_INPUT", "examples/quantum_photonics_qems_mems.pdf")

    try:
        result = tool.execute(input_path_or_url=sample, save_artifacts=True)
        print(json.dumps(
            {
                "doc_id": result["doc_id"],
                "artifacts": result["artifacts"],
                "timings_ms": result["timings_ms"],
                "metadata": result["metadata"],
                "markdown_preview": result["markdown"][:400],
            },
            indent=2,
            ensure_ascii=False,
        ))
    except Exception as e:
        print(f"Execution failed: {e}")
