# memory_service/graphiti_paper_backend.py

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List

from graphiti_core.nodes import EpisodeType
from graphiti_core.edges import EntityEdge

from shared_library.memory_interface import PaperMemoryBackend
from shared_library.data_contracts import (
    PaperSectionEpisodeIn,
    PaperNoteEpisodeIn,
    ConceptQuery,
    MemoryFact,
)
from .graphiti_client import GraphitiClient


class GraphitiPaperMemoryBackend(PaperMemoryBackend):
    """
    Graphiti/FalkorDB-backed implementation of PaperMemoryBackend.
    """

    def __init__(self, client: GraphitiClient) -> None:
        self._client = client

    async def init(self) -> None:
        await self._client.init()

    async def close(self) -> None:
        await self._client.close()

    # ---------------- ingestion ----------------

    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> str:
        g = self._client.client

        body = {
            "type": "paper_section",
            "paper": ep.paper.model_dump(),
            "section_name": ep.section_name,
            "section_index": ep.section_index,
            "chunk_index": ep.chunk_index,
            "text": ep.text,
        }

        created_at = ep.created_at or datetime.now(timezone.utc)
        reference_time = ep.paper.published_at or created_at

        episode = await g.add_episode(
            name=f"paper:{ep.paper.paper_id}:sec:{ep.section_name}:{ep.chunk_index}",
            episode_body=json.dumps(body, default=str),
            source=EpisodeType.json,
            source_description="paper section ingest",
            reference_time=reference_time,
        )

        return str(episode.uuid)

    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> str:
        g = self._client.client

        body = {
            "type": "paper_note",
            "paper": ep.paper.model_dump(),
            "location_hint": ep.location_hint,
            "note_text": ep.note_text,
            "note_type": ep.note_type,
        }

        created_at = ep.created_at or datetime.now(timezone.utc)

        episode = await g.add_episode(
            name=f"note:{ep.paper.paper_id}:{created_at.isoformat()}",
            episode_body=json.dumps(body, default=str),
            source=EpisodeType.json,
            source_description="user note on paper",
            reference_time=created_at,
        )

        return str(episode.uuid)

    # ---------------- retrieval ----------------

    async def search_concepts(self, q: ConceptQuery) -> List[MemoryFact]:
        g = self._client.client

        nl_query = (
            "Retrieve key facts, claims, results, and notes related to the topic: "
            f"'{q.query_text}'. "
            "Include numerical performance metrics (e.g., Q factor, energy/bit, "
            "fidelity, bandwidth) where available. Focus on silicon photonics, "
            "optical processing, and quantum photonics where relevant."
        )

        edges: List[EntityEdge] = await g.search(
            query=nl_query,
            num_results=q.limit,
            reference_time=q.time_filter_as_of,
        )

        facts: List[MemoryFact] = []
        for e in edges:
            facts.append(
                MemoryFact(
                    fact=getattr(e, "fact", ""),
                    created_at=getattr(e, "created_at", None),
                    valid_at=getattr(e, "valid_at", None),
                    invalid_at=getattr(e, "invalid_at", None),
                    expired_at=getattr(e, "expired_at", None),
                    episodes=list(getattr(e, "episodes", []) or []),
                    source_node_uuid=str(
                        getattr(e, "source_node_uuid", "") or ""
                    )
                    or None,
                    target_node_uuid=str(
                        getattr(e, "target_node_uuid", "") or ""
                    )
                    or None,
                )
            )
        return facts
