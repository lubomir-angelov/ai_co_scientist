# services/memory/Makefile

PYTHON ?= python

IMAGE_TAG ?= memory-service
HOST_PORT ?= 8005
HOST      := 0.0.0.0

# FalkorDB for local development
FALKORDB_IMAGE          ?= falkordb/falkordb-server:v4.20.7
FALKORDB_CONTAINER_NAME ?= falkordb-memory
FALKORDB_PORT           ?= 6379

# Local LLM / embeddings (host ports published by the root docker-compose.yml)
MEMORY_LLM_BASE_URL       ?= http://localhost:9000/v1
MEMORY_LLM_MODEL          ?= Qwen3.8-27B-UD-Q4_K_XL
MEMORY_EMBEDDING_BASE_URL ?= http://localhost:8006/v1

PWD       := $(shell pwd)
REPO_ROOT := $(abspath $(PWD)/../..)
export PYTHONPATH := $(PWD)/src:$(PWD)/../common/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install        - install service + test deps and shared_library into current venv"
	@echo "make run-falkordb   - start a local FalkorDB container on port $(FALKORDB_PORT)"
	@echo "make run            - start FalkorDB and run the service with reload on $(HOST):$(HOST_PORT)"
	@echo "make test           - run unit tests (no FalkorDB / LLM needed)"
	@echo "make fmt            - ruff format + ruff check"
	@echo "make docker-build   - build the service image (context: repo root)"
	@echo "make health         - query /health on localhost:$(HOST_PORT)"

.PHONY: install
install:
	$(PYTHON) -m pip install -r ../common/requirements.txt -r requirements.txt -r requirements_test.txt
	$(PYTHON) -m pip install --no-deps -e ../common -e .

.PHONY: run-falkordb
run-falkordb:
	@if docker ps --format '{{.Names}}' | grep -q '^$(FALKORDB_CONTAINER_NAME)$$'; then \
	  echo "FalkorDB container $(FALKORDB_CONTAINER_NAME) already running"; \
	elif docker ps -a --format '{{.Names}}' | grep -q '^$(FALKORDB_CONTAINER_NAME)$$'; then \
	  docker start $(FALKORDB_CONTAINER_NAME) >/dev/null; \
	else \
	  docker run -d --name $(FALKORDB_CONTAINER_NAME) -p $(FALKORDB_PORT):6379 \
	    -e REDIS_ARGS="--appendonly yes" $(FALKORDB_IMAGE) >/dev/null; \
	fi

.PHONY: run
run: run-falkordb
	MEMORY_FALKORDB_HOST=localhost \
	MEMORY_FALKORDB_PORT=$(FALKORDB_PORT) \
	MEMORY_LLM_BASE_URL=$(MEMORY_LLM_BASE_URL) \
	MEMORY_LLM_MODEL=$(MEMORY_LLM_MODEL) \
	MEMORY_EMBEDDING_BASE_URL=$(MEMORY_EMBEDDING_BASE_URL) \
	GRAPHITI_TELEMETRY_ENABLED=false \
	$(PYTHON) -m uvicorn memory_service.app:create_app --factory --host $(HOST) --port $(HOST_PORT) --reload

.PHONY: test
test:
	$(PYTHON) -m pytest -v tests

.PHONY: fmt
fmt:
	ruff format src tests
	ruff check src tests

.PHONY: docker-build
docker-build:
	cd $(REPO_ROOT) && docker build -t "$(IMAGE_TAG)" -f services/memory/Dockerfile .

.PHONY: health
health:
	curl -sf http://localhost:$(HOST_PORT)/health && echo
