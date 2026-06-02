# AGENTS.md

## Project Overview

`ai_co_scientist` is a local-first AI co-scientist system for reading, digesting, understanding, and reasoning over research papers in silicon photonics, optical processing, semiconductor systems, and quantum computing.

The project is built as a set of standalone microservices coordinated through Docker Compose.

Current service layout:

```text
ai_co_scientist/
├── docker-compose.yml
├── services/
│   ├── octo_agent/
│   │   ├── src/
│   │   │   ├── engine/
│   │   │   ├── tools/
│   │   │   ├── models/
│   │   │   └── solver.py
│   │   ├── Dockerfile
│   │   └── tests/
│   ├── memory/
│   ├── llm/
│   ├── ocr/
│   └── common/
```

The main services are:

* `llm`: local LLM API service, currently intended to expose a local DeepSeek/Qwen-derived model through an OpenAI-compatible interface.
* `ocr`: DeepSeekOCR-based document understanding service for PDFs, images, visual tokens, and paper ingestion.
* `memory`: temporal knowledge graph memory service based on Zep/Graphiti concepts.
* `octo_agent`: OctoTools-inspired orchestration and solver service that uses the LLM, OCR, memory, and other tools.
* `common`: shared library for cross-service contracts, schemas, logging helpers, and utilities.

The project should remain optimized for consumer hardware and local execution.

---

## Core Development Principles

Follow these principles for all changes:

1. Prefer simple, explicit Python over clever abstractions.
2. Keep each microservice independently understandable and runnable.
3. Use loose coupling between services.
4. Share only stable contracts and utilities through `services/common`.
5. Keep service-specific logic inside the owning service.
6. Use Docker Compose as the primary orchestration layer.
7. Use `pyproject.toml` and requirements files for project management.
8. Use `ruff` for linting and formatting.
9. Use robust logging everywhere service boundaries are crossed.
10. Avoid introducing unnecessary external dependencies.
11. Do not introduce Poetry, dotenv libraries, or heavy frameworks unless explicitly requested.
12. Prefer standard library features when they are sufficient.
13. Do not hide errors. Return clear error messages and log diagnostic context.
14. Preserve local-first operation. Do not add mandatory cloud dependencies.

---

## Repository Navigation Rules

When exploring the codebase:

1. Prefer semantic/context search tools when available, such as `context_search`, CCE, or equivalent.
2. Use direct file reads only when:

   * the exact file path is already known;
   * the file must be edited;
   * the exact complete content is required.
3. Avoid reading large files unnecessarily.
4. Do not edit vendored code unless explicitly instructed.
5. Before editing, identify the owning service and expected integration points.
6. Keep diffs focused and minimal.

Recommended exploration order:

```text
1. README / AGENTS.md
2. docker-compose.yml
3. relevant service Dockerfile
4. relevant service pyproject.toml / requirements files
5. service src/ code
6. tests/
7. services/common/
```

---

## Editing Rules

Before making code changes:

1. Determine which service owns the change.
2. Check whether the change requires shared contracts in `services/common`.
3. Keep public interfaces backwards compatible unless explicitly asked to break them.
4. Add or update tests when behavior changes.
5. Keep logging meaningful but not noisy.
6. Do not silently swallow exceptions.
7. Do not add unrelated refactors.
8. Do not reformat unrelated files.
9. Do not introduce new global state unless necessary.
10. Do not store secrets in source code.

When editing multiple services, clearly separate changes by service.

---

## Python Style

Use modern Python with explicit, maintainable structure.

Preferred style:

```python
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel
```

General rules:

* Follow the Zen of Python.
* Use type hints for public functions.
* Use `Path` instead of raw string path manipulation.
* Prefer small functions with clear names.
* Use dataclasses or Pydantic models for structured data.
* Avoid broad `except Exception` unless re-raising or logging with context.
* Do not use mutable default arguments.
* Prefer explicit dependency injection over hidden imports or globals.
* Keep imports sorted and ruff-compatible.
* Avoid circular imports between services and `common`.

---

## FastAPI Rules

For FastAPI services:

1. Keep route handlers thin.
2. Move business logic into service modules.
3. Use Pydantic request and response models.
4. Return structured errors.
5. Add health endpoints.
6. Log request-level failures with enough context to debug.
7. Avoid blocking the event loop with CPU-heavy or GPU-heavy work.
8. Use `asyncio.to_thread` or worker patterns where appropriate.
9. Validate file size, content type, and request shape for ingestion endpoints.
10. Do not leak internal stack traces to API clients.

Recommended endpoint structure:

```text
src/
├── app.py
├── api/
│   └── routes.py
├── core/
│   ├── config.py
│   └── logging.py
├── models/
│   └── schemas.py
└── services/
    └── processor.py
```

---

## Logging Rules

Use structured, service-aware logging.

Every service should log:

* startup configuration summary, excluding secrets;
* dependency readiness;
* request failures;
* external service calls;
* retry attempts;
* model loading progress;
* GPU/device selection where relevant;
* document processing progress where relevant.

Do not log:

* API keys;
* authorization headers;
* full base64 documents;
* full user prompts unless explicitly safe;
* private data from papers or uploaded documents unless needed for debugging and explicitly controlled.

Preferred pattern:

```python
logger = logging.getLogger(__name__)

logger.info("Starting OCR service", extra={"service": "ocr"})
logger.exception("OCR extraction failed", extra={"doc_id": doc_id})
```

---

## Docker and Compose Rules

Docker Compose is the primary orchestrator.

When changing Dockerfiles or Compose files:

1. Keep builds reproducible.
2. Prefer explicit environment variables with sane defaults.
3. Keep service ports consistent.
4. Add healthchecks for long-running services.
5. Do not assume internet access at runtime.
6. Avoid unnecessary image bloat.
7. Use bind mounts only where useful for local development.
8. Keep GPU-related configuration explicit.
9. Do not hardcode host-specific absolute paths.
10. Make services independently buildable where practical.

The root `docker-compose.yml` should coordinate service networking.

Service Dockerfiles should avoid reaching into unrelated service internals except for `services/common` when needed.

---

## Shared Library Rules

The `services/common` package is for stable shared code only.

Good candidates for `common`:

* Pydantic request/response contracts;
* shared error models;
* logging setup helpers;
* HTTP client utilities;
* common constants;
* serialization helpers;
* healthcheck response models.

Bad candidates for `common`:

* service-specific business logic;
* model loading logic;
* OCR implementation details;
* LLM provider-specific logic;
* memory backend implementation details;
* orchestration planning logic.

Do not make `common` a dumping ground.

---

## LLM Service Rules

The `llm` service should expose a local model through a stable API, preferably OpenAI-compatible.

Expected behavior:

* expose `/v1/models` where applicable;
* expose `/v1/chat/completions` where applicable;
* provide a health endpoint;
* support local model path configuration;
* log model loading status;
* support consumer GPU constraints;
* avoid cloud dependency by default.

When changing LLM integration:

1. Preserve compatibility with the `octo_agent` local LLM client.
2. Keep base URLs configurable.
3. Do not hardcode one model unless explicitly requested.
4. Keep timeout handling explicit.
5. Fail clearly when a model is missing.
6. Prefer streaming support only if the rest of the stack handles it.

---

## OCR Service Rules

The `ocr` service is responsible for document and image understanding.

Primary goals:

* process PDFs;
* process images;
* expose OCR/document extraction API;
* preserve layout-aware information where possible;
* support paper ingestion into memory;
* experiment with DeepSeekOCR visual tokens where useful.

Expected implementation qualities:

1. Use clear request and response models.
2. Validate base64 payloads.
3. Handle malformed PDFs gracefully.
4. Support page-level metadata.
5. Log page-level processing failures without crashing the whole job where possible.
6. Use GPU when available, but fail clearly if required resources are missing.
7. Avoid loading the model repeatedly per request.
8. Keep model initialization separate from request handling.
9. Keep concurrency bounded.
10. Avoid unbounded memory growth for large PDFs.

OCR responses should be structured enough for downstream memory ingestion.

Example conceptual response shape:

```text
OCRResponse
├── doc_id
├── sections[]
├── pages[]
└── metadata
```

---

## Memory Service Rules

The `memory` service is intended to provide temporal knowledge graph memory.

The conceptual model is based on Zep/Graphiti-style temporal facts:

* facts have validity windows;
* facts can change over time;
* memory should preserve historical state;
* the agent should be able to ask what changed between versions.

Important temporal fields:

```text
valid_at
invalid_at
created_at
source
confidence
```

When changing memory behavior:

1. Preserve temporal semantics.
2. Do not overwrite historical facts without retaining history.
3. Store source references where possible.
4. Keep paper-derived facts distinguishable from user preferences and agent hypotheses.
5. Keep ingestion idempotent where practical.
6. Make conflict handling explicit.
7. Avoid treating all memory as permanently true.

Useful memory query types:

* current known facts about a topic;
* facts valid at a specific time;
* changes between two hypothesis versions;
* source-backed claims from papers;
* contradictions between papers.

---

## Octo Agent Rules

The `octo_agent` service orchestrates tool usage, planning, solving, and reasoning.

It is based on OctoTools-style concepts:

```text
Initializer
Planner
Memory
Executor
Solver
ToolsRegistry
```

When changing `octo_agent`:

1. Keep the tool interface explicit and schema-driven.
2. Keep LLM calls behind a local engine/client abstraction.
3. Keep OCR, memory, and other services behind tool wrappers.
4. Avoid hardcoding service URLs in business logic.
5. Use environment variables or config objects.
6. Log planner/executor boundaries.
7. Keep solver runs reproducible where possible.
8. Avoid hidden network calls.
9. Keep long-running jobs observable.
10. Prefer small tools with clear input/output schemas.

Tools should be easy to test independently.

---

## Tool Wrapper Rules

Tool wrappers should be thin, typed HTTP clients around service APIs.

Recommended properties:

* explicit request model;
* explicit response model;
* configurable base URL;
* timeout;
* retry policy only when safe;
* clear exceptions;
* structured logging;
* tests with mocked HTTP responses.

Do not put orchestration logic inside low-level tool wrappers.

---

## Testing Rules

Use tests to protect service behavior and contracts.

Preferred test categories:

```text
tests/
├── unit/
├── integration/
└── smoke/
```

Minimum expectations:

1. Unit-test pure logic.
2. Test Pydantic schema validation.
3. Test service clients with mocked responses.
4. Add smoke tests for health endpoints.
5. Add integration tests for service-to-service flows where practical.
6. Avoid tests that require huge model downloads by default.
7. Mark GPU-heavy tests clearly.
8. Keep tests runnable on a developer workstation.

Useful commands should be exposed through Makefiles where possible.

---

## Makefile Rules

Prefer Makefile targets for common workflows.

Useful targets:

```makefile
make up
make down
make build
make logs
make ps
make health
make test
make lint
make format
make smoke
```

Service-level Makefiles may exist, but root-level orchestration should remain convenient.

Make targets should be explicit and readable. Avoid hiding too much logic in dense shell one-liners.

---

## Configuration Rules

Use environment variables for runtime configuration.

Good examples:

```text
LLM_BASE_URL
LLM_MODEL
OCR_BASE_URL
MEMORY_BASE_URL
LOG_LEVEL
MODEL_PATH
DATA_DIR
CACHE_DIR
REQUEST_TIMEOUT_SECONDS
```

Rules:

1. Provide `.env.example` where useful.
2. Do not require `.env` loading libraries.
3. Let Docker Compose pass environment variables directly.
4. Provide sensible defaults for local development.
5. Do not commit secrets.
6. Validate required configuration at startup.

---

## Dependency Rules

Avoid adding dependencies unless necessary.

Before adding a dependency, consider:

1. Can the standard library solve this?
2. Is the dependency maintained?
3. Is it compatible with Docker and GPU images?
4. Does it increase image size significantly?
5. Is it needed in one service only?
6. Can it remain service-local instead of shared?

Do not add:

* Poetry;
* dotenv libraries;
* unnecessary web frameworks;
* unnecessary async frameworks;
* large dependencies for simple utilities.

---

## API Contract Rules

Cross-service contracts should be explicit.

When changing request or response models:

1. Update the relevant Pydantic model.
2. Update service route handling.
3. Update client/tool wrappers.
4. Update tests.
5. Preserve backwards compatibility where possible.
6. Add versioning if a breaking change is unavoidable.

Prefer structured response fields over free-form strings when downstream services need to reason over results.

---

## Error Handling Rules

Errors should be clear, actionable, and logged.

For service APIs:

* return appropriate HTTP status codes;
* include a concise error message;
* include a machine-readable error code where useful;
* avoid leaking internal details.

For internal Python code:

* raise specific exceptions;
* preserve original exception context;
* log failures at service boundaries;
* do not convert all errors to generic strings too early.

---

## Security Rules

Never commit or print secrets.

Sensitive values include:

* API keys;
* tokens;
* private model registry credentials;
* database passwords;
* signed URLs;
* user documents;
* full prompts containing private data.

When adding logs, check that sensitive fields are excluded.

When adding debug endpoints, ensure they do not expose secrets or private documents.

---

## Performance Rules

The system is intended to run on consumer hardware.

Optimization priorities:

1. Avoid repeated model loads.
2. Keep GPU memory usage predictable.
3. Stream or chunk large files where possible.
4. Bound concurrency.
5. Avoid unbounded queues.
6. Avoid loading entire PDFs into memory unnecessarily.
7. Keep Docker images reasonably small.
8. Cache model artifacts intentionally.
9. Add timeouts to service calls.
10. Prefer incremental ingestion workflows.

Do not introduce distributed-system complexity unless clearly needed.

---

## Paper Ingestion Rules

For scientific paper ingestion:

1. Preserve source identity.
2. Preserve page numbers where possible.
3. Preserve section headings where possible.
4. Extract figures and captions when possible.
5. Keep claims linked to source spans.
6. Distinguish paper claims from agent conclusions.
7. Store uncertainty and confidence where available.
8. Preserve contradictions rather than overwriting them.
9. Make ingestion resumable.
10. Make memory population idempotent where possible.

Important domains:

* silicon photonics;
* optical interconnects;
* optical processors;
* photonic integrated circuits;
* semiconductor systems;
* quantum computing;
* processor-on-chip systems.

---

## Code Generation Rules

When generating code:

1. Produce complete, directly usable files or patches.
2. Include imports.
3. Include type hints.
4. Include logging.
5. Include docstrings where helpful.
6. Keep functions small.
7. Avoid placeholders unless unavoidable.
8. Make configuration explicit.
9. Add tests when appropriate.
10. Keep code ruff-compatible.

Do not generate code that assumes unavailable external services unless clearly marked.

---

## Preferred HTTP Client Pattern

Use `httpx` only if it is already part of the service dependencies or explicitly accepted.

For simple internal clients, prefer a small wrapper with:

```text
base_url
timeout
headers
request model
response model
```

All service-to-service calls should have timeouts.

---

## Database and Persistence Rules

When persistence is needed:

1. Keep schema changes explicit.
2. Add migrations if the service uses migrations.
3. Do not mix persistence concerns across services.
4. Keep memory persistence inside `memory`.
5. Keep OCR artifacts inside OCR-owned storage unless promoted to memory.
6. Avoid direct database access from unrelated services.

---

## Documentation Rules

Update documentation when behavior changes.

Good places to document:

* root `README.md`;
* service-level `README.md`;
* `.env.example`;
* Makefile help;
* API examples;
* test/smoke instructions.

Docs should include runnable commands where possible.

---

## Suggested Local Workflow

From the repository root:

```bash
make build
make up
make health
make smoke
make test
make lint
```

If root targets do not exist yet, prefer adding them instead of relying on long manual command sequences.

---

## Suggested Service Health Endpoints

Each HTTP service should expose a simple health endpoint:

```text
GET /health
```

Recommended response:

```json
{
  "status": "ok",
  "service": "ocr",
  "ready": true
}
```

For model-backed services, distinguish process health from model readiness:

```json
{
  "status": "ok",
  "service": "llm",
  "ready": true,
  "model_loaded": true
}
```

---

## Do Not Do These Things

Do not:

1. Add cloud dependencies by default.
2. Add secrets to code.
3. Add Poetry.
4. Add dotenv libraries.
5. Collapse all services into one monolith.
6. Put service-specific logic in `common`.
7. Bypass the local LLM service from `octo_agent`.
8. Bypass the memory service for persistent facts.
9. Repeatedly load large models per request.
10. Introduce hidden network calls.
11. Edit vendored code without explicit instruction.
12. Reformat unrelated files.
13. Add large dependencies for small utilities.
14. Ignore ruff failures.
15. Ignore failing tests.

---

## Agent Behavior Expectations

When acting as a coding agent in this repository:

1. Start by understanding the requested change.
2. Identify the impacted service.
3. Search before editing.
4. Read the exact file before modifying it.
5. Make the smallest correct change.
6. Update tests or add tests when behavior changes.
7. Run or recommend the most relevant validation command.
8. Summarize changes clearly.
9. Report any assumptions.
10. Report any commands that could not be run.

When uncertain, prefer a conservative implementation that preserves existing behavior.

---

## Completion Checklist

Before considering a task complete:

```text
[ ] Change is scoped to the correct service.
[ ] Shared contracts are updated if needed.
[ ] No secrets are introduced.
[ ] Logging is adequate.
[ ] Errors are handled clearly.
[ ] Tests are added or updated if needed.
[ ] Ruff-compatible style is preserved.
[ ] Docker/Compose impact is considered.
[ ] Documentation is updated if behavior changed.
[ ] The final summary includes validation steps.
```

---

## Project Direction

The long-term goal is to evolve this repository into a local AI co-scientist capable of:

* reading scientific papers;
* extracting structured claims;
* understanding figures and visual tokens;
* building temporal research memory;
* comparing hypotheses over time;
* assisting silicon photonics and quantum computing research;
* supporting future semiconductor and processor-on-chip system design workflows.

All implementation choices should support this direction while keeping the system practical, modular, and runnable on local consumer hardware.

