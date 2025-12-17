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

# --- keep your flash-attn disables, do this BEFORE importing transformers ---
os.environ["TRANSFORMERS_ATTENTION_IMPLEMENTATION"] = "eager"
os.environ["TRANSFORMERS_NO_FLASH_ATTENTION"] = "1"

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from transformers import AutoModel, AutoTokenizer
import torch
from pdf2image import convert_from_path
from PIL import Image

# run with make run to add the shared_library to PYTHONPATH
# or export it manually before running uvicorn
from shared_library.data_contracts import (
    OCRRequest,
    OCRResponse,
    OCRSection,
    OCRTable,
)

MODEL_PATH = "/opt/models/deepseek-ocr"

logger = logging.getLogger("__name__")


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


# Optional: cap page concurrency to avoid GPU OOM.
PAGE_CONCURRENCY = int(os.environ.get("OCR_PAGE_CONCURRENCY", "1"))
_page_sem = asyncio.Semaphore(PAGE_CONCURRENCY)


def _infer_one_page(image_path: str, out_dir: str) -> str:
    """
    Synchronous wrapper for model.infer; safe to call via asyncio.to_thread.
    """
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
    )

    if isinstance(res, dict):
        return (res.get("text", "") or "")
    return ""


async def _infer_one_page_async(image_path: str, out_dir: str) -> str:
    async with _page_sem:
        return await asyncio.to_thread(_infer_one_page, image_path, out_dir)


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
        for p in image_paths:
            texts.append(await _infer_one_page_async(p, out_dir))

        # Option B: limited concurrency (still risky on GPU)
        # texts = await asyncio.gather(*[
        #     _infer_one_page_async(p, os.path.join(out_dir, f"page_{i+1:04d}"))
        #     for i, p in enumerate(image_paths)
        # ])


        sections: list[OCRSection] = []
        for i, text in enumerate(texts):
            sections.append(OCRSection(name=f"Page {i+1}", text=text))

        # Optional: also provide a combined section
        combined = "\n\n".join([t.strip() for t in texts if (t or "").strip()]).strip()
        if combined:
            sections.insert(0, OCRSection(name="FullText", text=combined))

        return OCRResponse(
            doc_id=req.doc_id,
            sections=sections,
            tables=[],  # don’t parse tables yet
            metadata={
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "engine": "deepseek-ocr",
                "page_count": len(image_paths),
                "page_concurrency": PAGE_CONCURRENCY,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")
    finally:
        # Best-effort cleanup
        for d in cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)