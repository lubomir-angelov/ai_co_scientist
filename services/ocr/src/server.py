import os
import tempfile
import torch
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse
from transformers import AutoModel, AutoTokenizer

from pdf2image import convert_from_path
from PIL import Image
import mimetypes


# --- Force Transformers to NOT auto-enable FlashAttention ---
# This prevents the internal _autoset_attn_implementation() call
# from trying flash-attn and throwing ImportError.
os.environ["TRANSFORMERS_ATTENTION_IMPLEMENTATION"] = "eager"
# fallback belt + suspenders for some builds:
os.environ["TRANSFORMERS_NO_FLASH_ATTENTION"] = "1"

MODEL_PATH = "/opt/models/deepseek-ocr"  # baked into the image during build

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
)

print("Loading model on GPU (no flash-attn)...")
model = AutoModel.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
    use_safetensors=True,

    # critical: tell HF "do NOT try flash-attn kernels"
    _attn_implementation="eager",
)

# move model to RTX 5090 in BF16
model = model.to(device="cuda", dtype=torch.bfloat16).eval()
print("Model is on GPU and ready.")

app = FastAPI()

HTML_PAGE = """
<!DOCTYPE html>
<html>
  <body style="font-family:sans-serif; max-width:600px; margin:2rem auto;">
    <h2>DeepSeek OCR Demo (RTX 5090 GPU, eager attention)</h2>
    <form id="f">
      <input type="file" name="image" accept="image/*,application/pdf"/>
      <button type="submit">OCR</button>
    </form>
    <pre id="out" style="white-space:pre-wrap; background:#eee; padding:1rem; margin-top:1rem;"></pre>
    <script>
    const f = document.getElementById('f');
    const out = document.getElementById('out');
    f.onsubmit = async (e) => {
      e.preventDefault();
      const data = new FormData(f);
      out.textContent = "Running OCR...";
      const res = await fetch('/ocr', { method:'POST', body:data });
      const j = await res.json();
      out.textContent = j.text || j.error || "No result";
    };
    </script>
  </body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE

@app.post("/ocr")
async def ocr(image: UploadFile = File(...)):
    try:
        # Save upload to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename or "")[-1]) as tmp:
            file_bytes = await image.read()
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Decide what to feed into model.infer
        # Case 1: PDF -> render first page to a temp JPG
        is_pdf = (image.content_type == "application/pdf") or (
            (image.filename or "").lower().endswith(".pdf")
        )

        if is_pdf:
            pages = convert_from_path(tmp_path, dpi=300)
            if not pages:
                return JSONResponse({"error": "PDF had no pages"}, status_code=400)
            page0: Image.Image = pages[0]

            # Write that first page back out as a temp jpeg
            raster_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            page0.save(raster_tmp.name, format="JPEG", quality=95)
            image_path_for_infer = raster_tmp.name
        else:
            # Not a PDF: assume it's a normal image Pillow can open
            # Let's sanity check that it's actually an image
            try:
                _ = Image.open(tmp_path)
                image_path_for_infer = tmp_path
            except Exception:
                return JSONResponse(
                    {"error": "Uploaded file is not a supported image/PDF"},
                    status_code=400,
                )

        prompt = "<image>\n<|grounding|>Convert the document to markdown."
        out_dir = tempfile.mkdtemp()

        res = model.infer(
            tokenizer,
            prompt=prompt,
            image_file=image_path_for_infer,
            output_path=out_dir,
            base_size=1024,
            image_size=640,
            crop_mode=True,
            save_results=True,
            test_compress=True,
        )

        if isinstance(res, dict):
            text_out = res.get("text", "") or ""
        else:
            text_out = "OK, processed."

        return JSONResponse({"text": text_out})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)