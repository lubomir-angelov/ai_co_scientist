# Root Makefile - ai_co_scientist

.PHONY: help up down build restart logs ps health test lint format ocr-mcp-up ocr-mcp-down ocr-mcp-build memory-up memory-down memory-build

help:
	@echo "make up              - start all services"
	@echo "make down            - stop all services"
	@echo "make build           - build all docker images"
	@echo "make restart         - restart all services"
	@echo "make logs            - follow logs"
	@echo "make ps              - show running containers"
	@echo "make health          - check all service health"
	@echo "make test            - run tests"
	@echo "make lint            - run ruff"
	@echo "make format          - run ruff format"
	@echo "make ocr-mcp-up      - start OCR + OCR MCP service"
	@echo "make ocr-mcp-down    - stop OCR + OCR MCP service"
	@echo "make ocr-mcp-build   - build OCR + OCR MCP images"
	@echo "make memory-up       - start FalkorDB + embeddings + memory service"
	@echo "make memory-down     - stop FalkorDB + embeddings + memory service"
	@echo "make memory-build    - build the memory service image"

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

restart:
	docker compose down
	docker compose up -d

logs:
	docker compose logs -f

ps:
	docker compose ps

health:
	@echo "=== LLM Gateway ===" && \
	curl -sf http://localhost:9000/v1/models > /dev/null && echo "OK" || echo "FAIL"
	@echo "=== OCR ===" && \
	curl -sf http://localhost:8002/healthz && echo "" || echo "FAIL"
	@echo "=== OCR MCP ===" && \
	curl -sf http://localhost:8003/mcp > /dev/null && echo "OK" || echo "FAIL"
	@echo "=== FalkorDB ===" && \
	docker compose exec -T falkordb redis-cli ping 2>/dev/null || echo "FAIL"
	@echo "=== Embeddings ===" && \
	curl -sf http://localhost:8006/health && echo "" || echo "FAIL"
	@echo "=== Memory ===" && \
	curl -sf http://localhost:8005/health && echo "" || echo "FAIL"

test:
	$(MAKE) -C services/ocr test 2>/dev/null || true
	$(MAKE) -C services/common test 2>/dev/null || true
	$(MAKE) -C services/memory test

lint:
	ruff check services/
	ruff check services/ocr_mcp/

format:
	ruff format services/
	ruff format services/ocr_mcp/

# OCR + MCP stack
ocr-mcp-build:
	docker compose build ocr ocr-mcp

ocr-mcp-up:
	docker compose up -d ocr ocr-mcp

ocr-mcp-down:
	docker compose down ocr ocr-mcp

# Memory stack (graph DB + embeddings + service); extraction also needs the llm stack.
memory-build:
	docker compose build memory

memory-up:
	docker compose up -d falkordb embeddings memory

memory-down:
	docker compose stop memory embeddings falkordb
