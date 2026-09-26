# services/memory/Dockerfile
# Build from the repo root:  docker build -f services/memory/Dockerfile .

# CPU-only: the memory service calls the LLM / embedding services over HTTP.
# Python 3.13 matches services/common (requires-python >= 3.13).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRAPHITI_TELEMETRY_ENABLED=false

WORKDIR /app

# ---- Dependencies first (cached unless requirements change) ----
COPY services/common/requirements.txt /app/services/common/requirements.txt
COPY services/memory/requirements.txt /app/services/memory/requirements.txt
RUN pip install --no-cache-dir \
      -r services/common/requirements.txt \
      -r services/memory/requirements.txt

# ---- Source trees ----
COPY services/common /app/services/common
COPY services/memory /app/services/memory
RUN pip install --no-cache-dir --no-deps ./services/common ./services/memory

RUN useradd --create-home --uid 1000 memory
USER memory

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/health', timeout=4)"

# App factory: configuration is validated at startup (e.g. MEMORY_LLM_MODEL is required).
CMD ["uvicorn", "memory_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8005"]
