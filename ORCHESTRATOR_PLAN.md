# Orchestrator Plan

The orchestrator (`services/octo_agent`) is the co-scientist's "brain". It plans, calls tools
and synthesises answers. It never does a tool's job itself: OCR, memory and the LLM are
separate services behind thin HTTP tool wrappers. This document describes what exists and
what remains; see `STATUS.md` for the overall project state.

## Architecture

```
                     ┌──────────────────── octo_agent ─────────────────────┐
  question ────────▶ │ Initializer → Planner → Executor → Solver loop      │ ───▶ answer
                     │   (tools)    (sub-goal)  (tool cmd)  (base/final/    │
                     │                                       direct output)  │
                     │ Memory (per-run scratchpad)                         │
                     └───────┬───────────────┬──────────────────┬──────────┘
                             │ HTTP          │ HTTP             │ HTTP
                     ┌───────▼──────┐ ┌──────▼───────┐ ┌────────▼─────────┐
                     │ llm-gateway  │ │ ocr          │ │ memory           │
                     │ :9000 → llm  │ │ :8002        │ │ :8005 Graphiti + │
                     │ (llama.cpp)  │ │ DeepSeek-OCR │ │ FalkorDB         │
                     └──────────────┘ └──────────────┘ └──────────────────┘
```

| Component | Location | State |
|---|---|---|
| LLM engine adapter (`ChatLocalLLM`) | `src/engine/local_llm.py`, `factory.py` | Works; defaults still point at the old DeepSeek model and `llm-gateway:9000` |
| Initializer / Planner / Executor / Memory | `src/models/` | Ported from OctoTools |
| Solver loop + CLI | `src/solver.py` | CLI exists (`make run-solver`) |
| OCR tool | `src/tools/document_parser_ocr/` | Done |
| Memory tool | `src/tools/memory_graph/` | Done and unit-tested: `search`, `changes`, `record_step`, `record_hypothesis` |
| HTTP API (`src/agent_loop.py`) | missing | Dockerfile expects it; compose service is opt-in until it exists |

## How long-term memory is used

The memory service is both a **retrieval tool** for the planner and a **logging sink** for
the executor:

1. **Before planning:** `Memory_Graph_Tool.execute(action="search", query_text=...)` returns
   facts, each with `valid_at` / `invalid_at` and `source_kinds` (paper vs. note vs. agent
   step vs. hypothesis). Use `time_filter_as_of` to ask what was known at a date, and
   `action="changes"` to ask what changed in a window.
2. **After each step:** `record_step(run_id, step_index, sub_goal, tool_name,
   result_summary, succeeded)`. Later runs can then see what was tried and what failed.
3. **Hypotheses:** `record_hypothesis(hypothesis_id, version, statement, ...)`. Each version
   is a new episode, so the graph can diff versions over time.
4. **Papers:** OCR output goes to `POST /v1/memory/paper/ingest`, which chunks it and
   ingests idempotently, so an interrupted ingest can be retried.

## Remaining work (in order)

1. **Engine configuration.** Read `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` from
   `RuntimeConfig` instead of hardcoded defaults. Default to `http://llm-gateway:8000/v1`
   and `Qwen3.8-27B-UD-Q4_K_XL`.
2. **HTTP API.** `src/agent_loop.py` with `GET /health`, `GET /tools`, `POST /solve`, and
   long runs as background jobs with status polling. Then drop the compose `agent` profile.
3. **Memory in the loop.** Call `search` in the planner's query analysis and `record_step`
   after each executor step; fold both into the planner prompts.
4. **Paper pipeline tool.** A tool (or solver step) that sends a PDF through OCR and then
   `paper/ingest`, keeping `doc_id` as `paper_id` for provenance.
5. **End-to-end smoke test.** Question → OCR → memory → LLM → answer, with the answer
   citing memory facts; add it as a `make smoke` target.
6. **Outputs.** Finish the `base` / `final` / `direct` output types, with error handling and
   structured logging at the planner/executor boundaries.

## Design decisions

| Decision | Rationale |
|---|---|
| Services behind tool wrappers | One `BaseTool` interface for OCR, memory and future tools; each is testable with mocked HTTP |
| HTTP between services | Decoupled and debuggable; latency is acceptable for research tasks |
| Contracts in `services/common` | One definition of the request/response models across services |
| Two memories | The per-run scratchpad (`src/models/memory.py`) is fast; the memory service persists across runs, with time awareness |
| Local-first | Every model call goes to local llama.cpp; no cloud dependency |
