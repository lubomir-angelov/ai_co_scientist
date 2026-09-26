# services/memory/Makefile - Graphiti + FalkorDB temporal memory service

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
RUFF    := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)
COMPOSE := docker compose -f compose.yaml

HOST_PORT ?= 8005

# Local LLM / embeddings / FalkorDB as published on the host by the compose files
MEMORY_LLM_BASE_URL       ?= http://localhost:9000/v1
MEMORY_LLM_MODEL          ?= Qwen3.8-27B-UD-Q4_K_XL
MEMORY_EMBEDDING_BASE_URL ?= http://localhost:8006/v1

export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/../common/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install   - create $(VENV) with service, test and shared_library deps"
	@echo "make test      - unit tests (no FalkorDB / LLM / embeddings needed)"
	@echo "make lint      - ruff check"
	@echo "make fmt       - ruff format + ruff check --fix"
	@echo "make run       - run the API locally with reload (starts falkordb + embeddings via compose)"
	@echo "make build     - build images (compose.yaml)"
	@echo "make up / down - start / stop falkordb + embeddings + memory (compose.yaml)"
	@echo "make logs / ps - compose logs / status"
	@echo "make health    - query /health on localhost:$(HOST_PORT)"

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r ../common/requirements.txt -r requirements.txt -r requirements_test.txt ruff==0.15.12

.PHONY: check-venv
check-venv:
	@test -x $(PY) || { echo "No virtualenv at $(CURDIR)/$(VENV); run 'make install' first"; exit 1; }

.PHONY: test
test: check-venv
	$(PY) -m pytest -q tests

.PHONY: lint
lint:
	$(RUFF) check src tests

.PHONY: fmt
fmt:
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

.PHONY: run
run: check-venv
	$(COMPOSE) up -d falkordb embeddings
	MEMORY_FALKORDB_HOST=localhost \
	MEMORY_LLM_BASE_URL=$(MEMORY_LLM_BASE_URL) \
	MEMORY_LLM_MODEL=$(MEMORY_LLM_MODEL) \
	MEMORY_EMBEDDING_BASE_URL=$(MEMORY_EMBEDDING_BASE_URL) \
	GRAPHITI_TELEMETRY_ENABLED=false \
	$(PY) -m uvicorn memory_service.app:create_app --factory --host 0.0.0.0 --port $(HOST_PORT) --reload

.PHONY: build
build:
	$(COMPOSE) build

.PHONY: up
up:
	$(COMPOSE) up -d

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: logs
logs:
	$(COMPOSE) logs -f

.PHONY: ps
ps:
	$(COMPOSE) ps

.PHONY: health
health:
	@curl -sf http://localhost:$(HOST_PORT)/health && echo || { echo "memory not reachable on :$(HOST_PORT)"; exit 1; }
