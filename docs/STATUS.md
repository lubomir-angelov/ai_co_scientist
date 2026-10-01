# Project Status

_Last updated: 2026-10-01 (branch `feature/voice`)_

## Summary

The infrastructure is in place and verified, except the new `voice` service. The LLM, memory,
OCR and OCR-MCP services run from the per-service compose files, individually or as one stack.
`voice` (Kokoro TTS + faster-whisper STT, port 8007) is implemented and unit-tested but not yet
verified live; `ocr` now stores every result and serves it back, which `voice` reads. Long-term temporal memory
works end to end with the local LLM, and the paper-ingestion pipeline has been run for real:
the graph holds 41 of 41 papers from the `photonic/` corpus folder. The rest of the corpus
(~89 PDFs) is not ingested yet. The missing piece for the agent is the orchestrator's HTTP
entrypoint and its use of memory inside the agent loop.

`feature/voice` continues from the merged `feature/memory`. Per-service `make test` passes:
common 22, memory 41, ocr 18, ocr_mcp 3, octo_agent 118, voice 223 (1 GPU smoke test
deselected).

**Breaking change:** the OCR response contract now requires typed `pages[].blocks[]`, so the 82
cached OCR JSONs in the paper-ingest cache no longer validate. Papers must be re-OCR'd on demand
before listening (`make papers-ocr` is resumable). Doc ids containing whitespace are rejected.

## Services

| Service | State | Verified |
|---|---|---|
| `llm` + `llm-gateway` | ✅ Working | Live: `Qwen3.8-27B-UD-Q4_K_XL`, ctx 262144, `-np 4 --kv-unified`, `--cache-ram 4096`; ~28.9 GB of 32 GB VRAM |
| `memory` (+ `falkordb`, `embeddings`) | ✅ Working | 41 unit tests; Graphiti 0.30.2 on FalkorDB graph `photonic_memory`, CPU embeddings (Qwen3-Embedding-0.6B); live ingest of 41 papers; search checked by hand |
| `ocr-mcp` | ✅ Working | 3 unit tests; image builds and container is healthy |
| `ocr` | ✅ Working | 18 unit tests (GPU stack stubbed). Image rebuilt with torch pinned to 2.10.0 cu128; live `/healthz` OK; ~37 s/page with the GPU to itself. Now persists every `OCRResponse` to an OCR-owned document store (`OCR_DOCUMENTS_DIR` volume, atomic writes) and serves `GET /ocr/documents/{doc_id}`; the response carries required typed `pages[].blocks[]` (ref, bbox, full text). New contract and store are not yet re-verified live |
| `voice` | 🚧 Unverified | 223 unit tests (1 GPU smoke test deselected), 6 architecture guard tests. Port 8007; Kokoro-82M TTS + faster-whisper large-v3-turbo `int8_float16` STT, CUDA-only, meant to co-reside with `llm` (VRAM budget <= 3000 MiB; ~3.5 GiB free with the LLM up). **Not verified live:** no image built, real Kokoro/Whisper never loaded, VRAM budget unmeasured, voice + OCR GPU co-residency untested |
| `octo_agent` (orchestrator) | 🚧 Partial | Planner/executor/solver ported; OCR and memory tools done; resumable two-phase paper ingestion (`src/paper_ingest`); tool and ingest carry OCR `pages`, `DocId` validated at discovery; 118 unit tests. **No HTTP entrypoint** (`src/agent_loop.py` does not exist), so the compose service is opt-in (`make agent-up`) and will crash until one exists |
| `common` | ✅ Working | 22 tests: `DocId`/`OCRBlock`/`OCRPage` and required `OCRResponse.pages` contract; shared `atomic_files` helper |

Memory note: `LocalFalkorDriver` in `services/memory/src/memory_service/graphiti_client.py`
works around a Graphiti 0.30.2 bug (a bare `_` token from LaTeX in the fulltext query causes a
RediSearch syntax error). 0.30.2 is the latest PyPI release, so the workaround stays until
upstream fixes it.

## Voice

Code: `services/voice`; root compose includes `services/voice/compose.yaml`, root Makefile has
voice targets.

- **Two-step TTS flow.** `POST` prepare a paper by `doc_id` (fetches `GET /ocr/documents/{doc_id}`;
  OCR must be up for this step only) -> stored spoken script. Then render selected
  `section_indices` to per-section MP3 (24 kHz mono, one continuous encoder per file) plus an M3U
  playlist under `data/voice`, resumable and idempotent; or stream a section or free text as
  chunked MP3.
- **What is spoken.** Tables, figures, display equations and captions are omitted by OCR block
  type (`BLOCK_POLICY`). Citation numbers are spoken (no heuristic stripping).
- **STT.** `POST /v1/transcriptions?language=<code>` with a raw audio body.
- **Reproducibility.** Model weights pinned in `model_pins.json` and baked at image build
  (`HF_HUB_OFFLINE=1` at runtime); the g2p spaCy wheel sha256 is pinned.
- **Live verification outstanding:** `make -C services/voice build`, `make llm-up`,
  `make -C services/voice up && make -C services/voice test-gpu`.

## Paper ingestion

Code: `services/octo_agent/src/paper_ingest`. Design, resume/retry semantics and metadata rules:
`services/octo_agent/README.md`, "Paper ingestion". Launch recipe: root `README.md`,
"Ingesting papers".

### How to run

Root Make targets (the LLM and OCR cannot share the GPU, so each phase swaps the tenant):

- `make papers-ocr` - stop LLM, start OCR, OCR every PDF into the cache.
- `make papers-ingest` - stop OCR, start LLM + memory, extract metadata, ingest.
- `make papers-all` - both phases; continues to phase 2 even if some OCR failed.
- `make papers-status` - per-paper state.

**Always pass `INGEST_SECONDS_PER_PAGE=900`.** The default (300) is too low and aborted a run.
Command-line make variables propagate to sub-makes through `MAKEFLAGS`, so passing it to
`papers-all` reaches `services/octo_agent/Makefile`.

Work dir: `~/ai_cosc_paper_ingest` (`state/`, `ocr/`, `logs/`). State is per paper: a rerun
skips done papers and retries failed ones. A timeout or a 502/503/504 aborts the phase; rerun
to resume. An exclusive `flock` on the work dir prevents concurrent runs. Launch with
`setsid nohup` and the PID captured via `$$` (root `README.md` recipe).

### Current data state

- Graph `photonic_memory` holds **41/41 papers** from
  `/mnt/c/Users/lubom/OneDrive/Documents/ai_bsu/Literarutre/photonic`: 757 episodes,
  10,693 entities. Dates: 30 fully dated, 5 year-only, 4 undated.
- Not ingested: the PDFs directly in `.../Literarutre` (90 files; ~89 after excluding the
  717-page textbook `Programirane=++Algoritmi-v2015.pdf`).
- The graph was wiped once on 2026-09-26 (test data) before the real run.
- Discovery is non-recursive and `paper_id` is `file:<stem>`. The `photonic/` folder and the
  top-level folder share no filenames, so nothing in the top level collides with done papers.

### Measured timings

- OCR: ~37 s/page with the GPU to itself.
- Ingest: ~250-330 s/page on dense photonics papers, growing with the graph (Graphiti dedupe
  prompts get longer).
- The 41 papers / 421 pages took ~20 h ingest + ~14 h OCR (OCR was doubled by an accidental
  double launch, now prevented by the lock).
- Whether `-np 4` helps at the current graph size is not conclusively measured (early trial
  74 vs 116 s/chunk; later runs ~139 s/episode on a larger graph).
- Plan on roughly 2x the above for ~89 more papers; expect multi-day runs.

### Operational notes

- LLM: a single request may use the full context; Graphiti prompts reach 45k+ tokens, and a
  32k-per-slot trial failed with HTTP 400. Hence ctx 262144 with `-np 4 --kv-unified`.
- `--cache-ram` was 20000 and the host OOM-killed `llama-server` at 21 GB RSS on the 31 GB WSL
  VM; it is now 4096 (`services/llm/compose.yaml`).
- LLM and OCR on one GPU: the LLM drops from ~68 to ~0.25 tok/s. Never run both.
- Metadata: date comes from the arXiv filename, else page 1 via the LLM. Title and date must be
  grounded on page 1 (token-window binding, `month_text` for written months; no word lists).
  Honest rejects (ordinals, CJK dates, month ranges) are documented in the `metadata.py`
  docstring.

## Known issues

- **Orchestrator entrypoint missing.** The Dockerfile runs `src.agent_loop:app`, which doesn't exist.
- **`INGEST_SECONDS_PER_PAGE` default too low.** `services/octo_agent/Makefile` defaults to 300;
  a run aborted on it. Use 900 until the default is raised.
- **ETA shows 0 min** after a paper whose chunks were already stored.
- **Undated papers get `valid_at` = ingest time**, which confuses as-of queries (4 papers today).
- **paper_ingest OCR cache duplicates the OCR document store** (`services/octo_agent/src/paper_ingest`
  vs `services/ocr/src/document_store.py`); two copies of one concern. To be fixed next on this branch.
- **`ocr_mcp` placeholder default:** `doc_id: str = "unknown"`. To be fixed next on this branch.
- **`ruff format` drift in 20 `voice` files** (`make lint` is separate). To be fixed next on this branch.
- **`python-multipart` still listed** in the `ocr` and `octo_agent` requirements. To be fixed next on this branch.
- **`Executor.llm_engine_name` is unused** (dead field).
- **Format debt:** ~7 more files in `services/octo_agent` fail `ruff format --check` (pre-existing;
  `make lint` itself is clean).
- **Contradiction detection depends on the LLM.** Graphiti's LLM decides when a new fact
  invalidates an old one; it's a model judgment, not a rule.
- **Unused graph.** FalkorDB contains an empty `default_db` graph created by Graphiti's driver.
  It's harmless.
- **Re-ingesting a paper under a changed title or a newly-known publication date duplicates
  its episodes.** Episode identity hashes the title and date, and there is no delete API (see
  `services/octo_agent/README.md`, "Paper ingestion").

## Next steps

1. **Ingest the rest of the corpus** (launch via the root `README.md` nohup recipe):
   ```bash
   make papers-all INPUT_DIR="/mnt/c/Users/lubom/OneDrive/Documents/ai_bsu/Literarutre" \
     EXCLUDE="Programirane=++Algoritmi-v2015.pdf" INGEST_SECONDS_PER_PAGE=900
   ```
2. **Raise the `INGEST_SECONDS_PER_PAGE` default** in `services/octo_agent/Makefile`.
3. **Orchestrator HTTP API.** Add `src/agent_loop.py` (`/health`, `/tools`, `/solve` with
   background jobs), then remove the compose `agent` profile. See `ORCHESTRATOR_PLAN.md`.
4. **Memory in the agent loop.** Planner calls `Memory_Graph_Tool` `search`; executor calls
   `record_step` after each step; hypotheses are recorded as versions.
5. **Decide how to date undated papers** so as-of queries are not polluted by ingest time.
6. **Fix the four open follow-ups** listed under Known issues (OCR cache vs document store,
   `ocr_mcp` `"unknown"` default, `voice` format drift, `python-multipart`).
7. **End-to-end smoke test** (no `make smoke` target exists yet; add one): question -> OCR -> memory -> LLM -> answer citing
   memory facts.
8. **Memory hardening:** background ingest jobs with status polling; figure/table ingestion
   from OCR; an explicit contradiction report endpoint; a reviewed delete/supersede API for
   episodes.
9. **Live-verify `voice`:** build the image, bring up LLM + voice, run `make -C services/voice test-gpu`,
   measure VRAM against the 3000 MiB budget, and test voice + OCR co-residency.
10. **Re-OCR the cached papers** (`make papers-ocr`) so they validate against the new contract.
11. **Merge `feature/voice` into `main`** once reviewed.

## How to resume

```bash
make up && make health            # bring the stack up, check every service
make papers-status                # per-paper ingestion state
ls ~/ai_cosc_paper_ingest         # state/, ocr/, logs/, run.pid, run.log
make llm-up memory-up             # LLM + memory are required for queries
curl -s localhost:8005/v1/memory/concepts/search -H 'content-type: application/json' \
  -d '{"query_text": "microring Q factor"}'
```

Dev setup and tests: `make install && make test && make lint`. More: `README.md`,
`DOCKER_COMPOSE.md`, `ORCHESTRATOR_PLAN.md`, `services/memory/README.md`.
