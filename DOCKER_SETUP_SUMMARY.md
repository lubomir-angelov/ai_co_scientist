# Docker Compose Quick Reference

## Summary

A complete docker-compose setup is now configured that runs all ready services:

### Services Running:
- ✅ **LLM** (vLLM OpenAI-compatible) - Port 8000
- ✅ **LLM Gateway** (Auth proxy) - Port 9000  
- ✅ **OCR** (DeepSeek document/image understanding) - Port 8002
- ✅ **Orchestrator** (Agent coordination) - Port 8001
- ⏳ **Memory** (Graph store - not ready yet)

## Files Created/Modified

### docker-compose.yml
- Root-level orchestration of all 4 services
- GPU assignment (LLM on all, OCR on device 1)
- Service dependencies and health checks
- Internal network: `ai-co-scientist-network`

### services/orchestrator/Dockerfile
- Python 3.11-slim base
- Copies orchestrator code + shared library
- Runs FastAPI uvicorn server

### services/orchestrator/src/agent_loop.py
- Updated with FastAPI app
- Endpoints: `/health`, `/tools`, `/run`
- Integrates with ToolsRegistry

### services/orchestrator/requirements.txt
- Added fastapi, uvicorn, python-multipart

### .env.example
- Template for configuration variables
- LLM model, API keys, service URLs

### DOCKER_COMPOSE.md
- Comprehensive documentation
- Setup instructions, API examples, troubleshooting

## Quick Commands

```bash
# Build all services
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service health
curl http://localhost:9000/v1/models -H "x-api-key: local-llm"
curl http://localhost:8002/healthz
curl http://localhost:8001/health

# Stop services
docker-compose down
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│     ai-co-scientist Docker Network              │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────┐      ┌──────────────┐            │
│  │   LLM    │─────▶│ LLM Gateway  │            │
│  │(vLLM)    │      │(Auth Proxy)  │            │
│  │:8000     │      │:9000         │            │
│  └──────────┘      └──────────────┘            │
│       GPU:0             │                       │
│                         │                       │
│                    ┌────▼──────┐               │
│                    │Orchestrator│               │
│                    │Agent Loop  │               │
│                    │:8001       │               │
│                    └────┬───────┘               │
│                         │                       │
│                    ┌────▼──────┐               │
│                    │    OCR     │               │
│                    │  DeepSeek  │               │
│                    │   :8002    │               │
│                    └────────────┘               │
│                        GPU:1                    │
│                                                 │
│  [Memory Service - placeholder, not ready]    │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Important Notes

1. **Memory Service**: Not included - `graph_store.py` implementation pending
2. **GPU Requirements**: Needs 2 GPUs or adjust `CUDA_VISIBLE_DEVICES`
3. **First Run**: Model downloads (~30GB) will take 30+ minutes
4. **API Key**: Default `local-llm` for LLM Gateway authentication

## Next Steps

1. Update `services/memory/src/graph_store.py` with implementation
2. Create `services/memory/Dockerfile`
3. Add memory service to docker-compose.yml
4. Update orchestrator tools registry with memory endpoints
