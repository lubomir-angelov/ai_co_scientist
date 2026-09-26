# octo_agent (orchestrator)

An OctoTools-style agent: an `Initializer` loads tools, a `Planner` picks sub-goals and
tools, an `Executor` generates and runs tool commands, `Memory` is the per-run scratchpad,
and the `Solver` loop ties them together (`src/solver.py`, `src/models/`).

Tools live in `src/tools/<name>/tool.py` and are discovered by class name:

| Tool | Wraps |
|---|---|
| `Document_Parser_OCR_Tool` | OCR service `POST /ocr/extract` |
| `Memory_Graph_Tool` | Memory service: `search`, `changes`, `record_step`, `record_hypothesis` |

Configuration: `LLM_BASE_URL`, `LLM_API_KEY`, `OCR_BASE_URL`, `MEMORY_BASE_URL` (see
`src/runtime_config.py`).

> **Status:** the HTTP entrypoint (`src/agent_loop.py`) the Dockerfile expects doesn't exist
> yet, so the compose service sits behind the `agent` profile. The LLM engine still defaults
> to the old DeepSeek model and URL (`src/engine/`). See `STATUS.md`.

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
