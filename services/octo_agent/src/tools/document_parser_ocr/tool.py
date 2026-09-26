"""
Document Parser Tool:
 - Uses the DeepSeekOCR server to parse documents (PDF/images).

Calls a local/remote FastAPI OCR server:
  POST {base_url}/ocr/extract
with payload:
  {"doc_id": "...", "content_b64": "..."}

Returns a structured dict and (optionally) writes artifacts to output_dir. ``base_url``,
``timeout_s`` and ``auth_header`` default to ``RuntimeConfig.from_env()`` when not given
explicitly, so an agent call and the paper-ingestion batch share one configuration source.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from pydantic import ValidationError
from shared_library.data_contracts import OCRResponse

from runtime_config import RuntimeConfig
from service_errors import OCRServiceError
from tools.base import BaseTool

_URL_RE = re.compile(r"^(http|https|ftp)://", re.IGNORECASE)


@dataclass(frozen=True)
class _ToolConfig:
    base_url: str
    timeout_s: float
    verify_tls: bool
    auth_header: str | None


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
                "base_url": "str - OCR server base URL; default OCR_BASE_URL.",
                "timeout_s": "float - request timeout; default OCR_REQUEST_TIMEOUT_SECONDS (3600).",
                "save_artifacts": "bool - Save markdown/json outputs to output_dir (default: True).",
                "verify_tls": "bool - Verify TLS certificates for HTTPS URLs (default: True).",
                "auth_header": "str - Optional Authorization header value; default OCR_AUTH_HEADER.",
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
        doc_id: str | None = None,
        base_url: str | None = None,
        timeout_s: float | None = None,
        save_artifacts: bool = True,
        verify_tls: bool = True,
        auth_header: str | None = None,
    ) -> dict[str, Any]:
        env = RuntimeConfig.from_env()
        cfg = _ToolConfig(
            base_url=(base_url if base_url is not None else env.ocr_base_url).rstrip("/"),
            timeout_s=float(timeout_s if timeout_s is not None else env.ocr_request_timeout_seconds),
            verify_tls=bool(verify_tls),
            auth_header=auth_header if auth_header is not None else env.ocr_auth_header,
        )

        started = time.time()
        doc_id_final = doc_id if doc_id is not None else self._infer_doc_id(input_path_or_url)

        content_bytes, source_kind = self._load_bytes(input_path_or_url, cfg)
        content_b64 = base64.b64encode(content_bytes).decode("utf-8")

        payload = {"doc_id": doc_id_final, "content_b64": content_b64}

        t0 = time.time()
        response = self._post_ocr(cfg, payload)
        t1 = time.time()

        markdown = self._combine_sections_to_markdown(response.sections)

        artifacts: dict[str, str | None] = {"markdown_path": None, "json_path": None}
        if save_artifacts:
            artifacts = self._write_artifacts(response.doc_id, markdown, response)

        finished = time.time()
        return {
            "doc_id": response.doc_id,
            "source": {"kind": source_kind, "input": input_path_or_url},
            "markdown": markdown,
            "sections": [s.model_dump(mode="json") for s in response.sections],
            "tables": [t.model_dump(mode="json") for t in response.tables],
            "metadata": response.metadata,
            "artifacts": artifacts,
            "timings_ms": {
                "ocr_request_ms": int((t1 - t0) * 1000),
                "total_ms": int((finished - started) * 1000),
            },
        }

    def _infer_doc_id(self, input_path_or_url: str) -> str:
        if _URL_RE.match(input_path_or_url):
            tail = input_path_or_url.split("?")[0].rstrip("/").split("/")[-1]
            base = tail
        else:
            base = os.path.basename(input_path_or_url)

        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif"):
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
                break

        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", base).strip("_")
        if not safe:
            raise ValueError(
                f"Could not derive a non-empty doc_id from {input_path_or_url!r}; pass doc_id explicitly."
            )
        return safe

    def _load_bytes(self, input_path_or_url: str, cfg: _ToolConfig) -> tuple[bytes, str]:
        if _URL_RE.match(input_path_or_url):
            resp = requests.get(input_path_or_url, timeout=cfg.timeout_s, verify=cfg.verify_tls)
            resp.raise_for_status()
            return resp.content, "url"

        if not os.path.isfile(input_path_or_url):
            raise ValueError(f"Input path does not exist or is not a file: {input_path_or_url}")

        with open(input_path_or_url, "rb") as f:
            return f.read(), "file"

    def _post_ocr(self, cfg: _ToolConfig, payload: dict[str, Any]) -> OCRResponse:
        url = f"{cfg.base_url}/ocr/extract"
        headers = {"Content-Type": "application/json"}
        if cfg.auth_header:
            headers["Authorization"] = cfg.auth_header

        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=cfg.timeout_s, verify=cfg.verify_tls
            )
        except requests.RequestException as exc:
            raise OCRServiceError(
                f"OCR service unreachable at {url} (timeout={cfg.timeout_s}s): {exc}",
                status_code=None,
            ) from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise OCRServiceError(
                f"OCR server error {resp.status_code} on POST {url}: {detail}",
                status_code=resp.status_code,
            )

        try:
            return OCRResponse.model_validate(resp.json())
        except ValidationError as exc:
            raise OCRServiceError(
                f"OCR response violates OCRResponse contract: {exc}",
                status_code=resp.status_code,
            ) from exc

    def _combine_sections_to_markdown(self, sections: list[Any]) -> str:
        parts: list[str] = []
        for sec in sections:
            name = sec.name.strip()
            text = sec.text.rstrip()
            if name:
                parts.append(f"## {name}\n\n{text}\n")
            else:
                parts.append(f"{text}\n")
        return "\n".join(parts).strip() + "\n" if parts else ""

    def _write_artifacts(
        self, doc_id: str, markdown: str, response: OCRResponse
    ) -> dict[str, str | None]:
        out_dir = self.output_dir or os.path.join(os.getcwd(), "ocr_outputs")
        os.makedirs(out_dir, exist_ok=True)

        md_path = os.path.join(out_dir, f"{doc_id}.md")
        json_path = os.path.join(out_dir, f"{doc_id}.json")
        json_tmp_path = f"{json_path}.tmp"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        with open(json_tmp_path, "w", encoding="utf-8") as f:
            json.dump(response.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        os.replace(json_tmp_path, json_path)

        return {"markdown_path": md_path, "json_path": json_path}


if __name__ == "__main__":
    # Minimal manual test:
    #   python tool.py
    #   (expects OCR server at OCR_BASE_URL, default http://localhost:8002)
    tool = Document_Parser_OCR_Tool()
    tool.set_custom_output_dir("detected_ocr")

    sample = os.environ.get("OCR_SAMPLE_INPUT", "examples/quantum_photonics_qems_mems.pdf")

    result = tool.execute(input_path_or_url=sample, save_artifacts=True)
    print(
        json.dumps(
            {
                "doc_id": result["doc_id"],
                "artifacts": result["artifacts"],
                "timings_ms": result["timings_ms"],
                "metadata": result["metadata"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
