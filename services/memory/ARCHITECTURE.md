# 1. Ontology tuned to silicon photonics / optical / quantum papers

Think of the memory as “everything I’ve read & thought about photonics so far”:

## 1.1 Core entities

These will be the entity_types in Graphiti:

- paper
```bash
paper_id (e.g. arXiv:2501.12345)
title
venue
year
doi / url
```

- author
```bash
name
affiliation
```

- concept
```bash
“microring resonator”
“phase change material”
“Q factor”
“Mach–Zehnder interferometer”
“boson sampling”, “dual-rail encoding”, etc.
```

- device / architecture
```bash
“thermo-optic microring modulator”
“silicon-nitride waveguide lattice”
“time-multiplexed photonic neural network layer”
```

- result / claim
```bash
A statement with numbers, e.g.
Q = 1.2e6 at 1550 nm,
energy/bit = 5 fJ,
fidelity = 0.92 for 4-qubit circuit.
```

- dataset / benchmark (if papers use standard datasets / tasks)
```bash
e.g. “MZI-MNIST”, “synthetic Ising instances”, “VQE on H2”
```

- note / question
```bash
personal notes (“Why do they assume X?”, “Compare to Shen 2017”)
```

## 1.2 Episode types

### Episodes are “things that happened in your reading process”:
```bash
paper_ingest – you parse a PDF and push each section/paragraph.
paper_summary – LLM makes a section or whole-paper summary.
paper_claims – extracted claims / results.
user_note – your own comment on a passage.
qa_turn – a Q/A or explanation you asked the system.
```

### All of them are ingested as Graphiti episodes, which then create entities & edges:
```bash
(paper) -[MENTIONS]-> (concept)
(paper) -[USES_DEVICE]-> (device)
(paper) -[REPORTS_RESULT]-> (result)
(note) -[ABOUT]-> (concept|paper|device)
(paper) -[CITES]-> (paper)
(result) -[IMPROVES_ON]-> (result) (temporal performance progression)
```

### Edges have:
```bash
valid_at = when this claim/result became “true” (publication date)
invalid_at = if later contradicted or superseded
episodes = which ingest/summary/note created this edge
fact = natural language statement (Graphiti’s fact field)
```

# 2. Domain-specific episode write: “paper ingest” + “note”

We’ll define shared models around papers, then implement them with Graphiti+FalkorDB.

## 2.1 Shared models (go in shared_library)
- PaperMeta
- PaperSectionEpisodeIn
- PaperNoteEpisodein
- ConceptQuery
- MemoryFact
- GenericInterface
# 3. Graphiti + FalkorDB implementation (stays in memory_service)
## 3.1 Graphiti client (Falkor backend)
## 3.2 Paper memory backend: adding sections & notes
# 4. Graphiti queries for concept / topic retrieval

Now the key part: “What do we know about X?”

## 4.1 Search all facts about a concept / topic

Example user queries:

- “microring resonator thermal tuning”
- “integrated quantum photonics with time-bin encoding”
- “optical neural networks using phase-change materials”

We’ll use Graphiti’s hybrid search() over the graph; each result is an EntityEdge (a fact).
Use cases:

```
“Summarise what we know about microring resonators for ONNs”:
ConceptQuery(query_text="microring resonator optical neural network")

“As of 2023-01-01, what were the reported best energy/bit for PCM photonics?”:
time_filter_as_of=datetime(2023,1,1, tzinfo=UTC)
```

The planner can then synthesize these MemoryFacts into a structured answer.

# 5. Where to put what (re-answering your question)

Keep the split like this:

## In shared_library (reusable, no dependency on Graphiti/Falkor)

### Pydantic models:

```
PaperMeta, PaperSectionEpisodeIn, PaperNoteEpisodeIn
ConceptQuery, MemoryFact
```

### Abstract interface:
```
PaperMemoryBackend (add_paper_section, add_paper_note, search_concepts)
```

### The MemoryTool card definition (the function schema the LLM sees) that wraps PaperMemoryBackend.

So all other services (reader, planner, explainer) just see:
```
backend: PaperMemoryBackend
await backend.add_paper_section(...)
await backend.search_concepts(...)
``` 

## In memory_service (implementation details, Graphiti/Falkor-specific)
### GraphitiClient configuration:

Falkor URI, graph name, provider config

### GraphitiPaperMemoryBackend that:
```
calls Graphiti.add_episode() for sections & notes
calls Graphiti.search() to implement search_concepts
```

Any low-level search recipes, Cypher, recipes you use later.

## Why structure it this way?

If in 6 months we decide “I want Zep Cloud instead of self-hosted Graphiti”, you only rewrite the PaperMemoryBackend implementation inside memory_service.

The rest of the co-scientist (reader agents, planner, UI) keep working unchanged, since they depend only on the shared_library types.