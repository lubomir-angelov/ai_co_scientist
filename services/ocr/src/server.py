# services/ocr/src/server.py
import os
import base64
import logging
import tempfile
from typing import List, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import asyncio
import shutil
from pathlib import Path


# --- keep your flash-attn disables, do this BEFORE importing transformers ---
os.environ["TRANSFORMERS_ATTENTION_IMPLEMENTATION"] = "eager"
os.environ["TRANSFORMERS_NO_FLASH_ATTENTION"] = "1"

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from transformers import AutoModel, AutoTokenizer
import torch
from pdf2image import convert_from_path
from PIL import Image

# run with make run to add the shared_library to PYTHONPATH
# or export it manually before running uvicorn
from shared_library.data_contracts import (
    OCR_FULLTEXT_SECTION,
    DocId,
    OCRBlock,
    OCRPage,
    OCRRequest,
    OCRResponse,
    OCRSection,
    ocr_page_section_name,
)

from document_store import DocumentIntegrityError, DocumentNotFoundError, OcrDocumentStore
from utils import ParsedBlock, parse_deepseek_grounded_output, blocks_to_markdown

MODEL_PATH = "/opt/models/deepseek-ocr"

logger = logging.getLogger("__name__")


def _require_documents_dir() -> Path:
    raw = os.environ.get("OCR_DOCUMENTS_DIR")
    if not raw:
        raise RuntimeError("OCR_DOCUMENTS_DIR must be set to the OCR document store directory")
    return Path(raw)


# Read once at import; the store fails the service at startup if the dir is missing/unwritable.
document_store = OcrDocumentStore(_require_documents_dir())

# Initialize globals so healthz can check them before model loads
tokenizer = None
model = None


# load once
@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_PATH,
        trust_remote_code=True,
    )

    print("Loading model on GPU (eager attention, no flash-attn)...")
    model = AutoModel.from_pretrained(
        MODEL_PATH,
        trust_remote_code=True,
        use_safetensors=True,
        _attn_implementation="eager",
    )
    model = model.to(device="cuda", dtype=torch.bfloat16).eval()
    print("Model is on GPU and ready.")

    try:
        yield
    finally:
        # optional cleanup
        pass

app = FastAPI(title="DeepSeek OCR Service", 
              version="0.1.0",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "ocr",
        "ready": model is not None and tokenizer is not None,
    }

def is_pdf_bytes(data: bytes) -> bool:
    # PDF files start with: %PDF-
    is_pdf_bytes = data.startswith(b"%PDF-")

    return is_pdf_bytes


def _rasterize_pdf_to_image_paths(pdf_bytes: bytes, dpi: int = 300) -> Tuple[str, List[str]]:
    """
    Returns (tmp_dir, [image_paths...]) where tmp_dir must be cleaned up by caller.
    Runs synchronously; call it via asyncio.to_thread in async code.
    """
    tmp_dir = tempfile.mkdtemp(prefix="ocr_pdf_")

    pdf_path = os.path.join(tmp_dir, "input.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    pages = convert_from_path(pdf_path, dpi=dpi)
    if not pages:
        raise HTTPException(status_code=400, detail="PDF had no pages")

    image_paths: List[str] = []
    for i, page in enumerate(pages):
        out_path = os.path.join(tmp_dir, f"page_{i+1:04d}.jpg")
        page.save(out_path, format="JPEG", quality=95)
        image_paths.append(out_path)

    return tmp_dir, image_paths


def _write_image_bytes_to_path(image_bytes: bytes) -> Tuple[str, str]:
    """
    Returns (tmp_dir, image_path). Validates with PIL.
    """
    tmp_dir = tempfile.mkdtemp(prefix="ocr_img_")
    img_path = os.path.join(tmp_dir, "input.bin")
    with open(img_path, "wb") as f:
        f.write(image_bytes)

    # Validate image bytes
    Image.open(img_path)

    return tmp_dir, img_path


async def _bytes_to_image_paths_async(data: bytes, filename_hint: str) -> Tuple[List[str], List[str]]:
    """
    Returns (image_paths, cleanup_dirs).
    cleanup_dirs are temp dirs to delete in finally.
    """
    cleanup_dirs: List[str] = []

    # Decide PDF by bytes first, then filename as fallback.
    if is_pdf_bytes(data) or filename_hint.lower().endswith(".pdf"):
        tmp_dir, image_paths = await asyncio.to_thread(_rasterize_pdf_to_image_paths, data, 300)
        cleanup_dirs.append(tmp_dir)
        return image_paths, cleanup_dirs

    tmp_dir, img_path = await asyncio.to_thread(_write_image_bytes_to_path, data)
    cleanup_dirs.append(tmp_dir)
    return [img_path], cleanup_dirs


def _infer_one_page(image_path: str, out_dir: str) -> Tuple[str, List[ParsedBlock]]:
    os.makedirs(out_dir, exist_ok=True)

    prompt = "<image>\n<|grounding|>Convert the document to markdown."
    res = model.infer(
        tokenizer,
        prompt=prompt,
        image_file=image_path,
        output_path=out_dir,
        base_size=1024,
        image_size=640,
        crop_mode=True,
        save_results=True,
        test_compress=True,
        # https://huggingface.co/deepseek-ai/DeepSeek-OCR/discussions/62
        # please know that you need to set eval_mode=True when using the model.infer() 
        # method as shown in the example if you actually want to have anything returned.
        eval_mode=True
    )

    if not isinstance(res, str):
        raise RuntimeError(
            f"model.infer returned {type(res).__name__}, expected str, for {image_path}"
        )
    blocks = parse_deepseek_grounded_output(res)
    return blocks_to_markdown(blocks), blocks


def _error(status: int, code: str, **extra: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, **extra})


@app.get("/ocr/documents/{doc_id}", response_model=OCRResponse)
async def get_document(doc_id: DocId):
    try:
        return document_store.load(doc_id)
    except DocumentNotFoundError:
        return _error(404, "document_not_found", doc_id=doc_id)
    except DocumentIntegrityError:
        logger.exception("stored OCR document failed integrity check", extra={"doc_id": doc_id})
        return _error(500, "document_integrity_error", doc_id=doc_id)


@app.post("/ocr/extract", response_model=OCRResponse)
async def extract(req: OCRRequest):
    try:
        content_bytes = base64.b64decode(req.content_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    # Rasterize all pages (PDF) or get single image path.
    cleanup_dirs = []
    out_dir = tempfile.mkdtemp(prefix="ocr_out_")
    try:
        image_paths, cleanup_dirs = await _bytes_to_image_paths_async(content_bytes, filename_hint=req.doc_id)

        # sequential OCR but non-blocking event loop
        texts = []
        pages: list[OCRPage] = []
        for i, image_path in enumerate(image_paths):
            page_out_dir = os.path.join(out_dir, f"page_{i+1:04d}")
            page_text, page_blocks = await asyncio.to_thread(_infer_one_page, image_path, page_out_dir)
            texts.append(page_text)
            pages.append(
                OCRPage(
                    page_number=i + 1,
                    blocks=[OCRBlock(ref=b.ref, bbox=b.bbox, text=b.text) for b in page_blocks],
                )
            )

        sections: list[OCRSection] = []
        for i, text in enumerate(texts):
            sections.append(OCRSection(name=ocr_page_section_name(i + 1), text=text))

        # Optional: also provide a combined section
        combined = "\n\n".join([t.strip() for t in texts if (t or "").strip()]).strip()
        if combined:
            sections.insert(0, OCRSection(name=OCR_FULLTEXT_SECTION, text=combined))

        resp = OCRResponse(
            doc_id=req.doc_id,
            sections=sections,
            tables=[],  # don’t parse tables yet
            pages=pages,
            metadata={
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "engine": "deepseek-ocr",
                "page_count": len(image_paths),
            },
        )
        # Persist BEFORE returning: the caller never gets a success whose artifact is not stored.
        try:
            await asyncio.to_thread(document_store.save, resp)
        except OSError:
            logger.exception("failed to persist OCR document", extra={"doc_id": req.doc_id})
            return _error(500, "ocr_store_write_failed", doc_id=req.doc_id)
        return resp

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")
    finally:
        # Best-effort cleanup
        for d in cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)