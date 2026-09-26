# Memory service

Temporal knowledge-graph memory for the AI co-scientist, built on
[Graphiti](https://github.com/getzep/graphiti) with FalkorDB as the graph store.
Everything runs locally: entity/fact extraction uses the local LLM behind `llm-gateway`,
embeddings come from the `embeddings` service (llama.cpp on CPU), and Graphiti telemetry is disabled.

```text
episode (paper chunk | note | agent step | hypothesis)
   └─> Graphiti: extract entities + facts with the local LLM, embed, dedupe,
       invalidate contradicted facts (valid_at / invalid_at)
         └─> FalkorDB graph "photonic_memory"
```

## Running

From the repo root:

```bash
# one-time: put the embedding model where the embeddings service expects it
mkdir -p models/embeddings
curl -L -o models/embeddings/Qwen3-Embedding-0.6B-Q8_0.gguf \
  https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf

make memory-build
make memory-up        # falkordb + embeddings + memory
make llm-up           # needed for ingestion (Qwen thinking off in the stack)
make health
```

Or run this service on its own with `make -C services/memory up`. It shares the
`ai-co-scientist-network` network, so a separately started llm service is reachable.

Ingesting needs the LLM to be up, because Graphiti calls it for every episode. In a live
test on an RTX 5090 (27B Q4, thinking off), each chunk took about 20–30 s. Search only
needs FalkorDB and the embeddings service.

For local development without Docker for the service itself:

```bash
cd services/memory
make install          # creates services/memory/.venv
make run              # starts falkordb + embeddings via compose, runs uvicorn --reload on :8005
make test             # unit tests; no FalkorDB, LLM or embeddings needed
```

## Configuration

Environment variables use the prefix `MEMORY_` (see `src/memory_service/config.py`).

| Variable | Default | Notes |
|---|---|---|
| `MEMORY_LLM_MODEL` | *(required)* | Model id served by the LLM (llama.cpp router: models-dir entry name) |
| `MEMORY_LLM_BASE_URL` | `http://llm-gateway:8000/v1` | OpenAI-compatible chat endpoint |
| `MEMORY_LLM_API_KEY` | `local-llm` | Gateway key |
| `MEMORY_LLM_STRUCTURED_OUTPUT` | `json_schema` | Use `json_object` if the server rejects `json_schema` |
| `MEMORY_LLM_TEMPERATURE` | `0.6` | |
| `MEMORY_EMBEDDING_BASE_URL` | `http://embeddings:8080/v1` | OpenAI-compatible `/embeddings` |
| `MEMORY_EMBEDDING_MODEL` / `MEMORY_EMBEDDING_DIM` | `Qwen3-Embedding-0.6B` / `1024` | Changing the dimension needs a fresh graph |
| `MEMORY_FALKORDB_HOST` / `MEMORY_FALKORDB_PORT` | `falkordb` / `6379` | |
| `MEMORY_GRAPH_NAME` | `photonic_memory` | One FalkorDB graph per name |
| `MEMORY_MAX_CONCURRENT_EPISODES` | `1` | Graphiti recommends sequential ingestion |
| `MEMORY_CHUNK_MAX_CHARS` | `4000` | Chunk size for `/paper/ingest` |
| `LOG_LEVEL` | `INFO` | |

## API

All endpoints are under `/v1/memory`, except `GET /health`, which returns
`{"status": "ok", "service": "memory", "ready": <graph initialised>, "graph_name": ...}`.

| Method & path | Body | Returns |
|---|---|---|
| `POST /paper/ingest` | `PaperIngestRequest` (paper + OCR sections) | `PaperIngestResponse` |
| `POST /paper/sections` | `PaperSectionEpisodeIn` | `EpisodeAck` |
| `POST /paper/notes` | `PaperNoteEpisodeIn` | `EpisodeAck` |
| `POST /agent/steps` | `AgentStepEpisodeIn` | `EpisodeAck` |
| `POST /hypotheses` | `HypothesisEpisodeIn` | `EpisodeAck` |
| `POST /concepts/search` | `ConceptQuery` | `list[MemoryFact]` |
| `POST /facts/changes` | `FactChangesQuery` | `FactChanges` |

Models live in `services/common/src/shared_library/data_contracts.py`.

```bash
curl -s localhost:8005/v1/memory/paper/ingest -H 'content-type: application/json' -d '{
  "paper": {"paper_id": "arxiv:2105.00001", "title": "Low-loss microring resonators",
            "published_at": "2021-05-01T00:00:00Z"},
  "sections": [{"name": "Results", "text": "We measure an intrinsic Q of 1.2e6 at 1550 nm."}]}'

# what is known now / what was known at a date / including superseded facts
curl -s localhost:8005/v1/memory/concepts/search -H 'content-type: application/json' \
  -d '{"query_text": "microring Q factor", "time_filter_as_of": "2023-01-01T00:00:00Z"}'

# what changed in a window
curl -s localhost:8005/v1/memory/facts/changes -H 'content-type: application/json' \
  -d '{"query_text": "microring Q factor", "since": "2024-01-01T00:00:00Z"}'
```

### Semantics

- **Temporal facts.** Paper facts become valid at the paper's `published_at`; other episodes
  at their `created_at`, or now. The full publication date is included in the text the LLM
  sees. Any fact it still returns without a date gets the episode's reference time, so that
  as-of queries never surface a claim before its paper existed. When a newer episode contradicts a fact, Graphiti sets
  `invalid_at` rather than deleting it. `search` hides invalidated facts unless
  `include_invalidated` is set.
- **Provenance.** Each `MemoryFact` carries `episodes` and `source_kinds`
  (`paper_section`, `paper_note`, `agent_step`, `hypothesis`). This keeps literature claims
  distinguishable from notes and agent conclusions.
- **Idempotency and resumability.** Episode names are derived from identity plus a content
  hash. Re-sending an identical episode returns `created: false` and costs no LLM calls, so an
  interrupted `/paper/ingest` can be retried as-is. Changed text becomes a new episode, and the
  history is kept.
- **Errors.** Errors are structured as `{"error": {"code", "message"}}`: `backend_unavailable`
  and `graph_unavailable` return 503, `model_unavailable` returns 502, and `internal_error`
  returns 500. If FalkorDB is down at startup, the service still starts, reports
  `ready: false`, and retries on the next request.
- **Latency.** Ingestion runs several LLM calls per chunk, and requests stay open until
  extraction finishes. Size client timeouts to match (the octo_agent tool defaults to 600 s).

## octo_agent integration

`services/octo_agent/src/tools/memory_graph/tool.py` (`Memory_Graph_Tool`) wraps the API. Its
actions are `search` and `changes` for the planner, and `record_step` and
`record_hypothesis` for the executor. It reads `MEMORY_BASE_URL` (compose sets
`http://memory:8005`).

---

# Design background

The memory service should is based on the following architecture.

# Zep / Graphiti

Zep is a “memory layer service” for AI agents. Its job is to give an agent durable, queryable memory that survives across long conversations, sessions, and even dynamic business state. It was built for production settings where the agent needs to recall facts about people, processes, and events over time. 
arXiv


Under the hood, Zep runs on Graphiti, which is an open-source temporal knowledge graph engine. Graphiti doesn’t just store “X is true.” It stores what was true, when it became true, and when it stopped being true, using fields like valid_at and invalid_at. That lets the agent ask things like “What did the user prefer last week vs now?” or “What changed in hypothesis v2 compared to v1?” without losing history. 
GitHub


# Why this matters:

Traditional RAG is mostly static doc retrieval.

Agents in the real world need evolving state: conversations, logs of tool calls, business data, experiment results, etc. Zep/Graphiti fuses structured data and unstructured text into a single temporally-aware graph and can retrieve it with hybrid graph/semantic/keyword queries. 


# Performance:

On Deep Memory Retrieval (DMR), which MemGPT used to benchmark itself, Zep hits ~94.8% vs MemGPT’s ~93.4%.

On a harder benchmark (LongMemEval) that stresses long-term, cross-session reasoning, Zep improves accuracy by up to 18.5% and cuts response latency by ~90% compared to baselines. That’s a very “this can run in prod” signal. 


Zep is basically “agent long-term autobiographical + world-state memory with time awareness.”


# It should be able to perform the following tasks:

We treat Zep/Graphiti as a first-class tool card inside OctoTools:

- Add a “MemoryTool” tool card.

Inputs: a query like “retrieve all prior findings related to Hypothesis A about alloy fatigue above 400°C, sorted by most recent.”

Output: a structured bundle of retrieved facts, each tagged with timestamps, provenance (which run / which dataset), and confidence.
This is just another tool as far as OctoTools is concerned, the same way it would talk to a calculator or web search API. 

- Write back into Zep/Graphiti after each step.
After every sub-goal execution, the executor already captures tool_used, inputs, result. Instead of keeping that only in transient context, you also emit an “episode” into Graphiti:

Entities: {experiment_run, dataset, hypothesis, variable, result_summary}

Relationships: (experiment_run -> tested -> hypothesis), (experiment_run -> produced -> measurement), etc.

Temporal edges: valid_at = now, invalid_at = null (or filled later if we learn that result was superseded).
This matches how Graphiti ingests unstructured and structured data over time. 

- Planner conditioning.
Before the planner decides the next step, you let it call the MemoryTool to pull back (a) what's been tried already, (b) what failed, (c) what constraints exist (lab safety rules, cost ceilings, prior conclusions).
That gives OctoTools actual persistent memory across sessions, which it does not natively have today. 


- Temporal reasoning bonus.
Because Zep/Graphiti remembers how beliefs changed over time (“we thought catalyst X worked until 2025-10-12, then we disproved it”), your planner can reason historically. This is huge in research workflows, compliance, audits, reproducibility, etc. Zep was explicitly designed to excel at cross-session synthesis and long-term context maintenance for enterprise scenarios; the exact same trick applies to iterative scientific work. 
arXiv

We want to slot Zep/Graphiti in as OctoTools’ long-term, temporal memory layer. You’d expose it as both:
- a retrieval tool (for the planner),
- and a logging sink (for the executor).

That’s architecturally aligned with how OctoTools expects to interact with external capabilities.
