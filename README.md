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
git clone https://github.com/lubomir-angelov/ai_co_scientist.git 
cd ai_co_scientist

# fetch submodule contents
git submodule update --init --recursive
```

This is how Git pulls down the exact commit of OctoTools we’re pinned to.

If you skip this step, vendor/octotools exists but is empty-ish. That’s the #1 “why is my import failing?” confusion with submodules.

# Updating OctoTools to a newer upstream commit

Let’s say OctoTools released improvements and we want to pull them in.

```bash
cd vendor/octotools

# pull latest from its default branch (e.g. main)
git fetch origin
git checkout main
git pull origin main
# now vendor/octotools is at a newer commit

cd ../..  # back to repo root
git add vendor/octotools
git commit -m "Bump octotools submodule to latest main"
```
- moved the submodule’s pointer to a newer commit.
- committed that pointer change in your main repo.

Anyone who pulls this repo and runs:

```bash
git pull
git submodule update --init --recursive
```
will now get the new OctoTools commit.

# Making local modifications to OctoTools

Eventually, we’re going to want to hack OctoTools (inject memory calls, add provenance enforcement, etc.).

We will treat vendor/octotools as our fork

We can make changes directly in vendor/octotools and commit them there.

```bash
cd vendor/octotools
git checkout -b my-custom-agent
# edit planner.py, executor.py, etc.
git commit -am "Inject memory pre-query step"
```


Now, vendor/octotools has commits that don’t exist upstream.

From the root:

```bash
cd ../..   # back to repo root
git add vendor/octotools
git commit -m "Use customized octotools with memory injection"
```

This main repo now points at a custom commit hash. 

Anyone who clones and runs git submodule update --init --recursive will get the modified version, not upstream main.

At this point, vendor/octotools is effectively a fork living inside this project.

# Citation

@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
