# Root Makefile - ai_co_scientist
#
# The stack is composed from per-service compose files (see docker-compose.yml).
# Each service also has its own Makefile: make -C services/<svc> help

# Services with Python code, tests and a `make install/test/lint` contract
PY_SERVICES := common memory ocr ocr_mcp octo_agent voice
# Services with a compose file (runnable standalone with `make -C services/<svc> up`)
COMPOSE_SERVICES := llm ocr ocr_mcp memory octo_agent voice

LLM_API_KEY ?= local-llm
export LLM_API_KEY

.PHONY: help up down build restart logs ps health install test lint format \
        agent-up agent-down llm-up llm-down ocr-up ocr-down ocr-mcp-up ocr-mcp-down \
        ocr-mcp-build memory-up memory-down memory-build voice-up voice-down voice-build \
        papers-ocr papers-ingest papers-status papers-all

help:
	@echo "Stack (root docker-compose.yml; Qwen thinking off unless LLM_REASONING=on):"
	@echo "  make up / down         - start / stop llm, ocr, ocr-mcp, memory, voice"
	@echo "  make build             - build all images"
	@echo "  make restart           - down + up"
	@echo "  make logs / ps         - follow logs / show containers"
	@echo "  make health            - check every service endpoint"
	@echo "  make agent-up / down   - start / stop the orchestrator (opt-in 'agent' profile)"
	@echo ""
	@echo "Single services within the stack:"
	@echo "  make llm-up|ocr-up|ocr-mcp-up|memory-up|voice-up  (and matching -down)"
	@echo "  make ocr-mcp-build / memory-build / voice-build"
	@echo ""
	@echo "Development (per-service virtualenvs):"
	@echo "  make install           - create each service's venv ($(PY_SERVICES))"
	@echo "  make test              - run every service's unit tests; fails if any fails"
	@echo "  make lint              - ruff check services/"
	@echo "  make format            - ruff format services/"
	@echo ""
	@echo "Paper ingestion (two-phase, resumable; swaps the OCR/LLM GPU tenant for you):"
	@echo "  make papers-ocr INPUT_DIR=... [EXCLUDE='a.pdf b.pdf']  - Phase 1: OCR every PDF"
	@echo "  make papers-ingest                                    - Phase 2: metadata + memory ingest"
	@echo "  make papers-all INPUT_DIR=... [EXCLUDE='a.pdf b.pdf']  - Phase 1 then phase 2, one invocation"
	@echo "  make papers-status                                    - show per-paper state"

# ---- Stack -------------------------------------------------------------------

up:
	mkdir -p data/voice
	docker compose up -d

down:
	docker compose --profile agent down

build:
	docker compose build

restart: down up

logs:
	docker compose logs -f

ps:
	docker compose --profile agent ps

health:
	@echo "=== LLM Gateway ===" && \
	curl -sf -H "Authorization: Bearer $(LLM_API_KEY)" http://localhost:9000/v1/models > /dev/null && echo "OK" || echo "FAIL"
	@echo "=== OCR ===" && \
	curl -sf http://localhost:8002/healthz && echo "" || echo "FAIL"
	@echo "=== OCR MCP ===" && \
	docker compose exec -T ocr-mcp python -c "import socket; socket.create_connection(('localhost', 8003), 3)" \
	  2>/dev/null && echo "OK" || echo "FAIL"
	@echo "=== FalkorDB ===" && \
	docker compose exec -T falkordb redis-cli ping 2>/dev/null || echo "FAIL"
	@echo "=== Embeddings ===" && \
	curl -sf http://localhost:8006/health && echo "" || echo "FAIL"
	@echo "=== Memory ===" && \
	curl -sf http://localhost:8005/health && echo "" || echo "FAIL"
	@echo "=== Voice ===" && \
	curl -sf http://localhost:8007/health && echo ""

agent-up:
	docker compose --profile agent up -d orchestrator

agent-down:
	docker compose --profile agent stop orchestrator

llm-up:
	docker compose up -d llm llm-gateway

llm-down:
	docker compose stop llm-gateway llm

ocr-up:
	docker compose up -d ocr

ocr-down:
	docker compose stop ocr

ocr-mcp-build:
	docker compose build ocr ocr-mcp

ocr-mcp-up:
	docker compose up -d ocr ocr-mcp

ocr-mcp-down:
	docker compose stop ocr-mcp ocr

memory-build:
	docker compose build memory

memory-up:
	docker compose up -d falkordb embeddings memory

memory-down:
	docker compose stop memory embeddings falkordb

voice-build:
	docker compose build voice

voice-up:
	mkdir -p data/voice
	docker compose up -d voice

voice-down:
	docker compose stop voice

# ---- Development ---------------------------------------------------------------

install:
	@for svc in $(PY_SERVICES); do \
	  echo "=== install: $$svc ==="; \
	  $(MAKE) -C services/$$svc install || exit 1; \
	done

# Runs every suite, then fails if any failed, so one failure doesn't hide the rest.
test:
	@failed=""; \
	for svc in $(PY_SERVICES); do \
	  echo "=== test: $$svc ==="; \
	  $(MAKE) -C services/$$svc test || failed="$$failed $$svc"; \
	done; \
	if [ -n "$$failed" ]; then echo "FAILED:$$failed"; exit 1; fi; \
	echo "All service tests passed"

lint:
	ruff check services/

format:
	ruff format services/

# ---- Paper ingestion (sequences the GPU tenant on the host, then delegates) --------------

papers-ocr:     ## Phase 1: stop LLM, start OCR, OCR all PDFs (INPUT_DIR=..., EXCLUDE=...)
	$(MAKE) llm-down
	$(MAKE) ocr-up
	$(MAKE) -C services/octo_agent papers-ocr

papers-ingest:  ## Phase 2: stop OCR, start LLM + memory, extract metadata and ingest
	$(MAKE) ocr-down
	$(MAKE) llm-up
	$(MAKE) memory-up
	$(MAKE) -C services/octo_agent papers-ingest

# The leading `-` ignores papers-ocr's exit status: it exits non-zero when even one paper
# failed OCR, and phase 2 must still ingest everything that did OCR successfully — failed
# papers are simply retried on a later run. papers-all's own exit status is papers-ingest's.
papers-all:     ## Phase 1 then phase 2 in one invocation (INPUT_DIR=..., EXCLUDE=...)
	-$(MAKE) papers-ocr INPUT_DIR="$(INPUT_DIR)" EXCLUDE="$(EXCLUDE)"
	$(MAKE) papers-ingest

papers-status:  ## Show per-paper ingestion state
	$(MAKE) -C services/octo_agent papers-status
