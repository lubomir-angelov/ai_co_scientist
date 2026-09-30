# services/common/Makefile - shared_library (contracts, interfaces)

PYTHON ?= python3
VENV   ?= .venv
PY     := $(VENV)/bin/python
RUFF   := $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)

export PYTHONPATH := $(CURDIR)/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install  - create $(VENV) and install deps + test deps"
	@echo "make test     - run unit tests"
	@echo "make lint     - ruff check"
	@echo "make fmt      - ruff format + ruff check --fix"
	@echo "make build    - build a wheel into dist/"

.PHONY: install
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt -r requirements_test.txt ruff==0.15.12

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

.PHONY: build
build: check-venv
	$(PY) -m pip wheel --no-deps -w dist .
