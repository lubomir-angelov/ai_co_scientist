#####################################################################
# STAGE 1: builder - venv, torch, deps, pinned models baked into /opt/models
#####################################################################
ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04
ARG RUNTIME_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${BASE_IMAGE} AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV VENV_PATH=/opt/inference-venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common build-essential curl ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/python -m pip install --upgrade pip setuptools wheel

WORKDIR /tmp

# Pinned stable cu128 torch (RTX 50xx needs CUDA 12.8), same pin as the OCR image.
RUN ${VENV_PATH}/bin/python -m pip install torch==2.10.0 \
      --index-url https://download.pytorch.org/whl/cu128

COPY services/voice/requirements.txt /tmp/requirements.txt
RUN ${VENV_PATH}/bin/python -m pip install -r /tmp/requirements.txt && rm -rf /root/.cache/pip

# Model identity SSOT: model_pins.json. The spaCy wheel is installed with its pinned sha256 (pip
# verifies the #sha256 fragment) so misaki never downloads spaCy data at runtime.
COPY services/voice/model_pins.json /tmp/model_pins.json
COPY services/voice/scripts/fetch_models.py /tmp/scripts/fetch_models.py
RUN ${VENV_PATH}/bin/python -m pip install "$(${VENV_PATH}/bin/python /tmp/scripts/fetch_models.py g2p)"
RUN mkdir -p /opt/models && ${VENV_PATH}/bin/python /tmp/scripts/fetch_models.py models

COPY services/voice/src/ /tmp/src/

#####################################################################
# STAGE 2: runtime - offline
#####################################################################
FROM ${RUNTIME_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common curl ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 espeak-ng \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash voiceuser

WORKDIR /workspace

COPY --from=builder /opt/inference-venv /opt/inference-venv
COPY --from=builder /opt/models /opt/models
COPY --from=builder /tmp/src/ /workspace/src/
COPY services/common/src/ /workspace/common_src/
COPY services/voice/tests/gpu/ /workspace/tests/gpu/

# Created here so the bind-mounted/volume data dir inherits voiceuser ownership.
RUN mkdir -p /data && chown -R voiceuser:voiceuser /workspace /data /opt/models

ENV PYTHONPATH=/workspace/common_src:/workspace/src
ENV PATH="/opt/inference-venv/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=0
# Any hidden hub download raises instead of silently reaching the network.
ENV HF_HUB_OFFLINE=1
ENV VOICE_MODELS_MANIFEST=/opt/models/voice-models.json

USER voiceuser
EXPOSE 8007
CMD ["uvicorn", "voice_service.main:app", "--host", "0.0.0.0", "--port", "8007", "--no-access-log"]
