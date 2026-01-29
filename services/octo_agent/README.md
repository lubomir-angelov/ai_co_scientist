# Usage
cd services/orchestrator

# Setup venv and install dependencies
make venv
make install
make install-test

# Show PYTHONPATH
make pythonpath

# Run tests with PYTHONPATH set
make test
make test-registry

# Run Python with PYTHONPATH
make python SCRIPT=scripts/test_tools.py

# Activate venv
source ~/venvs/ai_cosc_orchestrator/bin/activate

# Run solver locally
```bash
export LLM_MODEL_ID="Corianas/DeepSeek-R1-Distill-Qwen-14B-AWQ"

python solver.py \
  --llm_engine_name local-llm \
  --enabled_tools all \
  --output_types final,direct \
  --question "Given a FastAPI service and an OCR microservice, propose an integration test strategy and list 8 concrete tests."
```

# Debug
```bash
curl -sS http://localhost:8000/openapi.json | jq -r '.paths | keys[]' | sort | head -n 50

curl -sS http://localhost:8000/v1/models | jq -r '.data[].id' | head -n 20

MODEL="Corianas/DeepSeek-R1-Distill-Qwen-14B-AWQ"
MODEL="$(curl -sS http://localhost:8000/v1/models | jq -r '.data[0].id')"
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer local-llm" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":8}"

```