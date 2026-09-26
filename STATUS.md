# Project Status

_Last updated: 2026-09-26 (branch `feature/memory`)_

## Summary

The infrastructure is in place and verified. The LLM, memory, OCR-MCP and gateway services
run from the per-service compose files, individually or as one stack. Long-term temporal
memory works end to end with the local LLM. The missing piece is the orchestrator's HTTP
entrypoint and its use of memory inside the agent loop.

## Services

| Service | State | Verified |
|---|---|---|
| `llm` + `llm-gateway` | ✅ Working | Live: model loads, `/v1/models` returns `Qwen3.8-27B-UD-Q4_K_XL`, thinking off in the stack (no reasoning trace) and on by request |
| `memory` (+ `falkordb`, `embeddings`) | ✅ Working | 37 unit tests; live ingest of two papers with the real LLM; as-of, history and change queries return correct results; idempotent re-ingest |
| `ocr-mcp` | ✅ Working | 3 unit tests; image builds and container is healthy |
| `ocr` | ⚠️ Image not rebuilt | 5 unit tests (GPU stack stubbed). The existing image works. Torch is now pinned to stable 2.10.0 cu128 and the pinned dependency set resolves, but the full image rebuild (~70 GB) hasn't been run |
| `octo_agent` (orchestrator) | 🚧 Partial | Planner/executor/solver ported; OCR and memory tools done (5 memory-tool tests). **No HTTP entrypoint**, so the compose service is opt-in (`make agent-up`) and will crash until one exists |
| `common` | ✅ Working | 7 contract tests |

The tooling checks run on this branch:

- `make test` passes (57 tests across 5 services) and `make lint` is clean.
- Every compose file validates, both standalone and via the root.
- `make health` is OK for every service that was running.

## How to run

```bash
make install && make test          # dev setup + all unit tests
make build && make up && make health
```

See the Quick Start in `README.md` and the full guide in `DOCKER_COMPOSE.md`.

## Known issues

- **Orchestrator entrypoint missing.** The Dockerfile runs `src.agent_loop:app`, which doesn't exist.
- **Stale engine defaults.** The octo_agent LLM engine (`src/engine/factory.py`,
  `local_llm.py`) defaults to the old DeepSeek model and `http://llm-gateway:9000/v1`. Inside
  the network the gateway listens on port 8000, and these values aren't read from env yet.
- **GPU contention.** The LLM (27B, 256k context) and OCR both use GPU 0 on a single 32 GB
  card and may not fit together. Lower `--ctx-size` or stop one of them.
- **Contradiction detection depends on the LLM.** Graphiti's LLM decides when a new fact
  invalidates an old one. It worked in the live test once facts carried exact publication
  dates, but it's a model judgment, not a rule.
- **Ingest latency.** Each paper chunk takes about 20–30 s (several LLM calls per chunk), and
  requests stay open until extraction finishes.
- **Unused graph.** FalkorDB contains an empty `default_db` graph created by Graphiti's
  driver. It's harmless.

## Next steps

1. **Orchestrator engine config.** Read `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` from env
   (`RuntimeConfig`) and fix the defaults.
2. **Orchestrator HTTP API.** Add `src/agent_loop.py` (`/health`, `/tools`, `/solve` with
   background jobs), then remove the compose `agent` profile.
3. **Memory in the agent loop.** Planner calls `Memory_Graph_Tool` `search`; executor calls
   `record_step` after each step; hypotheses are recorded as versions.
4. **Paper pipeline.** PDF → OCR → `POST /v1/memory/paper/ingest`, with `doc_id` kept as
   `paper_id`.
5. **Rebuild and verify the OCR image** with the pinned torch (`make -C services/ocr build`),
   then run a live OCR request.
6. **End-to-end smoke test** (`make smoke`): question → OCR → memory → LLM → answer citing
   memory facts.
7. **Memory hardening:**
   - background ingest jobs with status polling, for long papers;
   - figure/table ingestion from OCR;
   - an explicit contradiction report endpoint.
8. **Merge `feature/memory` into `main`** once reviewed.

See `ORCHESTRATOR_PLAN.md` for the orchestrator design and `services/memory/README.md` for the
memory API.
