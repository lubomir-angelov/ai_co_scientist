# shared_library

Stable cross-service contracts, imported by every service as `shared_library`.

- `data_contracts.py`: Pydantic request/response models. It covers OCR (`OCRRequest`,
  `OCRResponse`) and memory (`PaperMeta`, the episode inputs, `ConceptQuery`,
  `FactChangesQuery`, `MemoryFact`, `EpisodeAck`, ...).
- `memory_interface.py`: the `PaperMemoryBackend` abstract interface that the memory
  service implements.
- `provenance.py`, `timeutils.py`: small helpers.

Only stable contracts and utilities belong here; service logic stays in the service (see
`AGENTS.md`).

```bash
cd services/common
make install   # .venv with deps + pytest + ruff
make test
make lint
make build     # wheel into dist/
```
