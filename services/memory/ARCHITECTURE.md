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