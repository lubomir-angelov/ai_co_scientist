#####################################################################
# STAGE 1: builder
#####################################################################
ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04
ARG SERVICES_DIR=services
ARG SERVICE_NAME=ocr
FROM ${BASE_IMAGE} AS builder

# re-declare
ARG SERVICES_DIR
ARG SERVICE_NAME
ENV SERVICE_PATH=${SERVICES_DIR}/${SERVICE_NAME}
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV VENV_PATH=/opt/inference-venv

# 1) OS deps (rarely change)  --------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    git git-lfs \
    curl ca-certificates \
    pkg-config \
    wget \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev python3.12-venv python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# 2) create venv (rarely changes) ----------------------------------
RUN python3.12 -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/python -m pip install --upgrade pip setuptools wheel

WORKDIR /tmp

# 3) copy ONLY requirements first so pip layer can be cached --------
#    (this is your service requirements, small file, changes rarely)
COPY ${SERVICE_PATH}/requirements.txt /tmp/requirements_server.txt

# 4) install torch + service deps (slow, but cachable) --------------
RUN ${VENV_PATH}/bin/python -m pip install --pre torch torchvision torchaudio \
      --index-url https://download.pytorch.org/whl/nightly/cu128 && \
    ${VENV_PATH}/bin/python -m pip install -r /tmp/requirements_server.txt && \
    rm -rf /root/.cache/pip

# 5) clone DeepSeek-OCR (bigger, but still before your own code) ----
#    if you want it even more cacheable, fork & pin a commit
RUN git clone https://github.com/deepseek-ai/DeepSeek-OCR.git /tmp/DeepSeek-OCR
WORKDIR /tmp/DeepSeek-OCR
RUN ${VENV_PATH}/bin/python -m pip install -r requirements.txt

# 6) download / materialize model (separate layer) ------------------
RUN mkdir -p /opt/models/deepseek-ocr && \
    ${VENV_PATH}/bin/python - << 'PY'
from transformers import AutoModel, AutoTokenizer
MODEL_NAME = "deepseek-ai/DeepSeek-OCR"
tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    use_safetensors=True,
    _attn_implementation="eager",
)
tok.save_pretrained("/opt/models/deepseek-ocr")
model.save_pretrained("/opt/models/deepseek-ocr")
PY

# 7) NOW copy your changing code (last → rebuilds are fast) ---------
#    only this part invalidates the below layers when you edit src
COPY ${SERVICE_PATH}/src/ /tmp/src/

#####################################################################
# STAGE 2: runtime
#####################################################################
ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04
ARG SERVICES_DIR=services
ARG SERVICE_NAME=ocr
FROM ${BASE_IMAGE//-devel/-runtime} AS runtime

ARG SERVICES_DIR
ARG SERVICE_NAME
ENV SERVICE_PATH=${SERVICES_DIR}/${SERVICE_NAME}
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    git git-lfs \
    curl ca-certificates \
    poppler-utils \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash inferenceuser

WORKDIR /workspace

# copy from builder (these layers are cached!)
COPY --from=builder /opt/inference-venv /opt/inference-venv
COPY --from=builder /opt/models /opt/models
COPY --from=builder /tmp/DeepSeek-OCR /workspace/DeepSeek-OCR
COPY --from=builder /tmp/src/ /workspace/src/

# bring in shared_library source (from root context)
COPY ${SERVICES_DIR}/common/src/ /workspace/common_src/
ENV PYTHONPATH=/workspace/common_src:/workspace/src

RUN chown -R inferenceuser:inferenceuser /workspace /opt/inference-venv /opt/models

ENV PATH="/opt/inference-venv/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=0
ENV HF_HOME=/workspace/hf-cache
ENV TRANSFORMERS_ATTENTION_IMPLEMENTATION=eager
ENV TRANSFORMERS_NO_FLASH_ATTENTION=1

USER inferenceuser
WORKDIR /workspace

EXPOSE 8002
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
