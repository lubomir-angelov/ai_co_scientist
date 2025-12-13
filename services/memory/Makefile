# services/memory/Makefile

# ---------- Basic config ----------

BASE_IMAGE ?= python:3.11-slim
IMAGE_TAG  ?= memory-service

CONTAINER_PORT ?= 8005
HOST_PORT      ?= 8005

PYTHON    ?= python
APP_MODULE := memory_service.app:app
HOST      := 0.0.0.0

# FalkorDB config for local dev
FALKORDB_IMAGE           ?= falkordb/falkordb:latest
FALKORDB_CONTAINER_NAME  ?= falkordb-memory
FALKORDB_PORT            ?= 6379

# repo root (two levels up from services/memory)
REPO_ROOT  := $(abspath $(PWD)/../..)
SERVICE_DIR := services/memory

# add these at the top of the Makefile
PWD := $(shell pwd)
# Adjust PYTHONPATH so local imports work if needed
export PYTHONPATH := $(PWD):$(PWD)/../shared_library:$(PYTHONPATH)


# ---------- Help ----------

.PHONY: help
help:
	@echo "make install        - install memory service + shared_library into current venv"
	@echo "make run            - start FalkorDB (docker) and run uvicorn locally on $(HOST):$(HOST_PORT)"
	@echo "make run-falkordb   - start FalkorDB docker container only"
	@echo "make docker-build   - build docker image for memory service"
	@echo "make docker-run     - run docker container for memory service"
	@echo "make test           - run pytest"
	@echo "make fmt            - run ruff format + ruff check"


# ---------- Install ----------

.PHONY: install
install:
	$(PYTHON) -m pip install -r requirements.txt
	[ -f requirements_test.txt ] && $(PYTHON) -m pip install -r requirements_test.txt || true
	@if [ -d "../common" ]; then \
	  cd ../common && $(PYTHON) -m pip install -e . ; \
	fi
	# optional: install ruff for local formatting
	$(PYTHON) -m pip install ruff


# ---------- FalkorDB (local, via Docker) ----------

.PHONY: run-falkordb
run-falkordb:
	@echo "Ensuring FalkorDB container '$(FALKORDB_CONTAINER_NAME)' is running on port $(FALKORDB_PORT)..."
	@if ! docker ps --format '{{.Names}}' | grep -q '^$(FALKORDB_CONTAINER_NAME)$$'; then \
	  if docker ps -a --format '{{.Names}}' | grep -q '^$(FALKORDB_CONTAINER_NAME)$$'; then \
	    echo "Starting existing FalkorDB container $(FALKORDB_CONTAINER_NAME)..."; \
	    docker start $(FALKORDB_CONTAINER_NAME) >/dev/null; \
	  else \
	    echo "Running new FalkorDB container $(FALKORDB_CONTAINER_NAME)..."; \
	    docker run -d --name $(FALKORDB_CONTAINER_NAME) -p $(FALKORDB_PORT):6379 $(FALKORDB_IMAGE) >/dev/null; \
	  fi \
	else \
	  echo "FalkorDB container $(FALKORDB_CONTAINER_NAME) already running."; \
	fi


# ---------- Run locally ----------

.PHONY: run
run: run-falkordb
	MEMORY_GRAPHITI_URI=falkor://localhost:6379 \
	MEMORY_GRAPH_NAME=photonic_memory \
	MEMORY_LLM_PROVIDER=openai \
	MEMORY_EMBEDDING_PROVIDER=openai \
	$(PYTHON) -m uvicorn $(APP_MODULE) --host $(HOST) --port $(HOST_PORT) --reload


# ---------- Docker image ----------

.PHONY: docker-build
docker-build:
	cd $(REPO_ROOT) && \
	docker build \
	  --build-arg BASE_IMAGE="$(BASE_IMAGE)" \
	  -t "$(IMAGE_TAG)" \
	  -f $(SERVICE_DIR)/Dockerfile .

.PHONY: docker-run
docker-run:
	docker run -it --rm \
	  -p $(HOST_PORT):$(CONTAINER_PORT) \
	  -e MEMORY_GRAPHITI_URI=falkor://falkordb:6379 \
	  -e MEMORY_GRAPH_NAME=photonic_memory \
	  -e MEMORY_LLM_PROVIDER=openai \
	  -e MEMORY_EMBEDDING_PROVIDER=openai \
	  "$(IMAGE_TAG)"


# ---------- Tests & formatting ----------

.PHONY: test
test:
	$(PYTHON) -m pytest -v tests

.PHONY: fmt
fmt:
	ruff format .
	ruff check .
