# ai_co_scientist
An agentic framework for an ai co-scientist. 

Based on the Octotols framework: https://github.com/octotools/octotools

The agent focuses on three main capabilities: 
  1. Deep technical reasoning + math skill
  2. Long context window (to ingest papers, specs, layouts)
  3. Ability to generate and critique code / architectures.
  
An additional feature is the ability to run consumer-grade hardware.

# Structure
The reository structure is as follows:

```
ai_co_scientist/
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

## Add an external vendor
We are adding octools as an external submodule to use in this repo. 

Currently we are using it "as is" but we are planning to add changes in the near future, at that point see [here](#working-with-this-repo-with-the-submoduleWorking with this repo with the submodule)

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


### Using the submodule other parts of the repo:

```python
from vendor.octotools.core.planner import Planner
from vendor.octotools.core.executor import Executor
```


### When using from a venv or within a container:

- We need vendor/octotools/octotools on PYTHONPATH in the orchestrator container/runtime.
- We need vendor/octotools/octotools to be copied into the Docker build context.


# Working with this repo and the submodule

To work with the repo you need to pull and initialize the external submodule:

```bash
git clone https://github.com/lubomir-angelov/ai_co_scientist.git 
cd ai_co_scientist

# fetch submodule contents
git submodule update --init --recursive
```

This is how Git pulls down the exact commit of OctoTools we’re pinned to.

If you skip this step, vendor/octotools exists but is empty-ish. 

In that case the imports will start failing.

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

At this point we have: 

- moved the submodule’s pointer to a newer commit.
- committed that pointer change in your main repo.

Anyone who pulls after this point this repo and runs:

```bash
git pull
git submodule update --init --recursive
```

Will now get the new OctoTools commit.


# Making local modifications to OctoTools

Eventually, we’re going to hack OctoTools (inject memory calls, add provenance enforcement, etc.).

At that point of time, we will treat vendor/octotools as a fork.

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

This main repo will then point at a custom commit hash. 

Anyone who clones and runs 
```git submodule update --init --recursive``` will get the modified version, not upstream main.

At that point, vendor/octotools is effectively a fork living inside this project.

# Citation

```
@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
```
