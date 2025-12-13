# shared_library/memory_interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .data_contracts import (
    PaperSectionEpisodeIn,
    PaperNoteEpisodeIn,
    ConceptQuery,
    MemoryFact,
)


class PaperMemoryBackend(ABC):
    """
    Abstract interface for the co-scientist's long-term paper memory.

    - Lives in shared_library so that *all* microservices can depend on it
      without knowing about the underlying backend (Graphiti, Zep, etc.).
    - The memory microservice provides a concrete implementation.
    """

    async def init(self) -> None:
        """
        Optional initialization hook.
        Concrete backends may override this (e.g. to build indices).
        Default is a no-op.
        """
        return None

    async def close(self) -> None:
        """
        Optional shutdown hook.
        Concrete backends may override this to close connections, etc.
        Default is a no-op.
        """
        return None

    # ----------------- ingestion -----------------

    @abstractmethod
    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> str:
        """
        Ingest a chunk of a paper section into memory.

        Returns:
            Backend-specific episode identifier.
        """
        raise NotImplementedError

    @abstractmethod
    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> str:
        """
        Ingest a user-authored note/comment on a paper.

        Returns:
            Backend-specific episode identifier.
        """
        raise NotImplementedError

    # ----------------- retrieval -----------------

    @abstractmethod
    async def search_concepts(self, q: ConceptQuery) -> List[MemoryFact]:
        """
        Retrieve facts related to a concept / topic across all ingested papers.

        Implementations should:
          - Use both semantic and graph-based signals where possible.
          - Respect q.time_filter_as_of if provided (temporal 'as-of' queries).
          - Return up to q.limit results, sorted by recency/relevance.
        """
        raise NotImplementedError
