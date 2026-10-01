# services/ocr/Makefile - DeepSeek-OCR service (GPU)

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
RUFF    := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)
COMPOSE := docker compose -f compose.yaml

HOST_PORT ?= 8002
DOCS_PORT ?= 8008

export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/../common/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install       - create $(VENV) with light test deps (no torch; GPU libs are stubbed in tests)"
	@echo "make install-full  - add the full GPU runtime deps to $(VENV) (torch, transformers, ...)"
	@echo "make test          - unit tests"
	@echo "make lint          - ruff check"
	@echo "make fmt           - ruff format + ruff check --fix"
	@echo "make run           - run the server locally (needs install-full, a GPU and the model)"
	@echo "make build         - build the image (compose.yaml; large, downloads the model)"
	@echo "make up / down     - start / stop the OCR container"
	@echo "make logs / ps     - compose logs / status"
	@echo "make health        - query /healthz on localhost:$(HOST_PORT)"
	@echo "make health-documents - query the GPU-free ocr-documents reader on localhost:$(DOCS_PORT)"

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r ../common/requirements.txt -r requirements_test.txt ruff==0.15.12

.PHONY: install-full
install-full: install
	$(PY) -m pip install -q -r requirements.txt

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
	TRANSFORMERS_ATTENTION_IMPLEMENTATION=eager \
	TRANSFORMERS_NO_FLASH_ATTENTION=1 \
	$(PY) -m uvicorn src.server:app --host 0.0.0.0 --port $(HOST_PORT) --reload

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
	@curl -sf http://localhost:$(HOST_PORT)/healthz && echo || { echo "ocr not reachable on :$(HOST_PORT)"; exit 1; }

.PHONY: health-documents
health-documents:
	@curl -sf http://localhost:$(DOCS_PORT)/healthz && echo || { echo "ocr-documents not reachable on :$(DOCS_PORT)"; exit 1; }
