# Bare metal setup
## Fresh env
```bash
python -m venv .venv && source .venv/bin/activate
```

## Install PyTorch for your CUDA (see PyTorch Get Started for the exact command)
## Example (CUDA 12.1 wheels):
```bash
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## Install vLLM
```bash
pip install "vllm>=0.11"
```

## (Optional) FlashAttention can help on some GPUs, but vLLM already ships fast kernels.
## You can skip unless you specifically need it.
## pip install flash-attn --no-build-isolation

## Serve DeepSeek R1 Distill Qwen 14B
```bash
vllm serve deepseek-ai/DeepSeek-R1-Distill-Qwen-14B \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90
```
