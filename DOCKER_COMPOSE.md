# Docker Compose

Docker Compose orchestrates every service, and each service owns its own compose file. The
root `docker-compose.yml` only `include:`s them, so a service can run on its own or as part
of the full stack.

## Layout

| File | Services | Host ports |
|---|---|---|
| `services/llm/compose.yaml` (+ `compose.stack.yaml` in the stack) | `llm` (llama.cpp, CUDA), `llm-gateway` (API-key proxy) | 8000, 9000 |
| `services/ocr/compose.yaml` | `ocr` (DeepSeek-OCR, CUDA) | 8002 |
| `services/ocr_mcp/compose.yaml` | `ocr-mcp` (MCP over streamable HTTP) | 8003 |
| `services/memory/compose.yaml` | `falkordb`, `embeddings` (llama.cpp, CPU), `memory` | 6379, 8006, 8005 |
| `services/octo_agent/compose.yaml` | `orchestrator` (opt-in profile `agent`) | 8001 |

- **Shared network.** Every file uses the network `ai-co-scientist-network`, so services
  started separately still reach each other by service name (e.g. `http://llm-gateway:8000/v1`).
- **Persistent graph.** The FalkorDB volume is always `ai-co-scientist-falkordb-data`,
  whichever way the service is started.
- **No cross-file `depends_on`.** Compose rejects references to services in other files.
  Services tolerate dependencies that start later: memory reports `ready: false` or returns
  `502 model_unavailable` until they are up.
- **Orchestrator is opt-in.** Its HTTP entrypoint (`src/agent_loop.py`) doesn't exist yet,
  so it only starts with `make agent-up`.

## Prerequisites

- Docker with Compose ≥ 2.20 (for `include`) and the NVIDIA container toolkit (see
  `services/README.md`).
- Models on disk (git-ignored):
  - `models/hotswap/Qwen3.8-27B-UD-Q4_K_XL/Qwen3.8-27B-UD-Q4_K_XL.gguf`: main LLM
  - `models/embeddings/Qwen3-Embedding-0.6B-Q8_0.gguf`: embeddings for memory

  ```bash
  mkdir -p models/embeddings
  curl -L -o models/embeddings/Qwen3-Embedding-0.6B-Q8_0.gguf \
    https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf
  ```
- The OCR image downloads DeepSeek-OCR at build time, and the image is about 70 GB.

## Configuration

Copy `.env.example` to `.env` in the repo root (Compose reads it automatically). Key variables:

| Variable | Default | Effect |
|---|---|---|
| `LLM_API_KEY` | `local-llm` | Gateway key, also used by memory |
| `LLM_REASONING` | `off` in the stack, `on` standalone | Qwen thinking: `on` / `off` / `auto` (`auto` means on for Qwen) |
| `MEMORY_LLM_MODEL` | `Qwen3.8-27B-UD-Q4_K_XL` | Must match the llm service's `--alias` |
| `MEMORY_LLM_STRUCTURED_OUTPUT` | `json_schema` | Use `json_object` if structured output fails |
| `MEMORY_GRAPH_NAME` | `photonic_memory` | FalkorDB graph |
| `EMBEDDING_MODEL_FILE` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | Qwen3-Embedding-0.6B / 1024 | Embeddings |

## Commands

From the repo root:

```bash
make build            # build all images (the OCR image is large)
make up               # llm, llm-gateway, ocr, ocr-mcp, falkordb, embeddings, memory
make health           # check every endpoint
make ps / make logs
make down

LLM_REASONING=on make up          # full stack with Qwen thinking on
make llm-up | memory-up | ocr-up | ocr-mcp-up   # parts of the stack (and matching -down)
make agent-up                     # orchestrator (opt-in)
```

Run a single service standalone (it uses its own compose project, on the same shared network):

```bash
make -C services/llm up        # thinking on by default; LLM_REASONING=off make -C services/llm up
make -C services/memory up
make -C services/ocr up
make -C services/ocr_mcp up
```

## GPU budget (single RTX 5090, 32 GB)

The 27B Q4 model with a 256k context uses most of the card on its own. The OCR model also
runs on GPU 0, so running both at once may not fit. Embeddings run on CPU to leave VRAM for
the LLM. In the live check, the LLM at 32k context used about 18 GB on top of 5.7 GB already
used by other containers.

## Endpoints

```bash
# LLM via the gateway (requires the API key)
curl -s -H "Authorization: Bearer local-llm" http://localhost:9000/v1/models
curl -s http://localhost:9000/v1/chat/completions \
  -H "Authorization: Bearer local-llm" -H "Content-Type: application/json" \
  -d '{"model":"Qwen3.8-27B-UD-Q4_K_XL","messages":[{"role":"user","content":"Hello"}]}'

# OCR: body is {"doc_id", "content_b64"} with base64 PDF or image bytes
curl -s http://localhost:8002/healthz
printf '{"doc_id":"paper-1","content_b64":"%s"}' "$(base64 -w0 paper.pdf)" \
  | curl -s http://localhost:8002/ocr/extract -H "Content-Type: application/json" -d @-

# Memory (see services/memory/README.md for the full API)
curl -s http://localhost:8005/health
```

## Troubleshooting

- **The LLM doesn't fit in VRAM.** Check `nvidia-smi`, then lower `--ctx-size` in
  `services/llm/compose.yaml`, or stop OCR.
- **Memory returns `backend_unavailable`.** FalkorDB isn't reachable; check
  `docker compose logs falkordb`. The service retries on the next request.
- **Memory returns `model_unavailable`.** The llm-gateway or embeddings service is down, or
  `MEMORY_LLM_MODEL` doesn't match the served model id (`/v1/models`).
- **Graphiti extraction fails on malformed JSON.** Set `MEMORY_LLM_STRUCTURED_OUTPUT=json_object`.
- **The OCR build fails while resolving torch.** The Dockerfile pins stable torch 2.10.0 cu128.
  Don't switch back to the nightly index.
