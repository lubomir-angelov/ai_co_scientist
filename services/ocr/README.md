# OCR service

A [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) FastAPI server for PDFs and
images. It runs in a CUDA 12.8 container, and the model is downloaded into the image at build
time (the image is about 70 GB).

- `GET /healthz`: `{"status", "service": "ocr", "ready"}`. `ready` means the model is loaded.
- `POST /ocr/extract`: takes an `OCRRequest` `{doc_id, content_b64}` (PDF or image bytes)
  and returns an `OCRResponse` with a `FullText` section, one section per page, the full
  typed blocks per page (`pages[].blocks[]`: DeepSeek-OCR's `ref` label, `bbox`, full `text`),
  and page metadata. The response is persisted before it is returned; a failed write is a 500
  `ocr_store_write_failed`.

A second process, `ocr-documents` (same image, **no GPU**, port 8008, the volume mounted
read-only), is the only server of:

- `GET /ocr/documents/{doc_id}`: the stored `OCRResponse` for a doc id. 404
  with an `OcrDocumentError` body (code `NOT_FOUND`) when none is stored; 500 (code `INTEGRITY`)
  when the stored file is invalid. Route and error body are defined once in
  `shared_library.data_contracts` (`OCR_DOCUMENTS_ROUTE`, `OcrDocumentError`). Re-OCR of the same doc id replaces the stored document.
- `GET /healthz`: `{"status", "service": "ocr-documents", "ready"}`.

The GPU `ocr` server only writes (`OcrDocumentWriter`); `ocr-documents` only reads
(`OcrDocumentReader`); both derive the layout through `document_path`. The reader stays up while
the LLM owns the GPU, so paper ingest (both phases) and voice read documents without the OCR
GPU tenant. `tests/test_document_server_is_gpu_free.py` pins that `src/document_server.py`
imports no GPU stack.

Doc ids (`DocId` in `shared_library.data_contracts`) are non-empty and contain no `/` or
whitespace. Documents live in the `OCR_DOCUMENTS_DIR` directory (`/workspace/documents`, the
`ocr-documents` named volume in `compose.yaml`); the service refuses to start if the variable
is unset or the directory is missing or unwritable.

### Contract change: re-OCR of previously cached papers

`OCRResponse.pages` is required and the truncated `metadata.layout_blocks` / `metadata.pages`
previews are gone. OCR JSONs cached by older paper-ingest runs no longer validate, and paper ingest keeps no
cache any more: papers are re-OCR'd on demand into the store (`papers-ocr` is resumable); there is
no compatibility path. The old `~/ai_cosc_paper_ingest/ocr` directory is unread by any code;
operators delete it by hand (`rm -rf ~/ai_cosc_paper_ingest/ocr`).

Contracts live in `services/common/src/shared_library/data_contracts.py`.

## Running

```bash
cd services/ocr
make build     # docker image via compose.yaml (slow the first time)
make up        # ocr on port 8002 (GPU 0) and ocr-documents on port 8008 (CPU)
make health
make health-documents
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
