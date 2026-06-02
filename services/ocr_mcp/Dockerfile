FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

ARG SERVICE_NAME=ocr_mcp
ARG SERVICES_DIR=services

WORKDIR /workspace

# Install deps first for layer caching
COPY ${SERVICES_DIR}/${SERVICE_NAME}/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code
COPY ${SERVICES_DIR}/${SERVICE_NAME}/src/ /workspace/src/

# Default port for MCP streamable-http
EXPOSE 8003

# Run with streamable-http transport for Docker accessibility
CMD ["python", "-m", "src.server"]
