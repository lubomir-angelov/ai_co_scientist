# services/ocr/src/server.py
import os
import base64
import tempfile
from datetime import datetime, timezone
from contextlib import asynccontextmanager

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


def _bytes_to_image_path(data: bytes, filename_hint: str = "upload") -> str:
    # if it's a PDF, rasterize first page
    if filename_hint.lower().endswith(".pdf"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(data)
            pdf_path = tmp_pdf.name

        pages = convert_from_path(pdf_path, dpi=300)

        if not pages:
            raise HTTPException(status_code=400, detail="PDF had no pages")
        
        page0: Image.Image = pages[0]
        raster_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        page0.save(raster_tmp.name, format="JPEG", quality=95)

        return raster_tmp.name

    # else: assume image
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp_img:
        tmp_img.write(data)
        img_path = tmp_img.name

    # verify it’s actually an image (Pillow will throw if not)
    Image.open(img_path)
    
    return img_path


@app.post("/ocr/extract", response_model=OCRResponse)
def extract(req: OCRRequest):
    # decode base64
    try:
        content_bytes = base64.b64decode(req.content_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    # pick suitable image path (pdf→jpg)
    image_path = _bytes_to_image_path(content_bytes, filename_hint=f"{req.doc_id}.pdf")

    prompt = "<image>\n<|grounding|>Convert the document to markdown."
    out_dir = tempfile.mkdtemp()

    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    if isinstance(res, dict):
        text_out = res.get("text", "") or ""
    else:
        text_out = "OK, processed."

    # we don’t have real sections/tables parsed yet, so return 1 blob section
    sections = [OCRSection(name="FullText", text=text_out)]
    tables: list[OCRTable] = []

    return OCRResponse(
        doc_id=req.doc_id,
        sections=sections,
        tables=tables,
        metadata={
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "engine": "deepseek-ocr",
        },
    )
