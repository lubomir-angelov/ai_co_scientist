#####################################################################
# STAGE 1: builder
# - CUDA 12.8.1 devel (compiler, headers, cuDNN)
# - Python 3.12 via deadsnakes
# - torch nightly cu128 (Blackwell / sm_120 capable)
# - DeepSeek-OCR deps (minus vLLM / flash-attn)
# - prefetch model weights
#####################################################################
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# 1. Base system deps + Python 3.12 from deadsnakes
# We install compiler toolchain here because we may need to build some wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    git \
    git-lfs \
    curl \
    ca-certificates \
    pkg-config \
    wget \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# 2. Create our app venv
ENV VENV_PATH=/opt/inference-venv
RUN python3.12 -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/python -m pip install --upgrade pip setuptools wheel

# 3. Clone DeepSeek-OCR source (will also give us requirements.txt)
WORKDIR /tmp
RUN git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
WORKDIR /tmp/DeepSeek-OCR


# 4. Add server requirements (FastAPI + uvicorn).
#    You should have this file next to the Dockerfile in your build context.
#    Example contents:
#       fastapi==0.115.4
#       uvicorn[standard]==0.32.0
COPY requirements_server.txt /tmp/requirements_server.txt

# 5. Install PyTorch nightlies with CUDA 12.8 (cu128),
#    which include support for RTX 5090's sm_120 architecture.
#    Then install DeepSeek-OCR deps (minus vLLM/flash-attn),
#    then server deps.
RUN ${VENV_PATH}/bin/python -m pip install --pre torch torchvision torchaudio \
      --index-url https://download.pytorch.org/whl/nightly/cu128 && \
    ${VENV_PATH}/bin/python -m pip install -r /tmp/DeepSeek-OCR/requirements.txt && \
    ${VENV_PATH}/bin/python -m pip install -r /tmp/requirements_server.txt && \
    rm -rf /root/.cache/pip
 
# 6. Pre-download the DeepSeek-OCR model weights into /opt/models
#    so runtime doesn't have to hit Hugging Face.
#    We'll load from this local path in server.py.
RUN mkdir -p /opt/models/deepseek-ocr && \
    ${VENV_PATH}/bin/python - << 'PY'
import torch
from transformers import AutoModel, AutoTokenizer

MODEL_NAME = "deepseek-ai/DeepSeek-OCR"

print("Fetching tokenizer/model for warm cache...")
tok = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
)

model = AutoModel.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
    use_safetensors=True,
    # do NOT move to CUDA here; builder might not have GPU access
    _attn_implementation="eager",  # keep generic kernels, avoid flash-attn
)

tok.save_pretrained("/opt/models/deepseek-ocr")
model.save_pretrained("/opt/models/deepseek-ocr")
print("Saved model + tokenizer to /opt/models/deepseek-ocr")
PY

# 8. Copy our FastAPI server source into builder (we'll re-copy in runtime)
#    Make sure server.py sits next to Dockerfile in your build context.
COPY src/server.py /tmp/server.py


#####################################################################
# STAGE 2: runtime
# - CUDA 12.8.1 runtime (cuDNN, but no compiler)
# - install Python 3.12 again (matches builder's interpreter ABI)
# - create non-root user
# - copy venv, model, code
# - run uvicorn
#####################################################################
ARG BASE_IMAGE
FROM ${BASE_IMAGE//-devel/-runtime} AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# 1. Minimal runtime deps (Python 3.12, git for HF auth/LFS, curl/ca-certs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    git \
    git-lfs \
    curl \
    ca-certificates \
    poppler-utils \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# 2. Create a non-root user to run inference
RUN useradd -m -u 1000 -s /bin/bash inferenceuser

# 3. Workspace
WORKDIR /workspace

# 4. Copy virtualenv, source code, and pre-fetched model
COPY --from=builder /opt/inference-venv /opt/inference-venv
COPY --from=builder /opt/models /opt/models
COPY --from=builder /tmp/DeepSeek-OCR /workspace/DeepSeek-OCR
COPY --from=builder /tmp/server.py /workspace/server.py

# 5. Fix permissions so non-root can read/write/cache
RUN chown -R inferenceuser:inferenceuser /workspace /opt/inference-venv /opt/models

# 6. Runtime env
#    - use the venv's python/pip/uvicorn
#    - make a writable HF cache
ENV PATH="/opt/inference-venv/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=0
ENV HF_HOME=/workspace/hf-cache

USER inferenceuser
WORKDIR /workspace

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
