# Root Makefile - ai_co_scientist

.PHONY: help up down build restart logs ps health test lint format ocr-mcp-up ocr-mcp-down ocr-mcp-build

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

test:
	$(MAKE) -C services/ocr test 2>/dev/null || true
	$(MAKE) -C services/common test 2>/dev/null || true

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
