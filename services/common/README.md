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
# go to the common service root folder from the root of the repo
cd services/common

# get help
make help

# install all requirements (incl. tests)
make install

# run tests
make test

# build
make build 
```
