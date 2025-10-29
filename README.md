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


# Citation

@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
