"""Graphiti/FalkorDB implementation of the shared PaperMemoryBackend interface."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_filters import ComparisonOperator, DateFilter, SearchFilters

from shared_library.data_contracts import (
    AgentStepEpisodeIn,
    ConceptQuery,
    EpisodeAck,
    EpisodeKind,
    FactChanges,
    FactChangesQuery,
    HypothesisEpisodeIn,
    MemoryFact,
    PaperMeta,
    PaperNoteEpisodeIn,
    PaperSectionEpisodeIn,
)
from shared_library.memory_interface import PaperMemoryBackend

from .ontology import ENTITY_TYPES, EXTRACTION_INSTRUCTIONS

logger = logging.getLogger(__name__)

_FIND_EPISODE_BY_NAME = "MATCH (e:Episodic {name: $name}) RETURN e.uuid AS uuid LIMIT 1"
_EPISODE_KINDS = (
    "MATCH (e:Episodic) WHERE e.uuid IN $uuids RETURN e.uuid AS uuid, "
    "e.source_description AS source_description"
)


def _utc(dt: datetime | None) -> datetime:
    """Return an aware UTC datetime; naive inputs are interpreted as UTC, None as now."""
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def as_of_filters(as_of: datetime, include_invalidated: bool) -> SearchFilters:
    """
    Facts valid at ``as_of``: valid_at <= as_of (or unknown) and, unless history is
    requested, not invalidated at or before ``as_of``.

    Graphiti ORs the outer lists and ANDs the inner ones. It names date params by
    inner index only, so at most one OR-group per field may carry a date.
    """
    valid_at = [
        [DateFilter(date=as_of, comparison_operator=ComparisonOperator.less_than_equal)],
        [DateFilter(comparison_operator=ComparisonOperator.is_null)],
    ]
    invalid_at = None
    if not include_invalidated:
        invalid_at = [
            [DateFilter(date=as_of, comparison_operator=ComparisonOperator.greater_than)],
            [DateFilter(comparison_operator=ComparisonOperator.is_null)],
        ]
    return SearchFilters(valid_at=valid_at, invalid_at=invalid_at)


def _window(since: datetime, until: datetime) -> list[list[DateFilter]]:
    return [
        [
            DateFilter(date=since, comparison_operator=ComparisonOperator.greater_than_equal),
            DateFilter(date=until, comparison_operator=ComparisonOperator.less_than_equal),
        ]
    ]


def _paper_header(paper: PaperMeta) -> str:
    parts = [f"Paper: {paper.title} ({paper.paper_id})"]
    if paper.authors:
        parts.append(f"Authors: {', '.join(paper.authors)}")
    published = paper.published_at.date().isoformat() if paper.published_at else paper.year
    if paper.venue or published:
        parts.append(f"Published: {' '.join(str(p) for p in (paper.venue, published) if p)}")
    return "\n".join(parts)


class GraphitiPaperMemoryBackend(PaperMemoryBackend):
    """
    Writes episodes into Graphiti (which extracts entities and temporal fact edges
    with the local LLM) and answers hybrid, time-aware fact queries.

    Idempotency: each episode gets a deterministic name derived from its identity
    and a hash of its body; an episode whose name already exists is not re-ingested.
    Changed content produces a new episode, so history is preserved and Graphiti's
    edge invalidation records what was superseded.
    """

    def __init__(
        self, graphiti_factory: Callable[[], Graphiti], *, max_concurrent_episodes: int = 1
    ) -> None:
        # Graphiti is built lazily in init(): the FalkorDB client connects in its
        # constructor, and the service must start (and report not-ready) while the
        # database is still down.
        self._graphiti_factory = graphiti_factory
        self._graphiti_instance: Graphiti | None = None
        self._episode_slots = asyncio.Semaphore(max_concurrent_episodes)

    @property
    def _graphiti(self) -> Graphiti:
        if self._graphiti_instance is None:
            raise RuntimeError("GraphitiPaperMemoryBackend.init() has not completed")
        return self._graphiti_instance

    async def init(self) -> None:
        if self._graphiti_instance is None:
            # The constructor performs blocking network I/O; keep it off the event loop.
            self._graphiti_instance = await asyncio.to_thread(self._graphiti_factory)
        await self._graphiti_instance.build_indices_and_constraints()
        logger.info("Graph indices and constraints ready")

    async def close(self) -> None:
        if self._graphiti_instance is not None:
            await self._graphiti_instance.close()

    # ---------------- ingestion ----------------

    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> EpisodeAck:
        body = f"{_paper_header(ep.paper)}\nSection: {ep.section_name}\n\n{ep.text}"
        # Paper claims become valid at publication time, not at ingestion time.
        reference_time = _utc(ep.paper.published_at or ep.created_at)
        key = f"{ep.paper.paper_id}:{ep.section_index}:{ep.chunk_index}"
        return await self._add_episode(EpisodeKind.paper_section, key, body, reference_time)

    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> EpisodeAck:
        location = f" at {ep.location_hint}" if ep.location_hint else ""
        body = (
            f"{_paper_header(ep.paper)}\n"
            f"User {ep.note_type} about this paper{location}:\n\n{ep.note_text}"
        )
        key = f"{ep.paper.paper_id}:{ep.note_type}"
        return await self._add_episode(EpisodeKind.paper_note, key, body, _utc(ep.created_at))

    async def add_agent_step(self, ep: AgentStepEpisodeIn) -> EpisodeAck:
        outcome = "succeeded" if ep.succeeded else "failed"
        body = (
            f"Agent run {ep.run_id}, step {ep.step_index} ({outcome}).\n"
            f"Sub-goal: {ep.sub_goal}\n"
            f"Tool used: {ep.tool_name}\n"
            f"Result: {ep.result_summary}"
        )
        key = f"{ep.run_id}:{ep.step_index}"
        return await self._add_episode(EpisodeKind.agent_step, key, body, _utc(ep.created_at))

    async def add_hypothesis(self, ep: HypothesisEpisodeIn) -> EpisodeAck:
        lines = [
            f"Hypothesis {ep.hypothesis_id}, version {ep.version} (status: {ep.status}).",
            f"Statement: {ep.statement}",
        ]
        if ep.rationale:
            lines.append(f"Rationale: {ep.rationale}")
        if ep.confidence is not None:
            lines.append(f"Confidence: {ep.confidence:.2f}")
        key = f"{ep.hypothesis_id}:v{ep.version}"
        return await self._add_episode(
            EpisodeKind.hypothesis, key, "\n".join(lines), _utc(ep.created_at)
        )

    async def _add_episode(
        self, kind: EpisodeKind, key: str, body: str, reference_time: datetime
    ) -> EpisodeAck:
        name = f"{kind.value}:{key}:{_content_hash(body)}"
        async with self._episode_slots:
            existing = await self._find_episode_uuid(name)
            if existing is not None:
                logger.info("Episode already stored, skipping: name=%s uuid=%s", name, existing)
                return EpisodeAck(episode_id=existing, created=False)

            logger.info("Ingesting episode: name=%s chars=%d", name, len(body))
            started = time.perf_counter()
            result = await self._graphiti.add_episode(
                name=name,
                episode_body=body,
                source=EpisodeType.text,
                source_description=kind.value,
                reference_time=reference_time,
                entity_types=ENTITY_TYPES,
                custom_extraction_instructions=EXTRACTION_INSTRUCTIONS,
            )
            await self._date_undated_facts(result.edges, reference_time)

        logger.info(
            "Episode ingested: name=%s uuid=%s nodes=%d edges=%d seconds=%.1f",
            name,
            result.episode.uuid,
            len(result.nodes),
            len(result.edges),
            time.perf_counter() - started,
        )
        return EpisodeAck(
            episode_id=str(result.episode.uuid),
            created=True,
            nodes_extracted=len(result.nodes),
            facts_extracted=len(result.edges),
        )

    async def _date_undated_facts(self, edges: list[EntityEdge], reference_time: datetime) -> None:
        """
        Graphiti only sets valid_at when the LLM finds a date in the text. An undated
        fact would pass every as-of filter, so a paper claim would appear to have been
        known before the paper existed. Default it to the episode's reference time
        (publication date for papers, creation time otherwise).
        """
        undated = [e for e in edges if e.valid_at is None]
        for edge in undated:
            edge.valid_at = reference_time
            await edge.save(self._graphiti.driver)
        if undated:
            logger.info(
                "Defaulted valid_at to %s for %d undated facts",
                reference_time.isoformat(),
                len(undated),
            )

    async def _find_episode_uuid(self, name: str) -> str | None:
        records = await self._query(_FIND_EPISODE_BY_NAME, name=name)
        return str(records[0]["uuid"]) if records else None

    async def _query(self, cypher: str, **params: object) -> list[dict]:
        result = await self._graphiti.driver.execute_query(cypher, **params)
        if result is None:
            return []
        records, _header, _summary = result
        return records

    # ---------------- retrieval ----------------

    async def search_concepts(self, q: ConceptQuery) -> list[MemoryFact]:
        as_of = _utc(q.time_filter_as_of)
        edges = await self._graphiti.search(
            query=q.query_text,
            num_results=q.limit,
            search_filter=as_of_filters(as_of, q.include_invalidated),
        )
        logger.info("Concept search returned %d facts (as_of=%s)", len(edges), as_of.isoformat())
        return await self._to_facts(edges)

    async def fact_changes(self, q: FactChangesQuery) -> FactChanges:
        since, until = _utc(q.since), _utc(q.until)

        added, invalidated = await asyncio.gather(
            self._graphiti.search(
                query=q.query_text,
                num_results=q.limit,
                search_filter=SearchFilters(valid_at=_window(since, until)),
            ),
            self._graphiti.search(
                query=q.query_text,
                num_results=q.limit,
                search_filter=SearchFilters(invalid_at=_window(since, until)),
            ),
        )
        logger.info(
            "Fact changes %s..%s: added=%d invalidated=%d",
            since.isoformat(),
            until.isoformat(),
            len(added),
            len(invalidated),
        )
        return FactChanges(
            added=await self._to_facts(added),
            invalidated=await self._to_facts(invalidated),
        )

    async def _to_facts(self, edges: list[EntityEdge]) -> list[MemoryFact]:
        episode_uuids = sorted({uuid for e in edges for uuid in e.episodes})
        kind_by_episode: dict[str, EpisodeKind] = {}
        if episode_uuids:
            for record in await self._query(_EPISODE_KINDS, uuids=episode_uuids):
                try:
                    kind_by_episode[record["uuid"]] = EpisodeKind(record["source_description"])
                except ValueError:
                    # Episodes written outside this service carry free-form descriptions.
                    logger.debug("Unknown episode source: %s", record["source_description"])

        return [
            MemoryFact(
                fact=e.fact,
                uuid=e.uuid,
                relation=e.name,
                created_at=e.created_at,
                valid_at=e.valid_at,
                invalid_at=e.invalid_at,
                expired_at=e.expired_at,
                episodes=list(e.episodes),
                source_node_uuid=e.source_node_uuid,
                target_node_uuid=e.target_node_uuid,
                source_kinds=sorted(
                    {kind_by_episode[u] for u in e.episodes if u in kind_by_episode},
                    key=lambda k: k.value,
                ),
            )
            for e in edges
        ]
