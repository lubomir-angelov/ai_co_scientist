# ai_co_scientist
An agentic framework for an ai co-scientist. 

Based on the Octotols framework: https://github.com/octotools/octotools

The agent focuses on three main capabilities: 
  1. Deep technical reasoning + math skill
  2. Long context window (to ingest papers, specs, layouts)
  3. Ability to generate and critique code / architectures.
  4. Ability to run consumer-grade hardware.

# Structure

```
ai_co_scientist/
├── docker-compose.yml   # includes services/*/compose.yaml
├── Makefile             # stack + dev targets (make help)
├── STATUS.md            # current status and next steps
├── DOCKER_COMPOSE.md    # compose layout, configuration, troubleshooting
├── models/              # GGUF models (git-ignored): hotswap/ (LLM), embeddings/
└── services/
    ├── llm/             # llama.cpp + API-key gateway
    ├── ocr/             # DeepSeek-OCR service
    ├── ocr_mcp/         # MCP server wrapping the OCR service
    ├── memory/          # Graphiti + FalkorDB temporal knowledge graph
    ├── octo_agent/      # planner / executor / solver + tool wrappers
    └── common/          # shared_library (contracts)
```

## Quick Start

```bash
cp .env.example .env               # optional; the defaults work locally
make install && make test          # per-service venvs + unit tests (no GPU needed)

make build                         # docker images (the OCR image is ~70 GB)
make up                            # full stack, Qwen thinking off
make health

LLM_REASONING=on make up           # same, with thinking on
make llm-up && make memory-up      # just the LLM + memory
make -C services/llm up            # one service standalone (thinking on by default)
make down
```

Prerequisites (GPU setup, model files) are covered in `DOCKER_COMPOSE.md`.

## Services

| Service | Port | Description |
|---------|------|-------------|
| `llm` | 8000 | llama.cpp local LLM (OpenAI-compatible), Qwen3.8 27B |
| `llm-gateway` | 9000 | API-key proxy for the LLM (`Authorization: Bearer local-llm`) |
| `ocr` | 8002 | DeepSeek-OCR document extraction |
| `ocr-mcp` | 8003 | MCP server exposing OCR tools to agents |
| `memory` | 8005 | Temporal knowledge-graph memory (Graphiti) |
| `falkordb` | 6379 | Graph database for memory |
| `embeddings` | 8006 | llama.cpp embeddings (Qwen3-Embedding-0.6B, CPU) |
| `orchestrator` | 8001 | Agent loop (opt-in: `make agent-up`; entrypoint not implemented yet) |

## MCP Servers

The `ocr-mcp` service exposes the following tools via the MCP protocol on `http://localhost:8003/mcp`:

- **`ocr_extract_pdf`** — Extract text from a base64-encoded PDF
- **`ocr_extract_image`** — Extract text from a base64-encoded image
- **`ocr_extract_file`** — Extract text from a PDF or image file on disk
- **`ocr_health`** — Check the health of the underlying OCR service

## Adding to Another Agent (opencode.json)

To connect this MCP server from another opencode project, add this entry to that project's `opencode.json` under the `"mcp"` key:

```json
{
  "mcp": {
    "ocr": {
      "type": "remote",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

If the project already has other MCP servers, merge the `"ocr"` entry into the existing `"mcp"` object:

```json
{
  "mcp": {
    "context-engine": { ... },
    "cvat-sam2": { ... },
    "ocr": {
      "type": "remote",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

Then restart opencode for the changes to take effect.

# Citation

```
@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
```
