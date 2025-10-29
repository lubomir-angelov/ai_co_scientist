# ai_co_scientist
An agentic framework for an ai co-scientist. 

Based on the Octotols framework: https://github.com/octotools/octotools

The agent focuses on three main capabilities: 
  1. Deep technical reasoning + math skill
  2. Long context window (to ingest papers, specs, layouts)
  3. Ability to generate and critique code / architectures.
  
An additional feature is the ability to run consumer-grade hardware.

# Setup
The reository structure is as follows:

```
octotools-extended/
├── docker-compose.yml
├── services/
│   ├── orchestrator/
│   │   ├── src/
│   │   │   ├── agent_loop.py
│   │   │   ├── tools_registry.py
│   │   │   ├── adapters/        # http wrappers for OCR, memory, etc.
│   │   │   └── runtime_config.py
│   │   ├── Dockerfile
│   │   └── tests/
│   ├── memory/
│   ├── llm/
│   └── ocr/
└── vendor/
    └── octotools/   <-- git submodule of the original repo
```

## init the vendor
```bash
# create vendor/ if it doesn't exist yet
mkdir -p vendor

# add octotools as a submodule inside vendor/
git submodule add https://github.com/octotools/octotools.git vendor/octotools

# add and commit the submodule files
git add .gitmodules vendor/octotools
git commit -m "Add OctoTools as submodule under vendor/octotools"
```

At this point:

The repo tracks which commit of OctoTools it's pinned to.

We are referencing a specific commit from their repo.

## using the submodule in the other code

```python
from vendor.octotools.core.planner import Planner
from vendor.octotools.core.executor import Executor
```

## Notes:

When using from a venv or in Docker:

1. We need vendor on PYTHONPATH in the orchestrator container/runtime.
2. We need vendor/octotools to be copied into the Docker build context.

# Working with this repo with the submodule

```bash
git clone <your-repo-url> octotools-extended
cd octotools-extended

# fetch submodule contents
git submodule update --init --recursive
```

# Citation

@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
