#####################################################################
# STAGE 1: builder
#####################################################################
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

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

ENV VENV_PATH=/opt/inference-venv
RUN python3.12 -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/python -m pip install --upgrade pip setuptools wheel

WORKDIR /tmp
RUN git clone https://github.com/deepseek-ai/DeepSeek-OCR.git
WORKDIR /tmp/DeepSeek-OCR

# server deps (fastapi, uvicorn, pdf2image, pillow, etc.)
COPY requirements.txt /tmp/requirements_server.txt

RUN ${VENV_PATH}/bin/python -m pip install --pre torch torchvision torchaudio \
      --index-url https://download.pytorch.org/whl/nightly/cu128 && \
    ${VENV_PATH}/bin/python -m pip install -r /tmp/DeepSeek-OCR/requirements.txt && \
    ${VENV_PATH}/bin/python -m pip install -r /tmp/requirements_server.txt && \
    rm -rf /root/.cache/pip

# OPTIONAL: install your shared_library wheel if it's in build context
COPY services/common/dist/shared_library-0.1.0-py3-none-any.whl /tmp/shared_library.whl
RUN ${VENV_PATH}/bin/pip install /tmp/shared_library.whl

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

# copy ALL src (server.py + ocr_runtime.py)
# assuming your Docker build context has: services/ocr/src/...
COPY src/ /tmp/src/
#####################################################################
# STAGE 2: runtime
#####################################################################
ARG BASE_IMAGE
FROM ${BASE_IMAGE//-devel/-runtime} AS runtime

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

# run as non-root
RUN useradd -m -u 1000 -s /bin/bash inferenceuser

WORKDIR /workspace

# copy venv, models, code
COPY --from=builder /opt/inference-venv /opt/inference-venv
COPY --from=builder /opt/models /opt/models
COPY --from=builder /tmp/DeepSeek-OCR /workspace/DeepSeek-OCR
COPY --from=builder /tmp/src/ /workspace/src/

RUN chown -R inferenceuser:inferenceuser /workspace /opt/inference-venv /opt/models

ENV PATH="/opt/inference-venv/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=0
ENV HF_HOME=/workspace/hf-cache

# keep flash-attn disabled at container level too
ENV TRANSFORMERS_ATTENTION_IMPLEMENTATION=eager
ENV TRANSFORMERS_NO_FLASH_ATTENTION=1

USER inferenceuser
WORKDIR /workspace

# expose OCR service port
EXPOSE 8002

# run the FastAPI app
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
