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
