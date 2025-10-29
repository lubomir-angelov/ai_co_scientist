# shared_library

Shared Pydantic models and helper utilities used across all services
(orchestrator, ocr, memory, llm).

## Contents
- `data_contracts.py`: request/response schemas for service APIs
- `provenance.py`: helpers for building FactTriple payloads with timestamps
- `timeutils.py`: UTC/ISO time helpers
- `__about__.py`: version string
- `py.typed`: marks this package as typed

## Build / install locally
```bash
cd services/common
python -m build
pip install dist/shared_library-0.1.0-py3-none-any.whl
