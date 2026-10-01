# services/voice/Makefile - Kokoro TTS + faster-whisper STT (GPU)

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
RUFF    := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)
COMPOSE := docker compose -f compose.yaml

HOST_PORT ?= 8007
VOICE_HOST_DATA_DIR ?= ../../data/voice
export VOICE_HOST_DATA_DIR

export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/../common/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install       - create $(VENV) with light test deps (no torch / kokoro / faster-whisper)"
	@echo "make test          - unit + architecture tests (GPU tests deselected)"
	@echo "make test-gpu      - GPU smoke test inside the running container (real models, VRAM budget)"
	@echo "make lint          - ruff check"
	@echo "make fmt           - ruff format + ruff check --fix"
	@echo "make pin-g2p       - one-time: record the sha256 of the pinned spaCy model wheel"
	@echo "make run           - local uvicorn (needs the GPU runtime deps and baked models)"
	@echo "make build         - build the image (downloads the pinned models; large)"
	@echo "make up / down     - start / stop the voice container"
	@echo "make logs / ps     - compose logs / status"
	@echo "make health        - query /health on localhost:$(HOST_PORT)"
	@echo "make prepare DOC_ID=<id>                   - build the paper script from the OCR document"
	@echo "make render DOC_ID=<id> SECTIONS='0 2 3'   - render sections to MP3"

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements_test.txt ruff==0.15.12

.PHONY: check-venv
check-venv:
	@test -x $(PY) || { echo "No virtualenv at $(CURDIR)/$(VENV); run 'make install' first"; exit 1; }

.PHONY: test
test: check-venv
	$(PY) -m pytest -q tests

.PHONY: test-gpu
test-gpu:
	$(COMPOSE) exec voice python -m pytest -q -p no:cacheprovider -m gpu /workspace/tests/gpu

.PHONY: lint
lint:
	$(RUFF) check src tests scripts

.PHONY: fmt
fmt:
	$(RUFF) format src tests scripts
	$(RUFF) check --fix src tests scripts

.PHONY: pin-g2p
pin-g2p: check-venv
	$(PY) scripts/fetch_models.py pin-g2p

.PHONY: run
run: check-venv
	VOICE_DATA_DIR=$(CURDIR)/$(VOICE_HOST_DATA_DIR) $(PY) -m uvicorn voice_service.main:app --host 0.0.0.0 --port $(HOST_PORT)

.PHONY: build
build:
	$(COMPOSE) build

.PHONY: up
up:
	mkdir -p $(VOICE_HOST_DATA_DIR)
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
	curl -sf http://localhost:$(HOST_PORT)/health && echo

.PHONY: prepare
prepare:
	@test -n "$(DOC_ID)" || { echo "usage: make prepare DOC_ID=<id>"; exit 1; }
	curl -s -X POST http://localhost:$(HOST_PORT)/v1/papers/$(DOC_ID)/script

.PHONY: render
render:
	@test -n "$(DOC_ID)" -a -n "$(SECTIONS)" || { echo "usage: make render DOC_ID=<id> SECTIONS='0 2 3'"; exit 1; }
	curl -s -X POST http://localhost:$(HOST_PORT)/v1/papers/$(DOC_ID)/renders \
	  -H 'Content-Type: application/json' \
	  -d '{"section_indices": [$(shell echo $(SECTIONS) | tr ' ' ',')]}'
