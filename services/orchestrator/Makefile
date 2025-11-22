# Orchestrator service Makefile
# Controls agent loop, tool registry, and orchestration logic

SHELL := /bin/bash
VENV := ~/venvs/ai_cosc_orchestrator
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
SRC_DIR := $(PWD)/src
PYTHONPATH := $(SRC_DIR):$(PYTHONPATH)

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

.PHONY: test-tools-integration
test-tools-integration: install ## Test tools registry with actual services
	@echo "Testing LLM service..."
	@curl -s -H "Authorization: Bearer local-llm" \
	    -H "Content-Type: application/json" \
	    -d '{"model":"deepseek-ai/DeepSeek-R1-Distill-Qwen-14B-AWQ","messages":[{"role":"user","content":"test"}]}' \
	    http://localhost:9000/v1/chat/completions | jq '.choices[0].message.content' && echo "✓ LLM OK" || echo "✗ LLM failed"
	@echo "Testing OCR service..."
	@curl -s http://localhost:8001/health 2>/dev/null && echo "✓ OCR OK" || echo "✗ OCR failed"

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