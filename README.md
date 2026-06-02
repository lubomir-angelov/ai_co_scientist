# ai_co_scientist
An agentic framework for an ai co-scientist. 

Based on the Octotols framework: https://github.com/octotools/octotools

The agent focuses on three main capabilities: 
  1. Deep technical reasoning + math skill
  2. Long context window (to ingest papers, specs, layouts)
  3. Ability to generate and critique code / architectures.
  4. Ability to run consumer-grade hardware.

# Structure
The repository structure is as follows:

```
ai_co_scientist/
├── docker-compose.yml
├── Makefile
├── opencode.json
├── services/
│   ├── llm/
│   ├── ocr/
│   ├── ocr_mcp/          # MCP server wrapping the OCR service
│   ├── octo_agent/
│   └── memory/
```


## Quick Start

```bash
# Build and start all services
make build
make up
make health

# Or just the OCR + MCP stack
make ocr-mcp-build
make ocr-mcp-up
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `llm` | 8000 | llama.cpp local LLM (OpenAI-compatible) |
| `ocr` | 8002 | DeepSeek-OCR document extraction |
| `ocr-mcp` | 8003 | MCP server exposing OCR tools to agents |
| `octo_agent` | 8001 | Orchestrator agent loop |

## MCP Servers

The `ocr-mcp` service exposes the following tools via the MCP protocol on `http://localhost:8003/mcp`:

- **`ocr_extract_pdf`** — Extract text from a base64-encoded PDF
- **`ocr_extract_image`** — Extract text from a base64-encoded image
- **`ocr_extract_file`** — Extract text from a PDF or image file on disk
- **`ocr_health`** — Check the health of the underlying OCR service

## Adding to Another Agent (opencode.json)

To connect this MCP server from another opencode project, add this entry to that project's `opencode.json` under the `"mcp"` key:

```json
{
  "mcp": {
    "ocr": {
      "type": "remote",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

If the project already has other MCP servers, merge the `"ocr"` entry into the existing `"mcp"` object:

```json
{
  "mcp": {
    "context-engine": { ... },
    "cvat-sam2": { ... },
    "ocr": {
      "type": "remote",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

Then restart opencode for the changes to take effect.

# Citation

```
@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
```
