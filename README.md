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

## Ingesting papers

Batch-loads a directory of PDFs into memory: `octo_agent`'s `Document_Parser_OCR_Tool` OCRs
each paper, then its `Memory_Graph_Tool` extracts metadata and ingests it into the knowledge
graph. It runs in two phases because the LLM and OCR models can't share the 32 GB GPU (with
both loaded, the LLM drops from ~68 to ~0.25 tok/s): phase 1 stops the LLM and starts OCR;
phase 2 stops OCR and starts the LLM + memory. Full design, resume/retry semantics and title
extraction rules are in
[`services/octo_agent/README.md`](services/octo_agent/README.md#paper-ingestion) — this
section is only the runbook for kicking a run off and keeping it alive.

**Optional one-time fresh start.** Wipes the memory graph so a prior test run's data doesn't
mix with real ingestion. **Irreversible** — only do this before your first real corpus run:

```bash
docker compose exec falkordb redis-cli GRAPH.DELETE photonic_memory
docker compose restart memory
```

**Foreground.** Runs in the current terminal; stops if the terminal closes:

```bash
make papers-ocr INPUT_DIR="/path/to/pdfs" EXCLUDE='skip-this.pdf'
make papers-ingest
make papers-status
```

**RECOMMENDED — `nohup`.** Runs both phases unattended and survives closing the terminal:

```bash
mkdir -p ~/ai_cosc_paper_ingest
setsid nohup sh -c 'make papers-ocr INPUT_DIR="/path/to/pdfs" EXCLUDE="skip-this.pdf"; make papers-ingest' \
  > ~/ai_cosc_paper_ingest/run.log 2>&1 &
echo $! > ~/ai_cosc_paper_ingest/run.pid
```

The `;` between the two `make` calls is deliberate, not `&&`: `papers-ocr` exits non-zero if
even one paper failed OCR, and phase 2 should still ingest everything that did OCR
successfully — failed papers are simply retried on the next run.

- Monitor: `tail -f ~/ai_cosc_paper_ingest/run.log` or `make papers-status`. Per-phase logs
  also land in `~/ai_cosc_paper_ingest/logs/`.
- Stop: `kill -- -"$(cat ~/ai_cosc_paper_ingest/run.pid)"` — the leading `-` targets the whole
  process group `setsid` started, so the `make` and Python batch under it stop too; a plain
  `kill <pid>` would only stop the outer shell and leave them running. Resume: re-run the same
  command — papers already done are skipped. Check nothing was left behind:
  `ps -o pid,args -g "$(cat ~/ai_cosc_paper_ingest/run.pid)"` (no output means the group is
  gone). Stopping mid-paper may leave the OCR/memory service still processing that request
  server-side — a rerun re-sends it, and memory skips chunks already stored.

**Alternative — `tmux`.** Prefer this when you want to watch the live output instead of
tailing a log:

```bash
tmux new -s ingest
# inside the session: make papers-ocr INPUT_DIR="/path/to/pdfs" EXCLUDE='skip-this.pdf'
#                      make papers-ingest
# detach: Ctrl-b d
tmux attach -t ingest   # reattach later
```

**WSL caveat.** The run only continues while the WSL VM keeps running and Windows stays
awake — disable sleep on the host for the duration of a multi-day run.

**Measured timings** (live, RTX 5090, 32 GB GPU, 2026-09-26): OCR ≈ 37 s/page with the GPU to
itself; ingest ≈ 134 s/page. A 20-page paper measured 747 s of OCR and 2688 s of ingest (22
episodes). Example: a ~2,200-page corpus is roughly 23 h of OCR followed by roughly 3.4 days
of ingest. These are measured on this machine, not a guarantee for other hardware.

**Resume and failures, briefly:** re-running a phase skips papers already `done` and retries
ones that `failed`; a single paper's failure is recorded and the run continues with the rest.
A service timeout or a 502/503/504 aborts the whole phase instead (the service may still be
busy) — just rerun to resume. Titles are read from page 1 via the LLM and must appear
verbatim on that page, or the paper fails rather than falling back to the filename; dates come
from an arXiv-style filename or page 1, else are left empty.

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
