# LLM service

A local LLM served by [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llm`, CUDA), with a
small FastAPI proxy that enforces an API key (`llm-gateway`). Both expose an
OpenAI-compatible API.

| Service | Host port | Notes |
|---|---|---|
| `llm` | 8000 | llama.cpp server; model id `Qwen3.8-27B-UD-Q4_K_XL` (`--alias`) |
| `llm-gateway` | 9000 | Proxies `/v1/models`, `/v1/chat/completions`, `/v1/completions`; requires `Authorization: Bearer $LLM_API_KEY` |

The model file is expected at
`models/hotswap/Qwen3.8-27B-UD-Q4_K_XL/Qwen3.8-27B-UD-Q4_K_XL.gguf` (repo root, git-ignored).
The MTP draft model and the vision projector in the same folder are wired up but commented
out in `compose.yaml`.

## Running

```bash
cd services/llm
make up            # standalone: build + start llm and gateway (thinking ON)
make wait          # wait until the gateway answers
make curl-models   # list served models
make curl-chat     # sample chat completion
make install       # .venv with the openai client, needed for `make smoke`
make smoke
make logs / make down
```

In the full stack (`make up` from the repo root), the same `compose.yaml` is used together
with `compose.stack.yaml`.

## Qwen thinking

Thinking is controlled by `LLAMA_ARG_REASONING`, which is set from `LLM_REASONING`:

| Where | Default | Override |
|---|---|---|
| Standalone (`make -C services/llm up`) | `on` | `LLM_REASONING=off make up` |
| Full stack (`make up` at the root) | `off` | `LLM_REASONING=on make up` |

`auto`, llama.cpp's default, follows the chat template, and for Qwen that means thinking is
on. The old `--reasoning` CLI flag is left in `compose.yaml` commented out, because a CLI
flag would override the env var. A single request can still turn thinking on with
`"chat_template_kwargs": {"enable_thinking": true}`.

## Tuning

`compose.yaml` holds the runtime flags: 256k context, q8_0 KV cache, flash attention,
`--cache-ram`, and sampling defaults (temp 1.0, top-p 0.95, top-k 20). If the model doesn't
fit alongside other GPU workloads, lower `--ctx-size` first.
