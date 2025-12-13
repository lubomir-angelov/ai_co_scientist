# services/memory/Dockerfile

# CPU-only base is fine for the memory + Graphiti client
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---- System deps (for building wheels etc.) ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# ---- Pre-copy only metadata to leverage Docker cache for deps ----
# repo structure:
#   /services/common/...
#   /services/memory/...

COPY services/common/pyproject.toml services/common/requirements.txt /app/services/common/
COPY services/memory/pyproject.toml services/memory/requirements.txt /app/services/memory/

# ---- Install Python dependencies (no editable installs yet) ----
RUN pip install --no-cache-dir -r services/common/requirements.txt && \
    pip install --no-cache-dir -r services/memory/requirements.txt

# ---- Copy full source trees ----
COPY services/common /app/services/common
COPY services/memory /app/services/memory

# ---- Install shared_library + memory service in editable mode ----
# common contains src/shared_library, managed via its own pyproject
RUN pip install --no-cache-dir -e services/common --no-deps && \
    pip install --no-cache-dir -e services/memory --no-deps

# Make sure src dirs are on PYTHONPATH (defensive; editable installs should already handle it)
ENV PYTHONPATH=/app/services/common/src:/app/services/memory/src:$PYTHONPATH

# Memory service listens on 8005 (match your Makefile / compose)
EXPOSE 8005

# Graphiti talks to FalkorDB; configure URI via env at runtime (docker-compose)
# Default app module is memory_service.app:app under services/memory/src
CMD ["uvicorn", "memory_service.app:app", "--host", "0.0.0.0", "--port", "8005"]
