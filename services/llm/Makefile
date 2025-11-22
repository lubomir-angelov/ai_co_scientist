# LLM service Makefile (services/llm)
# Controls vLLM + API-key gateway via docker compose

SHELL := /bin/bash
COMPOSE := docker compose
COMPOSE_FILE := docker-compose.yml
PROJECT := ai-co-llm

# Defaults (can be overridden via environment or .env)
LLM_MODEL ?= deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
LLM_API_KEY ?= local-llm
BASE_URL ?= http://localhost:9000/v1

# ---- Helpers ---------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nTargets:\n"} /^[a-zA-Z0-9_\-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.env: .env.example ## Initialize .env if missing
	@[ -f .env ] || (echo "Creating .env from .env.example"; cp .env.example .env)

# ---- Lifecycle -------------------------------------------------------------

.PHONY: up
up: .env ## Build and start the LLM stack (gateway + vLLM)
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
logs-llm: ## Tail vLLM logs only
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
		-d '{"model":"Corianas/DeepSeek-R1-Distill-Qwen-14B-AWQ","messages":[{"role":"user","content":"List 3 safe Python refactors."}]}' \
		$(BASE_URL)/chat/completions | jq .

.PHONY: smoke
smoke: ## Run scripts/smoke_llm.py using OpenAI client (BASE_URL, API KEY)
	@LLM_BASE_URL=$(BASE_URL) LLM_API_KEY=$(LLM_API_KEY) LLM_MODEL=$(LLM_MODEL) \
		python3 scripts/smoke_llm.py

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
