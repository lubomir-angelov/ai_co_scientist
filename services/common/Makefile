# services/common/Makefile

PYTHON ?= python
# add src/ so "import shared_library" works from this folder
export PYTHONPATH := $(PWD)/src:$(PYTHONPATH)

.PHONY: help
help:
	@echo "make install      - install test/dev deps"
	@echo "make test         - run tests with current venv"
	@echo "make build        - build wheel"

.PHONY: install
install:
	$(PYTHON) -m pip install -r requirements.txt
	[ -f requirements_test.txt ] && $(PYTHON) -m pip install -r requirements_test.txt || true

.PHONY: test
test:
	$(PYTHON) -m pytest -v tests

.PHONY: build
build:
	$(PYTHON) -m build
