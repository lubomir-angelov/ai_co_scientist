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
- `GET /ocr/documents/{doc_id}`: the stored `OCRResponse` for a doc id. 404
  `{"code": "document_not_found"}` when none is stored; 500 `document_integrity_error` when
  the stored file is invalid. Re-OCR of the same doc id replaces the stored document.

Doc ids (`DocId` in `shared_library.data_contracts`) are non-empty and contain no `/` or
whitespace. Documents live in the `OCR_DOCUMENTS_DIR` directory (`/workspace/documents`, the
`ocr-documents` named volume in `compose.yaml`); the service refuses to start if the variable
is unset or the directory is missing or unwritable.

### Contract change: re-OCR of previously cached papers

`OCRResponse.pages` is required and the truncated `metadata.layout_blocks` / `metadata.pages`
previews are gone. OCR JSONs cached before this change (for example
`<INGEST_WORK_DIR>/ocr/<paper_id>.json` from `make papers-ocr`) no longer validate and must be
re-OCR'd on demand (`papers-ocr` is resumable); there is no compatibility path.

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
