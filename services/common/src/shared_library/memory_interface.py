# shared_library/memory/interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .papers import (
    PaperSectionEpisodeIn,
    PaperNoteEpisodeIn,
    ConceptQuery,
    MemoryFact,
)


class PaperMemoryBackend(ABC):
    """
    Abstract interface for the co-scientist's long-term paper memory.

    - Lives in shared_library so that *all* microservices can depend on it
      without knowing about the underlying backend (Graphiti, Zep, pgvector, etc.).
    - The memory microservice provides a concrete implementation of this interface.
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

    # --- Episode ingestion methods ---

    @abstractmethod
    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> str:
        """
        Ingest a chunk of a paper section into memory.

        Returns:
            A backend-specific episode identifier (string).
        """
        raise NotImplementedError

    @abstractmethod
    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> str:
        """
        Ingest a user-authored note/comment on a paper.

        Returns:
            A backend-specific episode identifier (string).
        """
        raise NotImplementedError

    # --- Retrieval methods ---

    @abstractmethod
    async def search_concepts(self, q: ConceptQuery) -> List[MemoryFact]:
        """
        Retrieve facts related to a concept / topic across all ingested papers.

        Implementations should:
          - Use both semantic and graph-based signals where possible.
          - Respect q.time_filter_as_of if provided (temporal 'as-of' queries).
          - Return up to q.limit results, sorted by recency/relevance.

        Args:
            q: ConceptQuery describing the topic and temporal constraints.

        Returns:
            A list of MemoryFact objects.
        """
        raise NotImplementedError
