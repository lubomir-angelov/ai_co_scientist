# shared_library/memory_interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .data_contracts import (
    AgentStepEpisodeIn,
    ConceptQuery,
    EpisodeAck,
    FactChanges,
    FactChangesQuery,
    HypothesisEpisodeIn,
    MemoryFact,
    PaperNoteEpisodeIn,
    PaperSectionEpisodeIn,
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
    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> EpisodeAck:
        """
        Ingest a chunk of a paper section into memory.

        Implementations must be idempotent: re-sending an identical chunk
        returns the existing episode with ``created=False``.
        """
        raise NotImplementedError

    @abstractmethod
    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> EpisodeAck:
        """
        Ingest a user-authored note/comment on a paper.
        """
        raise NotImplementedError

    @abstractmethod
    async def add_agent_step(self, ep: AgentStepEpisodeIn) -> EpisodeAck:
        """
        Record one executed agent step (sub-goal, tool, result summary).
        """
        raise NotImplementedError

    @abstractmethod
    async def add_hypothesis(self, ep: HypothesisEpisodeIn) -> EpisodeAck:
        """
        Record a new version of a research hypothesis.
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

    @abstractmethod
    async def fact_changes(self, q: FactChangesQuery) -> FactChanges:
        """
        Return facts about a topic that became valid, or were invalidated,
        within the [q.since, q.until] window.
        """
        raise NotImplementedError
