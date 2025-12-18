# Orchestrator service Makefile
# Controls agent loop, tool registry, and orchestration logic

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
VENV := ~/venvs/ai_cosc_orchestrator
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
SRC_DIR := $(PWD)/src
PYTHONPATH := $(SRC_DIR):$(PYTHONPATH)

# Services
OCR_URL ?= http://localhost:8002
OCR_PATH ?= /ocr/extract

# Minimal valid 1-page PDF (base64)
SMOKE_PDF_B64 := JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgaHR0cDovL3d3dy5yZXBvcnRsYWIuY29tCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhCi9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nCi9OYW1lIC9GMQovU3VidHlwZSAvVHlwZTEKL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSCi9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0KL1BhcmVudCA2IDAgUgovUmVzb3VyY2VzIDw8Ci9Gb250IDw8Ci9GMSAxIDAgUgo+PgovUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PgovVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUKL1BhZ2VzIDYgMCBSCi9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGF1dG9nZW4pCi9DcmVhdGlvbkRhdGUgKEQ6MjAyNTEyMTMxNjI1NDkrMDInMDAnKQovQ3JlYXRvciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gd3d3LnJlcG9ydGxhYi5jb20pCi9LZXl3b3JkcyAoKQovTW9kRGF0ZSAoRDoyMDI1MTIxMzE2MjU0OSswMicwMCcpCi9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gd3d3LnJlcG9ydGxhYi5jb20pCi9TdWJqZWN0ICgpCi9UaXRsZSAoKQovVHJhcHBlZCAvRmFsc2UKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL0NvdW50IDEKL0tpZHMgWyAzIDAgUiBdCi9UeXBlIC9QYWdlcwo+PgplbmRvYmoKNyAwIG9iago8PAovTGVuZ3RoIDg2Cj4+CnN0cmVhbQpCVAovRjEgMTIgVGYKMTAwIDcwMCBUZAooc21va2UgdGVzdCkgVGoKRVQKZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwOTUgMDAwMDAgbiAKMDAwMDAwMDE1MCAwMDAwMCBuIAowMDAwMDAwMzAyIDAwMDAwIG4gCjAwMDAwMDA0NTMgMDAwMDAgbiAKMDAwMDAwMDUyMiAwMDAwMCBuIAowMDAwMDAwODM5IDAwMDAwIG4gCjAwMDAwMDA5MTIgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgWzw2Y2I0NmIzOGE1YzE3NjM5NDg0MWU2MGQxZDA1ZWIwYz48NmNiNDZiMzhhNWMxNzYzOTQ4NDFlNjBkMWQwNWViMGM+XQovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgoxMDc2CiUlRU9GCg==

LLM_URL ?= http://localhost:8000
MEMORY_URL ?= http://localhost:8005

# Defaults
PROJECT := ai-co-orchestrator

# ---- Helpers ---------------------------------------------------------------

.PHONY: help
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nTargets:\n"} /^[a-zA-Z0-9_\-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---- Virtual Environment ---------------------------------------------------

.PHONY: venv
venv: ## Create virtual environment at ~/venvs/ai_cosc_orchestrator
	@if [ -d "$(VENV)" ]; then \
	    echo "✓ venv already exists at $(VENV)"; \
	else \
	    echo "Creating venv at $(VENV)..."; \
	    python3 -m venv $(VENV); \
	    $(PIP) install --upgrade pip setuptools wheel; \
	    echo "✓ venv created"; \
	fi

.PHONY: install
install: venv ## Install dependencies
	@$(PIP) install -r requirements.txt
	@echo "✓ Dependencies installed"

.PHONY: install-test
install-test: install ## Install test dependencies
	@$(PIP) install -r requirements_test.txt
	@echo "✓ Test dependencies installed"

.PHONY: activate
activate: ## Print activation command for venv
			@echo "source $(VENV)/bin/activate"

# ---- Development -----------------------------------------------------------

.PHONY: shell
shell: venv ## Start Python shell with PYTHONPATH set
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON)

.PHONY: python
python: venv ## Execute Python script with PYTHONPATH set (usage: make python SCRIPT=script.py)
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) $(SCRIPT)

.PHONY: pythonpath
pythonpath: ## Show PYTHONPATH
	@echo "PYTHONPATH=$(PYTHONPATH)"

# ---- Testing ---------------------------------------------------------------

.PHONY: test
test: install-test ## Run all tests
	@PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/ -v

.PHONY: test-registry
test-registry: install-test ## Run tools registry tests
	@PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/test_tools_registry.py -v

.PHONY: test-agent
test-agent: install-test ## Run agent loop tests
	@PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/test_agent_loop.py -v

.PHONY: test-coverage
test-coverage: install-test ## Run tests with coverage report
	@PYTHONPATH=$(PYTHONPATH) $(PYTEST) tests/ -v --cov=src --cov-report=html
	@echo "✓ Coverage report generated in htmlcov/index.html"

.PHONY: test-watch
test-watch: install-test ## Run tests on file changes (requires pytest-watch)
	@$(PIP) install pytest-watch
	@PYTHONPATH=$(PYTHONPATH) ptw tests/ -- -v

# ---- Linting & Formatting --------------------------------------------------

.PHONY: lint
lint: install ## Run linting (flake8, mypy)
	@$(PIP) install flake8 mypy
	@PYTHONPATH=$(PYTHONPATH) flake8 src/ tests/ --max-line-length=100
	@PYTHONPATH=$(PYTHONPATH) mypy src/ --ignore-missing-imports
	@echo "✓ Linting passed"

.PHONY: format
format: install ## Format code with black
	@$(PIP) install black
	@PYTHONPATH=$(PYTHONPATH) black src/ tests/ --line-length=100
	@echo "✓ Code formatted"

.PHONY: format-check
format-check: install ## Check code formatting
	@$(PIP) install black
	@PYTHONPATH=$(PYTHONPATH) black src/ tests/ --line-length=100 --check
	@echo "✓ Formatting check passed"

# ---- Integration -----------------------------------------------------------

.PHONY: run-agent
run-agent: install ## Run agent loop (set TASK env var)
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m src.agent_loop --task "$(TASK)"


.PHONY: test-ocr
test-ocr:
	@echo "Testing OCR service (integration)..."
	@payload="$$(jq -n --arg doc_id "smoke-test" --arg content_b64 "$(SMOKE_PDF_B64)" '{doc_id:$$doc_id, content_b64:$$content_b64}')"; \
	curl -sS --fail-with-body --connect-timeout 2 --max-time 60 \
	  -H "Content-Type: application/json" \
	  --data "$$payload" \
	  "$(OCR_URL)$(OCR_PATH)" \
	| jq -e . >/dev/null \
	&& echo "✓ OCR OK" || echo "✗ OCR failed"

.PHONY: test-llm
test-llm: install
	@echo "Testing LLM service (integration)..."
	@tmp_body="$$(mktemp)"; tmp_hdr="$$(mktemp)"; \
	payload="$$(jq -n \
	  --arg model "Corianas/DeepSeek-R1-Distill-Qwen-14B-AWQ" \
	  --arg msg "ping" \
	  '{model:$$model,messages:[{role:"user",content:$$msg}],temperature:0,max_tokens:8,stream:false}')" ; \
	code="$$(curl -sS --connect-timeout 2 --max-time 120 \
	  -D "$$tmp_hdr" -o "$$tmp_body" \
	  -H "Authorization: Bearer local-llm" \
	  -H "Content-Type: application/json" \
	  --data "$$payload" \
	  "$(LLM_URL)/v1/chat/completions" \
	  -w "%{http_code}" || echo 000)"; \
	if [ "$$code" -ge 200 ] && [ "$$code" -lt 300 ]; then \
	  jq -er '.choices[0].message.content | strings | select(length>0)' "$$tmp_body" >/dev/null \
	    && echo "✓ LLM OK" || (echo "✗ LLM returned unexpected JSON"; sed -n '1,120p' "$$tmp_body"; exit 1); \
	else \
	  echo "✗ LLM failed (HTTP $$code)"; \
	  echo "--- response headers (first 30 lines) ---"; sed -n '1,30p' "$$tmp_hdr"; \
	  echo "--- response body (first 120 lines) ---"; sed -n '1,120p' "$$tmp_body"; \
	  exit 1; \
	fi; \
	rm -f "$$tmp_body" "$$tmp_hdr"


.PHONY: test-tools-integration
test-tools-integration: install
	@echo "Running tools integration tests LLM + OCR ..."
	## Run LLM + OCR integration checks
	@$(MAKE) test-llm
	@$(MAKE) test-ocr


# ---- Maintenance -----------------------------------------------------------

.PHONY: clean
clean: ## Remove cache, __pycache__, .pytest_cache
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf htmlcov/ .coverage
	@echo "✓ Cache cleaned"

.PHONY: clean-venv
clean-venv: ## Remove virtual environment
	@rm -rf $(VENV)
	@echo "✓ venv removed"

.PHONY: freeze
freeze: venv ## Export installed packages
	@$(PIP) freeze > requirements.lock
	@echo "✓ Requirements exported to requirements.lock"

.PHONY: show-env
show-env: ## Show environment info
	@echo "VENV: $(VENV)"
	@echo "PYTHON: $(PYTHON)"
	@echo "PYTHONPATH: $(PYTHONPATH)"
	@echo "SRC_DIR: $(SRC_DIR)"
	@echo "Python version:"
	@$(PYTHON) --version