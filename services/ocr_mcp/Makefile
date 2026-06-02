# services/ocr_mcp/Makefile

BASE_IMAGE    ?= python:3.12-slim
IMAGE_TAG     ?= ocr-mcp-service

CONTAINER_PORT ?= 8003
HOST_PORT      ?= 8003

PYTHON ?= python3
APP_MODULE := src.server

# repo root (two levels up from services/ocr_mcp)
REPO_ROOT := $(abspath $(PWD)/../..)
SERVICE_DIR := services/ocr_mcp

.PHONY: help
help:
	@echo "make install        - install deps for local development"
	@echo "make run            - run MCP server locally (stdio transport)"
	@echo "make run-http       - run MCP server with streamable-http locally"
	@echo "make docker-build   - build docker image"
	@echo "make docker-run     - run docker container"
	@echo "make test           - run tests"

.PHONY: install
install:
	$(PYTHON) -m pip install -r requirements.txt

.PHONY: run
run:
	MCP_TRANSPORT=stdio $(PYTHON) -m $(APP_MODULE)

.PHONY: run-http
run-http:
	MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8003 $(PYTHON) -m $(APP_MODULE)

.PHONY: docker-build
docker-build:
	docker build \
	  -t "$(IMAGE_TAG)" \
	  -f $(SERVICE_DIR)/Dockerfile .

.PHONY: docker-run
docker-run:
	docker run -it --rm \
	  -p $(HOST_PORT):$(CONTAINER_PORT) \
	  -e OCR_BASE_URL=$(OCR_BASE_URL) \
	  -e MCP_TRANSPORT=streamable-http \
	  -e MCP_HOST=0.0.0.0 \
	  -e MCP_PORT=$(CONTAINER_PORT) \
	  "$(IMAGE_TAG)"

.PHONY: test
test:
	$(PYTHON) -m pytest -v tests 2>/dev/null || echo "No tests directory yet"
