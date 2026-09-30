# LLM service Makefile (services/llm)
# Controls llama.cpp server + API-key gateway via docker compose.
# Qwen thinking: on by default standalone; override with LLM_REASONING=off make up

SHELL := /bin/bash
COMPOSE := docker compose
COMPOSE_FILE := compose.yaml
PROJECT := ai-co-llm

# Defaults (can be overridden via environment or .env)
LLM_MODEL ?= Qwen3.8-27B-UD-Q4_K_XL
LLM_API_KEY ?= local-llm
BASE_URL ?= http://localhost:9000/v1
PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
RUFF := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)

# ---- Helpers ---------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nTargets:\n"} /^[a-zA-Z0-9_\-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.env: .env.example ## Initialize .env if missing
	@[ -f .env ] || (echo "Creating .env from .env.example"; cp .env.example .env)

# ---- Lifecycle -------------------------------------------------------------

.PHONY: up
up: .env ## Build and start the LLM stack (gateway + llama.cpp)
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) up -d --build

.PHONY: up-fast
up-fast: .env ## Start without rebuild
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) up -d

.PHONY: down
down: ## Stop containers (keep volumes/images)
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) down

.PHONY: restart
restart: ## Restart services
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) restart

.PHONY: ps
ps: ## List service status
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) ps

.PHONY: logs
logs: ## Tail combined logs
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) logs -f

.PHONY: logs-llm
logs-llm: ## Tail llama.cpp logs only
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) logs -f llm

.PHONY: logs-gateway
logs-gateway: ## Tail gateway logs only
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) logs -f llm-gateway

# ---- Health & Tests --------------------------------------------------------

.PHONY: nvidia
nvidia: ## Show GPU status inside host (checks NVIDIA setup)
	@nvidia-smi || (echo "nvidia-smi not available"; exit 1)

.PHONY: wait
wait: ## Wait until gateway is healthy
	@echo "Waiting for gateway at $(BASE_URL)/models ..."
	@for i in {1..60}; do \
		curl -s -H "Authorization: Bearer $(LLM_API_KEY)" $(BASE_URL)/models >/dev/null && { echo "OK"; exit 0; }; \
		sleep 2; \
	done; \
	echo "Gateway did not become ready in time" && exit 1

.PHONY: curl-models
curl-models: ## Hit /v1/models through gateway
	@curl -s -H "Authorization: Bearer $(LLM_API_KEY)" $(BASE_URL)/models | jq .

.PHONY: curl-chat
curl-chat: ## Sample chat completion via curl
	@curl -s -H "Authorization: Bearer $(LLM_API_KEY)" -H "Content-Type: application/json" \
		-d '{"model":"$(LLM_MODEL)","messages":[{"role":"user","content":"List 3 safe Python refactors."}]}' \
		$(BASE_URL)/chat/completions | jq .

.PHONY: smoke
smoke: ## Run scripts/smoke_llm.py using OpenAI client (BASE_URL, API KEY)
	@test -x $(PY) || { echo "No virtualenv at $(CURDIR)/$(VENV); run 'make install' first"; exit 1; }
	@LLM_BASE_URL=$(BASE_URL) LLM_API_KEY=$(LLM_API_KEY) LLM_MODEL=$(LLM_MODEL) \
		$(PY) scripts/smoke_llm.py

.PHONY: install
install: ## Create $(VENV) with the smoke-test client and ruff
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q openai ruff==0.15.12

.PHONY: lint
lint: ## ruff check the gateway and scripts
	$(RUFF) check src scripts

.PHONY: fmt
fmt: ## ruff format + safe fixes
	$(RUFF) format src scripts
	$(RUFF) check --fix src scripts

.PHONY: build
build: ## Build images
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) build

# ---- Maintenance -----------------------------------------------------------

.PHONY: pull
pull: ## Pull latest images
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) pull

.PHONY: rebuild
rebuild: ## Force rebuild gateway image
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) build --no-cache llm-gateway

.PHONY: clean
clean: ## Stop and remove containers, networks, anonymous volumes
	$(COMPOSE) -p $(PROJECT) -f $(COMPOSE_FILE) down -v

.PHONY: prune
prune: ## Remove dangling images (CAUTION)
	@docker image prune -f
