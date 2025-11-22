# AI Co-Scientist Orchestrator Architecture Plan

## System Overview

The orchestrator acts as the **central brain** that coordinates four specialized microservices to implement the "AI co-scientist" workflow:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Agent Loop)                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Planner: Analyze → Decompose → Select Tools               │  │
│  │ Memory: Track state, episodes, hypotheses across runs      │  │
│  │ Executor: Call tools, capture results, handle errors       │  │
│  │ Solver: Main loop integrating all 3 above                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           │                                          │
├──────────────────────────┼──────────────────────────────────────────┤
│   │                      │                      │                   │
│   ▼                      ▼                      ▼                   │
│ ┌────────┐          ┌────────┐          ┌────────┐                │
│ │  LLM   │          │  OCR   │          │ MEMORY │                │
│ │ Gateway│          │Service │          │Service │                │
│ │ :9000  │          │ :8002  │          │ :8003  │                │
│ └────────┘          └────────┘          └────────┘                │
│   (reasoning)      (document             (knowledge              │
│   (planning)        extraction)           graph)                  │
│   (decomposition)                                                 │
│                                                                    │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │         SHARED_LIBRARY (services/common/src)                │ │
│ │    Data contracts, utility functions, type definitions     │ │
│ └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
        │
        └──────────────► Uses /vendor/octotools code (read-only)
                         • Tool definitions & execution
                         • Engine integrations
                         • Advanced reasoning prompts
```

---

## Detailed Component Architecture

### 1. **Orchestrator Service** (`services/orchestrator/`)

**Purpose**: Main agent loop that coordinates all services using OctoTools patterns

**Key Classes** (ported from octotools):

- **Planner**: 
  - Analyzes incoming research task/query
  - Breaks down into sub-goals using LLM
  - Selects appropriate tools (OCR, Memory, Experiments)
  - Generates execution plans
  - **Uses**: LLM Gateway for reasoning

- **Executor**:
  - Executes tool commands (OCR extraction, memory queries, tool invocations)
  - Captures structured results
  - Handles tool-specific error recovery
  - **Integrates with**: OCR Service, Memory Service, external tools

- **Memory** (local state tracker):
  - Tracks current query, files, action history
  - Formats action sequences for context
  - Acts as local scratchpad during single run
  - **Publishes to**: Memory Service (via GraphQL/API) after each step

- **Solver** (main loop):
  - Orchestrates Planner → Executor → Memory cycle
  - Enforces max_steps, max_time, max_tokens limits
  - Generates base/final/direct responses
  - Exposes via FastAPI endpoints
  - **Output types**: 
    - `base`: Direct LLM response (fast, low-reasoning)
    - `final`: Full agentic reasoning with tool calls
    - `direct`: Short, actionable next steps

**FastAPI Endpoints**:
```
POST   /solve              - Run full agent loop on task
GET    /health             - Service health
GET    /tools              - List available tools
POST   /tools/query        - Call specific tool
POST   /memory/recall      - Query long-term memory
POST   /memory/record      - Store episode result
```

**Configuration** (from env vars):
```
LLM_BASE_URL=http://llm-gateway:9000/v1
LLM_API_KEY=<api-key>
OCR_BASE_URL=http://ocr:8002
MEMORY_BASE_URL=http://memory:8003
VENDOR_PATH=./vendor/octotools
```

---

### 2. **LLM Service** (`services/llm/`)

**Purpose**: Multi-step reasoning engine (already mostly done)

**Stack**:
- **Backend**: vLLM (OpenAI-compatible inference)
- **Frontend**: Gateway with authentication

**Reasoning Capabilities**:
- Decomposition (breaking down complex tasks)
- Tool selection (choosing right tools for sub-goals)
- Code generation (for experiments/analysis)
- Fact extraction (from OCR'd documents)
- Verification (checking results make sense)

**Accessed by**: Orchestrator Planner & Executor via HTTP

---

### 3. **OCR Service** (`services/ocr/`)

**Purpose**: Convert documents → structured facts + metadata

**Stack**:
- **Model**: DeepSeek-OCR (already in Dockerfile)
- **Framework**: FastAPI + transformers

**I/O Contract** (from `shared_library.data_contracts`):
```python
OCRRequest:
  - doc_id: str (for tracking provenance)
  - content_b64: bytes (PDF or image, base64-encoded)

OCRResponse:
  - doc_id: str (same as request)
  - sections: List[OCRSection]  # {name, text}
  - tables: List[OCRTable]       # {caption, rows}
  - metadata: dict               # {page_count, language, confidence, ...}
```

**Endpoints**:
```
POST   /ocr/extract        - Extract text/tables from document
GET    /health             - Health check
```

**Key feature**: Compression at extraction time
- Extracts only semantic nuggets (figures, tables, equations)
- Avoids token bloat for long documents
- Provenance tracking (doc_id → source tracking)

---

### 4. **Memory Service** (`services/memory/`)

**Purpose**: Temporal knowledge graph for cross-run persistence

**Stack**:
- **Backend**: Graphiti (temporal graph engine on FalkorDB)
- **LLM Integration**: OpenAI client (for semantic queries + embedding)
- **FastAPI**: Query & ingest interfaces

**Key Concepts** (from Graphiti):
- **Entities**: experiment_run, hypothesis, dataset, measurement, result_summary
- **Relationships**: tested_on, produced, refuted, confirmed
- **Temporal edges**: `valid_at`, `invalid_at` (track when beliefs changed)
- **Queries**: Hybrid (semantic + graph structure + temporal filters)

**I/O Contract** (from `shared_library.data_contracts`):
```python
FactTriple:
  - subject: str (entity)
  - predicate: str (relationship type)
  - object: str (entity)
  - conditions: dict (context, parameters)
  - valid_at: datetime (when this became true)
  - source_doc: str (which run/dataset)
  - evidence_span: str (quote from result)

UpsertFactsRequest:
  - facts: List[FactTriple]
```

**Endpoints**:
```
POST   /v1/memory/episodes    - Log run result as episode
GET    /v1/memory/queries     - Query knowledge graph
POST   /v1/memory/facts       - Upsert facts/beliefs
GET    /v1/memory/timeline    - Get hypothesis evolution over time
```

**Post-execution workflow**:
1. Executor captures: tool_used, inputs, results, timestamp
2. Planner extracts facts: hypothesis, measurement, conditions
3. Orchestrator publishes to Memory Service as episode
4. Graphiti stores with temporal edges: "believed X from T1→T2"
5. Later runs can query: "What worked on Hypothesis A?"

---

### 5. **Shared Library** (`services/common/src/shared_library/`)

**Purpose**: Single source of truth for data contracts, utilities

**Contents**:

- `data_contracts.py`: Pydantic models
  ```python
  - OCRRequest, OCRResponse
  - FactTriple, UpsertFactsRequest
  - (add more as needed: ExperimentResult, ToolCommand, etc.)
  ```

- `provenance.py`: Tracking lineage
  ```python
  - @with_provenance decorator
  - DocumentSource, RunContext
  - Fact generation with evidence_span extraction
  ```

- `timeutils.py`: Temporal helpers
  ```python
  - valid_time_range(valid_at, invalid_at)
  - temporal_filter(facts, after=None, before=None)
  ```

**Import pattern in all services**:
```python
from shared_library.data_contracts import OCRRequest, FactTriple
from shared_library.provenance import with_provenance
```

---

## Execution Flow: Example Research Task

**Task**: "Analyze papers on high-entropy alloys (HEA) and summarize hypotheses about failure modes above 400°C, comparing with past experiments."

### Step 1: Planner Analysis
```
Query: [analyze papers] + [hypotheses] + [400°C failure]
→ Planner calls LLM: "What skills/tools needed?"
→ LLM: "OCR (PDF parsing) + Memory (retrieve past findings) + Reasoning (synthesis)"
→ Planner decomposes:
   1. Fetch all PDFs on HEA from disk/database
   2. OCR → extract: hypothesis statements, measurements, conditions
   3. Memory → retrieve: past HEA experiments, what was tested, results
   4. LLM → synthesize: compare new findings vs. past beliefs
   5. Memory → upsert: new facts with valid_at timestamp
```

### Step 2: Executor Runs Tools
```
Iteration 1:
  Sub-goal: "Extract key facts from Paper_A.pdf"
  Tool: OCR
  Command: tool.execute(doc_id="Paper_A", content_b64=<encoded>)
  Result: {sections=[...], tables=[...], metadata={...}}
  Memory.add_action(step=1, tool="OCR", sub_goal=..., result=...)

Iteration 2:
  Sub-goal: "Retrieve prior HEA experiments at T>350°C"
  Tool: Memory Query
  Command: tool.execute(
    query="SELECT * WHERE (hypothesis CONTAINS 'HEA') 
                          AND (temperature > 350) 
                          ORDER BY recent"
  )
  Result: {facts=[...], timeline={...}}
  Memory.add_action(step=2, tool="MemoryQuery", ...)

Iteration 3:
  Sub-goal: "Compare findings: contradictions? new insights?"
  Tool: LLM Reasoning
  Command: tool.execute(
    context=<OCR + memory results>,
    prompt="Synthesize findings and flag contradictions"
  )
  Result: {synthesis="...", contradictions=[...], new_hypotheses=[...]}
  Memory.add_action(step=3, tool="LLMReasoning", ...)
```

### Step 3: Memory Persistence
```
After each iteration:
  facts_to_store = [
    FactTriple(
      subject="Hypothesis_HEA_HighT",
      predicate="tested_at_temperature",
      object="425C",
      conditions={"material": "CoCrFeNi", "duration_h": 100},
      valid_at=now(),
      source_doc="Paper_A + Experiment_Run_ID",
      evidence_span="Failure occurred in <500h at 425C..."
    ),
    ...
  ]
  memory_service.upsert_facts(UpsertFactsRequest(facts=facts_to_store))
```

### Step 4: Final Response
```
Solver formats output:
  - base_response: Quick LLM answer (fast path)
  - final_response: Full trajectory with reasoning
  - action_history: [action1, action2, action3, ...]
  - conclusion: "3 papers, 2 experiments found. 1 contradiction flagged.
                 New hypothesis: X-phase stability dominates >400C.
                 Recommended next: test Y-element addition."
```

---

## Data Flow Between Services

### OCR → Orchestrator
```
Orchestrator.execute_tool("ocr_extract", ...)
  ↓
HTTP POST /ocr/extract
  ← OCRResponse(sections=[], tables=[], metadata={})
  ↓
Extract facts: for each section/table → (subject, predicate, object)
```

### Orchestrator → Memory (Write)
```
Executor finishes tool execution
  ↓
Memory.add_action(step, tool, sub_goal, command, result)
  ↓
Solver after all steps:
  facts = extract_facts_from_actions(Memory.get_actions())
  ↓
HTTP POST /v1/memory/episodes
  ← Graphiti stores with valid_at=now, invalid_at=null
```

### Orchestrator ← Memory (Read)
```
Planner needs context for next step
  ↓
HTTP POST /v1/memory/queries
  ← Graphiti hybrid search:
    - Semantic: embedding similarity
    - Structure: follow relationships
    - Temporal: filter by valid_at range
  ← Returns: List[FactTriple] with results
```

### Orchestrator ← LLM
```
Planner.analyze_query(...) or Executor.generate_tool_command(...)
  ↓
HTTP POST /v1/chat/completions (via gateway)
  ← JSON response with reasoning + tool selection
```

---

## Implementation Phases

### Phase 1: Scaffolding (done)
- [x] Docker-compose orchestration
- [x] Service Dockerfiles
- [x] Shared data contracts

### Phase 2: Orchestrator Core (in-progress)
- [ ] **Engines**: Port LLM engine adapter (ChatLocalLLM) that talks to gateway
- [ ] **Models**: Planner, Executor, Memory classes (adapted from vendor octotools)
- [ ] **Solver**: Main agent loop
- [ ] **FastAPI**: Expose endpoints
- [ ] **Tool Registry**: Map tool names → execution functions

### Phase 3: Memory Service Integration
- [ ] Implement graph_client.py (Graphiti initialization)
- [ ] Episodes router (POST /episodes → upsert facts)
- [ ] Queries router (POST /queries → hybrid graph search)
- [ ] Temporal query support

### Phase 4: OCR → Planner Integration
- [ ] Fact extraction from OCR sections (NLP for entity recognition)
- [ ] Table interpretation (convert to relationships)
- [ ] Provenance linkage (doc_id → source_doc in FactTriple)

### Phase 5: End-to-End Integration
- [ ] Test full loop: query → OCR → Memory → LLM → store
- [ ] Implement output_types: base / final / direct
- [ ] Add error handling & fallbacks
- [ ] Logging and observability

---

## File Structure (Post-Implementation)

```
services/orchestrator/
├── src/
│   ├── __init__.py
│   ├── agent_loop.py          # FastAPI app + main endpoints
│   ├── runtime_config.py       # Config from env
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── base.py             # EngineLM, CachedEngine (from octotools)
│   │   └── local_llm.py        # ChatLocalLLM adapter
│   ├── models/
│   │   ├── __init__.py
│   │   ├── formatters.py       # Pydantic models (from octotools)
│   │   ├── memory.py           # Memory class (from octotools)
│   │   ├── planner.py          # Planner class (ported from octotools)
│   │   ├── executor.py         # Executor class (ported from octotools)
│   │   └── solver.py           # Solver class (main loop from octotools)
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── ocr_tool.py         # Wrap OCR service as BaseTool
│   │   ├── memory_tool.py      # Wrap Memory service as BaseTool
│   │   └── external_tools.py   # Import tools from vendor/octotools
│   └── utils/
│       ├── __init__.py
│       └── prompts.py          # Planner/Executor prompts
├── Dockerfile
├── requirements.txt
└── pyproject.toml

services/memory/
├── src/
│   ├── __init__.py
│   ├── app.py                  # FastAPI
│   ├── config.py               # Graphiti config
│   ├── graph_client.py         # Graphiti initialization
│   └── routers/
│       ├── episodes.py         # POST /episodes
│       └── queries.py          # POST /queries
├── tests/
├── Dockerfile
├── requirements.txt
└── pyproject.toml

services/common/src/shared_library/
├── __init__.py
├── data_contracts.py           # Pydantic models
├── provenance.py               # Lineage tracking
├── timeutils.py                # Temporal helpers
└── py.typed
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Use vendor/octotools code read-only** | Single source of truth for reasoning logic; no duplication |
| **Wrap services as "tool cards"** | OCR, Memory, external tools all follow same interface (BaseTool) |
| **HTTP between services** | Decoupled, language-agnostic, easy to debug; latency acceptable for research tasks |
| **Temporal edges in Memory** | Tracks hypothesis evolution (when did we believe X? what falsified it?) |
| **Local Memory + persistent Memory** | Local = fast (single run context); persistent = reasoning across runs |
| **Data contracts in shared_library** | One place for OCRRequest, FactTriple, etc.; all services import same types |
| **FastAPI for Orchestrator** | Matches LLM/OCR services; easy to add web UI later |

---

## Success Criteria

1. **Orchestrator can analyze a research task** → Planner decomposes into sub-goals ✓
2. **OCR extracts documents** → Facts with provenance stored locally ✓
3. **Memory Service persists facts** → Temporal knowledge graph queryable ✓
4. **Executor calls tools iteratively** → Results captured and stored ✓
5. **End-to-end run** → Query in → tools called → memory updated → report out ✓
6. **Temporal queries** → "What was believed about Hypothesis X on date Y?" ✓
7. **Multi-run reasoning** → Agent recalls past experiments when planning new ones ✓

---

## Next Steps

Implement in order:
1. **Engines** (ChatLocalLLM adapter)
2. **Models** (Planner, Executor, Memory, Solver ported from octotools)
3. **Agent Loop** (FastAPI endpoints)
4. **Tool Adapters** (OCR, Memory as tool cards)
5. **Memory Service** (Graphiti integration)
6. **End-to-end test**
