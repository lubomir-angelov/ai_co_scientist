# Docker Compose Setup

This docker-compose configuration orchestrates all microservices for the AI Co-Scientist platform.

## Services

### 1. **LLM Service** (Port 8000)
- **Image**: `vllm/vllm-openai:latest`
- **Purpose**: Provides OpenAI-compatible LLM inference
- **Environment**: GPU-accelerated (all GPUs)
- **Features**:
  - DeepSeek-R1 or custom model support
  - 32K token context window
  - 90% GPU memory utilization

### 2. **LLM Gateway** (Port 9000)
- **Image**: Built from `services/llm/src/gateway`
- **Purpose**: Authentication proxy for LLM service
- **API Key**: Configured via `LLM_API_KEY` env var (default: `local-llm`)
- **Depends on**: LLM service (healthcheck)

### 3. **OCR Service** (Port 8002)
- **Image**: Built from `services/ocr/Dockerfile`
- **Purpose**: DeepSeek OCR for document/image text extraction
- **GPU**: Uses GPU device 1 (separate from LLM)
- **Features**:
  - PDF and image processing
  - Bfloat16 precision
  - Eager attention (no flash attention)
  - Model cached at `/opt/models/deepseek-ocr`
- **Dependencies**: LLM Gateway (for coordination)

### 4. **Orchestrator** (Port 8001)
- **Image**: Built from `services/orchestrator/Dockerfile`
- **Purpose**: Agent loop coordinating between services
- **Endpoints**:
  - `GET /health` - Health check
  - `GET /tools` - List available tools
  - `POST /run` - Execute agent task
- **Dependencies**: LLM Gateway and OCR service

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- NVIDIA Docker Runtime
- 2x GPU (or adjust `CUDA_VISIBLE_DEVICES`)
- ~60GB free disk space (for model downloads)

## Configuration

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` if needed**:
   - `LLM_MODEL`: Change LLM model (default: DeepSeek-R1-Distill-Qwen-14B)
   - `LLM_API_KEY`: Set authentication key
   - `CUDA_VISIBLE_DEVICES`: Assign GPUs

## Quick Start

### Build Services
```bash
docker-compose build
```

### Start All Services
```bash
docker-compose up -d
```

### View Logs
```bash
docker-compose logs -f
```

### Check Service Health
```bash
# LLM Gateway
curl -H "x-api-key: local-llm" http://localhost:9000/v1/models

# OCR Service
curl http://localhost:8002/healthz

# Orchestrator
curl http://localhost:8001/health
```

### Stop Services
```bash
docker-compose down
```

## Service Communication

Internal network: `ai-co-scientist-network`

Service URLs (from within Docker):
- LLM: `http://llm:8000/v1`
- LLM Gateway: `http://llm-gateway:9000/v1` (requires API key)
- OCR: `http://ocr:8002`
- Orchestrator: `http://orchestrator:8001`

## GPU Assignment

- **LLM Service**: All GPUs (via `gpus: all`)
- **OCR Service**: GPU device 1 (via `gpus: [1]`)

To use different GPUs, modify `CUDA_VISIBLE_DEVICES` env var or adjust service GPU assignments.

## Volume & Caching

- **HuggingFace Cache**: `/workspace/hf-cache` (OCR service)
- **Model Cache**: `/opt/models/deepseek-ocr` (OCR service)

These are persistent across restarts but stored in container layers. To clean:
```bash
docker-compose down -v  # Remove volumes
docker system prune -a   # Remove unused images
```

## Troubleshooting

### LLM Service Won't Start
- Check available GPU memory: `nvidia-smi`
- Reduce batch size or increase `--max-model-len`
- Verify NVIDIA runtime: `docker run --rm --gpus all nvidia/cuda:12.8.1-base nvidia-smi`

### OCR Service Timeout
- First model download takes ~30 mins
- Check logs: `docker-compose logs ocr`
- Verify model file: `/opt/models/deepseek-ocr/`

### Memory Service Not Ready
- Implementation in progress
- Placeholder only; will be added when graph_store.py implementation is complete

## Development

### Local Development (non-Docker)

For OCR service:
```bash
cd services/ocr
make install
make run  # Runs on localhost:8002
```

For Orchestrator:
```bash
cd services/orchestrator
pip install -r requirements.txt
uvicorn src.agent_loop:app --host 0.0.0.0 --port 8001 --reload
```

### Rebuilding After Code Changes
```bash
docker-compose build --no-cache
docker-compose up -d
```

## API Examples

### Call LLM via Gateway
```bash
curl -X POST http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: local-llm" \
  -d '{
    "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Extract Text from Image via OCR
```bash
curl -X POST http://localhost:8002/ocr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "<base64-encoded-image>",
    "format": "base64"
  }'
```

### List Agent Tools
```bash
curl http://localhost:8001/tools
```
