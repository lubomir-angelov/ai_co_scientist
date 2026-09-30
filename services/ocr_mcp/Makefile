# services/ocr_mcp/Makefile - MCP server exposing the OCR service as tools

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
RUFF    := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)
COMPOSE := docker compose -f compose.yaml

HOST_PORT    ?= 8003
OCR_BASE_URL ?= http://localhost:8002

.PHONY: help
help:
	@echo "make install   - create $(VENV) with service + test deps"
	@echo "make test      - unit tests (OCR service mocked)"
	@echo "make lint      - ruff check"
	@echo "make fmt       - ruff format + ruff check --fix"
	@echo "make run       - run the MCP server locally over stdio"
	@echo "make run-http  - run the MCP server locally over streamable HTTP on :$(HOST_PORT)"
	@echo "make build     - build the image (compose.yaml)"
	@echo "make up / down - start / stop the container (expects ocr on the shared network)"
	@echo "make logs / ps - compose logs / status"

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt -r requirements_test.txt ruff==0.15.12

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
	OCR_BASE_URL=$(OCR_BASE_URL) MCP_TRANSPORT=stdio $(PY) -m src.server

.PHONY: run-http
run-http: check-venv
	OCR_BASE_URL=$(OCR_BASE_URL) MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=$(HOST_PORT) \
	$(PY) -m src.server

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
