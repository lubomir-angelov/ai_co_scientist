"""Per-paper resumable state — the one source of truth for what stage each paper is in.

``StateStore`` is the only writer of state files and the only deriver of the work-directory
layout (``ocr_cache_path`` / ``state_path``), so nothing else in the batch re-derives these
paths (CLAUDE.md §6). Writes are atomic (tmp file + ``os.replace``), so a crash mid-write
never leaves a half-written state file for the next run to misread.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class OcrDone(BaseModel):
    status: Literal["done"]
    finished_at: datetime
    seconds: float
    page_count: int


class IngestDone(BaseModel):
    status: Literal["done"]
    finished_at: datetime
    seconds: float
    episodes: int
    created: int


class StageFailed(BaseModel):
    status: Literal["failed"]
    finished_at: datetime
    seconds: float
    error: str
    status_code: int | None


class ResolvedMeta(BaseModel):
    title: str
    published_at: datetime | None
    year: int | None
    # None iff published_at is None and year is None (the model found no date at all).
    published_at_source: Literal["arxiv_filename", "page1_llm"] | None


class PaperState(BaseModel):
    paper_id: str
    source_file: str  # absolute path of the PDF at phase-1 time
    ocr: OcrDone | StageFailed | None = None  # None = never attempted
    meta: ResolvedMeta | None = None  # set once, reused on every retry
    ingest: IngestDone | StageFailed | None = None


class StateStore:
    """Reads and writes one ``PaperState`` JSON file per paper under ``<work_dir>/state/``."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.state_dir = work_dir / "state"
        self.ocr_dir = work_dir / "ocr"
        self.logs_dir = work_dir / "logs"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def state_path(self, paper_id: str) -> Path:
        return self.state_dir / f"{paper_id}.json"

    def ocr_cache_path(self, paper_id: str) -> Path:
        return self.ocr_dir / f"{paper_id}.json"

    def load(self, paper_id: str) -> PaperState | None:
        """Return the paper's state, or None when it has never been touched in any run."""
        path = self.state_path(paper_id)
        if not path.is_file():
            return None
        return PaperState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: PaperState) -> None:
        path = self.state_path(state.paper_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp_path, path)

    def known_paper_ids(self) -> list[str]:
        """Every paper_id that has a state file, sorted for a deterministic run order."""
        return sorted(path.stem for path in self.state_dir.glob("*.json"))
