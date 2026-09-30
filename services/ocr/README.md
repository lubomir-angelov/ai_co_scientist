# OCR service

A [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) FastAPI server for PDFs and
images. It runs in a CUDA 12.8 container, and the model is downloaded into the image at build
time (the image is about 70 GB).

- `GET /healthz`: `{"status", "service": "ocr", "ready"}`. `ready` means the model is loaded.
- `POST /ocr/extract`: takes an `OCRRequest` `{doc_id, content_b64}` (PDF or image bytes)
  and returns an `OCRResponse` with a `FullText` section, one section per page, and page
  metadata.

Contracts live in `services/common/src/shared_library/data_contracts.py`.

## Running

```bash
cd services/ocr
make build     # docker image via compose.yaml (slow the first time)
make up        # port 8002, GPU 0
make health
make down
```

Or, from the repo root, `make ocr-up` / `make ocr-mcp-up` (OCR plus its MCP server).

Example request (piped through `printf` so large PDFs don't exceed the argument-length limit):

```bash
printf '{"doc_id":"paper-1","content_b64":"%s"}' "$(base64 -w0 paper.pdf)" \
  | curl -s localhost:8002/ocr/extract -H 'Content-Type: application/json' -d @-
```

## Development

```bash
make install        # light .venv: FastAPI + test deps, no torch
make test           # unit tests stub torch/transformers/pdf2image (tests/conftest.py)
make lint
make install-full   # adds the GPU runtime deps, needed for `make run`
make run            # local uvicorn (needs a GPU and the model at /opt/models/deepseek-ocr)
```

Torch is pinned to the stable 2.10.0 cu128 build in the `Dockerfile` (RTX 50xx needs CUDA 12.8).
Page concurrency is `OCR_PAGE_CONCURRENCY` (default 1).
