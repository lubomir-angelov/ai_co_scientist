# octo_agent (orchestrator)

An OctoTools-style agent: an `Initializer` loads tools, a `Planner` picks sub-goals and
tools, an `Executor` generates and runs tool commands, `Memory` is the per-run scratchpad,
and the `Solver` loop ties them together (`src/solver.py`, `src/models/`).

Tools live in `src/tools/<name>/tool.py` and are discovered by class name:

| Tool | Wraps |
|---|---|
| `Document_Parser_OCR_Tool` | OCR service `POST /ocr/extract` |
| `Memory_Graph_Tool` | Memory service: `search`, `changes`, `record_step`, `record_hypothesis`, `ingest_paper` |

Configuration (the single source is `RuntimeConfig.from_env()` in `src/runtime_config.py`):
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `OCR_BASE_URL`, `OCR_AUTH_HEADER`,
`OCR_REQUEST_TIMEOUT_SECONDS`, `MEMORY_BASE_URL`, `MEMORY_REQUEST_TIMEOUT_SECONDS`.

> **Status:** the HTTP entrypoint (`src/agent_loop.py`) the Dockerfile expects doesn't exist
> yet, so the compose service sits behind the `agent` profile. See `STATUS.md`.

## Development

The virtualenv lives at `~/venvs/ai_cosc_orchestrator`.

```bash
cd services/octo_agent
make install-test   # venv + deps + test deps
make test           # unit tests
make lint           # ruff
make fmt
make help           # all targets
```

Integration checks against running services:

```bash
make test-llm       # LLM_URL (default http://localhost:8000), LLM_MODEL
make test-ocr       # OCR_URL (default http://localhost:8002)
```

Running the solver CLI:

```bash
make run-solver ARGS='--enabled_tools all --output_types final,direct \
  --question "Summarise what we know about microring Q factors."'
```

Manual checks for a single tool:

```bash
cd services/octo_agent
PYTHONPATH=src:../common/src ~/venvs/ai_cosc_orchestrator/bin/python -m tools.document_parser_ocr.tool
PYTHONPATH=src:../common/src ~/venvs/ai_cosc_orchestrator/bin/python -m tools.memory_graph.tool
```

## Paper ingestion

`src/paper_ingest/` (`python -m paper_ingest {ocr|ingest|status}`) OCRs a corpus of PDFs and
ingests them into memory as page-section episodes. It is deterministic tool orchestration,
not an LLM planning loop: the OCR model and the reasoning LLM cannot share the GPU on
consumer hardware, so the batch runs in two phases with the GPU tenant swapped between them,
and it is resumable — a crash or a `Ctrl-C` loses at most the one paper in flight.

**One-time pre-run step.** Before ingesting a real corpus, wipe any test data already in the
memory graph so publication dates stay honest (episode identity includes the title and date,
so re-ingesting under a different date creates a second, differently-dated copy rather than
replacing the first — see "Known issues" in `STATUS.md`):

```bash
docker compose exec falkordb redis-cli GRAPH.DELETE photonic_memory
make memory-down && make memory-up   # restart so Graphiti rebuilds its indices
```

**Phase 1 (GPU = OCR).** For every PDF in `INPUT_DIR`, calls `Document_Parser_OCR_Tool`,
caches the validated `OCRResponse` JSON under `<work-dir>/ocr/<paper_id>.json`, and records
`ocr.status` in `<work-dir>/state/<paper_id>.json`. Requires the LLM gateway to be down (the
root target stops it first).

**Phase 2 (GPU = LLM + memory).** For every paper whose OCR is done, resolves the title (and,
absent a filename-derived date, the publication date) from page 1 via a structured LLM call
grounded against the page text, then calls `Memory_Graph_Tool` `ingest_paper` with every page
section (never `FullText`, which would duplicate every page). Metadata is resolved once and
reused on every retry, because it is part of the memory episode's identity hash. Requires OCR
to be down and the LLM + memory to be up (the root target sequences this).

```bash
make papers-ocr INPUT_DIR=/path/to/pdfs EXCLUDE='skip-this.pdf another.pdf'
make papers-ingest
make papers-status   # read-only; safe to run anytime, including mid-run
```

**paper_id and dates:**
- An arXiv-style filename (`YYMM.NNNN[N][vN].pdf`, new scheme, YY ≥ 07) becomes
  `arxiv:YYMM.NNNN`, with `published_at` at **month precision**
  (`datetime(2000+YY, MM, 1, tzinfo=UTC)`) — a documented precision convention for "first
  submitted this month", not a claimed day. The LLM is not asked for a date in this case.
- Any other filename becomes `file:<stem>` (stem unchanged), and phase 2 asks the LLM for the
  title and, if shown on page 1, the publication date — accepted only when it appears
  verbatim on the page (NFKC + casefold + whitespace-insensitive match). A missing or
  ungrounded title fails that paper rather than falling back to the filename as a title.
- `doc_id` sent to OCR is always `paper_id`, so the same id is used end to end.

**Resume and failure handling:** each paper's stage status lives in
`<work-dir>/state/<paper_id>.json`. Re-running a phase skips papers already `done` and
retries ones that `failed`. Most per-paper failures (bad content, a contract violation, an
ungrounded date) are recorded and the run continues; a service timeout/connection-refused, or
a 502/503/504, aborts the whole run immediately (retrying would queue behind
already-in-flight work or fail identically for every remaining paper).

**Exit codes:** `0` when every paper in scope is `done`; `1` when the run finished with any
`failed`/`blocked` paper (the logged summary lists each one with its full error); an aborted
or preflight-failed run propagates as an exception (non-zero, with a traceback).

**Expected duration for a large corpus** (measured on this stack, 44 s/page OCR,
~120 s/page ingest): phase 1 ≈ pages × 44 s; phase 2 ≈ pages × 120 s. For ~2,200 pages that is
roughly a day of OCR followed by roughly three days of ingest — `make papers-status` is the
way to check progress without interrupting a multi-day run.
