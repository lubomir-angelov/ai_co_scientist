# services/ocr/Makefile

BASE_IMAGE ?= nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04
IMAGE_TAG  ?= deepseek-ocr-service

CONTAINER_PORT ?= 8002
HOST_PORT      ?= 8002

PYTHON ?= python
APP_MODULE := src.server:app
HOST := 0.0.0.0

# repo root (two levels up from services/ocr)
REPO_ROOT := $(abspath $(PWD)/../..)
SERVICE_DIR := services/ocr


.PHONY: help
help:
	@echo "make install        - install server + dev deps"
	@echo "make run            - run uvicorn locally on $(HOST):$(HOST_PORT)"
	@echo "make docker-build   - build docker image"
	@echo "make docker-run     - run docker container with GPU"
	@echo "make test           - run pytest"
	@echo "make fmt            - run ruff format + ruff check"

# add these at the top of the Makefile
PWD := $(shell pwd)
export PYTHONPATH := $(PWD)/src:$(PWD)/../common/src:$(PYTHONPATH)

.PHONY: install
install:
	$(PYTHON) -m pip install -r requirements.txt
	[ -f requirements_test.txt ] && $(PYTHON) -m pip install -r requirements_test.txt || true
	@if [ -d "../common" ]; then \
	  cd ../common && $(PYTHON) -m pip install -e . ; \
	fi
	# optional: install ruff for local formatting
	$(PYTHON) -m pip install ruff

.PHONY: run
run:
	TRANSFORMERS_ATTENTION_IMPLEMENTATION=eager \
	TRANSFORMERS_NO_FLASH_ATTENTION=1 \
	$(PYTHON) -m uvicorn $(APP_MODULE) --host $(HOST) --port $(HOST_PORT) --reload

.PHONY: docker-build
docker-build:
	cd $(REPO_ROOT) && \
	docker build \
	  --build-arg BASE_IMAGE="$(BASE_IMAGE)" \
	  -t "$(IMAGE_TAG)" \
	  -f $(SERVICE_DIR)/Dockerfile .

.PHONY: docker-run
docker-run:
	docker run -it --rm --gpus all \
	  -p $(HOST_PORT):$(CONTAINER_PORT) \
	  -v $(PWD)/shared:/workspace/shared \
	  "$(IMAGE_TAG)"

.PHONY: test
test:
	$(PYTHON) -m pytest -v tests

.PHONY: fmt
fmt:
	ruff format src
	ruff check src
