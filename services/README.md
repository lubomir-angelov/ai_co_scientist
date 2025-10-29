# Services

We employ several microservices that constitue the ai_co_scientist.

Those are:

```
ai_co_scientist/
├── docker-compose.yml
├── services/
│   ├── orchestrator/ # This is where we wrap OctoTools itself. This service is the “brain that calls tools.” 
                      # It should not try to be the tools.
│   │   │
│   │   ├── src/
│   │   │   ├── agent_loop.py
│   │   │   ├── tools_registry.py
│   │   │   ├── adapters/        # http wrappers for OCR, memory, etc.
│   │   │   └── runtime_config.py
│   │   ├── Dockerfile
│   │   └── tests/
│   │   │ # The rest are all called by the orchestrator. Each exposes a tiny, well-defined HTTP API.
│   ├── memory/
│   ├── llm/
│   └── ocr/
│   ├── common/ # Is crucial. We don’t duplicate schemas, timestamps, provenance logic or logging config in four places. 
                # We make a light shared lib we can import from each service.
│   │   
└── vendor/
    └── octotools/   <-- git submodule of the original repo
```


