FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy orchestrator service
COPY services/orchestrator/src/ ./src/

# Copy shared library
COPY services/common/src/ ./common_src/
ENV PYTHONPATH=/app/common_src:/app/src

EXPOSE 8000

# Run the agent loop
CMD ["python", "-m", "uvicorn", "src.agent_loop:app", "--host", "0.0.0.0", "--port", "8000"]
