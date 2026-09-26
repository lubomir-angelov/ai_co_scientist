from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_filters import ComparisonOperator

from memory_service.graphiti_paper_backend import GraphitiPaperMemoryBackend, as_of_filters
from memory_service.ontology import ENTITY_TYPES
from shared_library.data_contracts import (
    AgentStepEpisodeIn,
    ConceptQuery,
    EpisodeKind,
    FactChangesQuery,
    HypothesisEpisodeIn,
    PaperMeta,
    PaperNoteEpisodeIn,
    PaperSectionEpisodeIn,
)

PUBLISHED = datetime(2021, 5, 1, tzinfo=UTC)
PAPER = PaperMeta(
    paper_id="arxiv:2105.00001",
    title="Low-loss microring resonators",
    authors=["A. Author"],
    year=2021,
    published_at=PUBLISHED,
)


def make_graphiti(existing_episode: str | None = None, kinds: list[dict] | None = None):
    """Fake Graphiti: execute_query answers the episode-name lookup and episode-kind lookup."""

    async def execute_query(cypher: str, **params):
        if "name: $name" in cypher:
            rows = [{"uuid": existing_episode}] if existing_episode else []
        else:
            rows = [r for r in (kinds or []) if r["uuid"] in params["uuids"]]
        return rows, ["uuid"], None

    graphiti = MagicMock()
    graphiti.driver.execute_query = AsyncMock(side_effect=execute_query)
    graphiti.add_episode = AsyncMock(
        return_value=SimpleNamespace(
            episode=SimpleNamespace(uuid="ep-new"), nodes=[1, 2, 3], edges=[1, 2]
        )
    )
    graphiti.search = AsyncMock(return_value=[])
    graphiti.build_indices_and_constraints = AsyncMock()
    graphiti.close = AsyncMock()
    return graphiti


async def ready_backend(graphiti, **kwargs) -> GraphitiPaperMemoryBackend:
    backend = GraphitiPaperMemoryBackend(lambda: graphiti, **kwargs)
    await backend.init()
    return backend


def make_edge(uuid: str, episodes: list[str], invalid_at: datetime | None = None) -> EntityEdge:
    return EntityEdge(
        uuid=uuid,
        group_id="_",
        source_node_uuid="n-src",
        target_node_uuid="n-dst",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        name="REPORTS_RESULT",
        fact="The resonator reaches Q = 1.2e6 at 1550 nm.",
        episodes=episodes,
        valid_at=PUBLISHED,
        invalid_at=invalid_at,
    )


async def test_section_episode_uses_publication_time_and_ontology() -> None:
    graphiti = make_graphiti()
    backend = await ready_backend(graphiti)

    ack = await backend.add_paper_section(
        PaperSectionEpisodeIn(
            paper=PAPER, section_name="Results", section_index=3, chunk_index=0, text="Q = 1.2e6"
        )
    )

    assert ack.created and ack.episode_id == "ep-new"
    assert (ack.nodes_extracted, ack.facts_extracted) == (3, 2)
    kwargs = graphiti.add_episode.await_args.kwargs
    assert kwargs["reference_time"] == PUBLISHED
    assert kwargs["source"] == EpisodeType.text
    assert kwargs["source_description"] == EpisodeKind.paper_section.value
    assert kwargs["entity_types"] is ENTITY_TYPES
    assert kwargs["name"].startswith("paper_section:arxiv:2105.00001:3:0:")
    assert "Section: Results" in kwargs["episode_body"]
    assert "Low-loss microring resonators" in kwargs["episode_body"]


async def test_existing_episode_is_not_reingested() -> None:
    graphiti = make_graphiti(existing_episode="ep-old")
    backend = await ready_backend(graphiti)

    ack = await backend.add_paper_section(
        PaperSectionEpisodeIn(
            paper=PAPER, section_name="Abstract", section_index=0, chunk_index=0, text="t"
        )
    )

    assert not ack.created and ack.episode_id == "ep-old"
    graphiti.add_episode.assert_not_awaited()


async def test_episode_name_changes_with_content() -> None:
    graphiti = make_graphiti()
    backend = await ready_backend(graphiti)
    section = dict(paper=PAPER, section_name="Abstract", section_index=0, chunk_index=0)

    await backend.add_paper_section(PaperSectionEpisodeIn(**section, text="version one"))
    await backend.add_paper_section(PaperSectionEpisodeIn(**section, text="version two"))

    names = [c.kwargs["name"] for c in graphiti.add_episode.await_args_list]
    assert names[0] != names[1]


async def test_naive_created_at_is_treated_as_utc() -> None:
    graphiti = make_graphiti()
    backend = await ready_backend(graphiti)

    await backend.add_paper_note(
        PaperNoteEpisodeIn(paper=PAPER, note_text="Why SOI?", created_at=datetime(2026, 2, 1))
    )

    assert graphiti.add_episode.await_args.kwargs["reference_time"] == datetime(
        2026, 2, 1, tzinfo=UTC
    )


async def test_agent_step_and_hypothesis_are_tagged_by_kind() -> None:
    graphiti = make_graphiti()
    backend = await ready_backend(graphiti)

    await backend.add_agent_step(
        AgentStepEpisodeIn(
            run_id="run-1",
            step_index=2,
            sub_goal="Extract Q factors",
            tool_name="Document_Parser_OCR_Tool",
            result_summary="Found Q = 1.2e6",
            succeeded=False,
        )
    )
    await backend.add_hypothesis(
        HypothesisEpisodeIn(
            hypothesis_id="H1", version=2, statement="SiN beats SOI for Q", confidence=0.4
        )
    )

    step, hyp = (c.kwargs for c in graphiti.add_episode.await_args_list)
    assert step["source_description"] == "agent_step"
    assert "(failed)" in step["episode_body"]
    assert hyp["source_description"] == "hypothesis"
    assert hyp["name"].startswith("hypothesis:H1:v2:")
    assert "Confidence: 0.40" in hyp["episode_body"]


def test_as_of_filter_excludes_invalidated_by_default() -> None:
    as_of = datetime(2023, 1, 1, tzinfo=UTC)

    current = as_of_filters(as_of, include_invalidated=False)
    history = as_of_filters(as_of, include_invalidated=True)

    assert current.valid_at[0][0].date == as_of
    assert current.valid_at[0][0].comparison_operator == ComparisonOperator.less_than_equal
    assert current.valid_at[1][0].comparison_operator == ComparisonOperator.is_null
    assert current.invalid_at[0][0].comparison_operator == ComparisonOperator.greater_than
    assert current.invalid_at[1][0].comparison_operator == ComparisonOperator.is_null
    assert history.invalid_at is None


async def test_search_maps_edges_and_source_kinds() -> None:
    graphiti = make_graphiti(
        kinds=[
            {"uuid": "ep-paper", "source_description": "paper_section"},
            {"uuid": "ep-hyp", "source_description": "hypothesis"},
            {"uuid": "ep-ext", "source_description": "something external"},
        ]
    )
    graphiti.search.return_value = [make_edge("e1", ["ep-paper", "ep-hyp", "ep-ext"])]
    backend = await ready_backend(graphiti)

    facts = await backend.search_concepts(
        ConceptQuery(query_text="microring Q factor", time_filter_as_of=datetime(2023, 1, 1))
    )

    kwargs = graphiti.search.await_args.kwargs
    assert kwargs["query"] == "microring Q factor"
    assert kwargs["num_results"] == 30
    assert kwargs["search_filter"].valid_at[0][0].date == datetime(2023, 1, 1, tzinfo=UTC)
    [fact] = facts
    assert fact.uuid == "e1" and fact.relation == "REPORTS_RESULT"
    assert fact.valid_at == PUBLISHED
    assert fact.source_kinds == [EpisodeKind.hypothesis, EpisodeKind.paper_section]


async def test_fact_changes_searches_added_and_invalidated_windows() -> None:
    graphiti = make_graphiti()
    invalidated_edge = make_edge("e2", [], invalid_at=datetime(2024, 6, 1, tzinfo=UTC))
    graphiti.search.side_effect = [[make_edge("e1", [])], [invalidated_edge]]
    backend = await ready_backend(graphiti)
    since, until = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC)

    changes = await backend.fact_changes(
        FactChangesQuery(query_text="PCM photonics", since=since, until=until)
    )

    added_filter, invalid_filter = (
        c.kwargs["search_filter"] for c in graphiti.search.await_args_list
    )
    assert [f.date for f in added_filter.valid_at[0]] == [since, until]
    assert added_filter.invalid_at is None
    assert [f.date for f in invalid_filter.invalid_at[0]] == [since, until]
    assert [f.uuid for f in changes.added] == ["e1"]
    assert [f.uuid for f in changes.invalidated] == ["e2"]


async def test_concurrent_episodes_are_serialised() -> None:
    graphiti = make_graphiti()
    in_flight = 0
    peak = 0

    async def slow_add_episode(**kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return SimpleNamespace(episode=SimpleNamespace(uuid="x"), nodes=[], edges=[])

    graphiti.add_episode.side_effect = slow_add_episode
    backend = await ready_backend(graphiti, max_concurrent_episodes=1)

    await asyncio.gather(
        *(
            backend.add_paper_note(PaperNoteEpisodeIn(paper=PAPER, note_text=f"note {i}"))
            for i in range(3)
        )
    )
    assert peak == 1


@pytest.mark.parametrize("result", [None, ([], [], None)])
async def test_query_handles_empty_driver_results(result) -> None:
    graphiti = make_graphiti()
    graphiti.driver.execute_query = AsyncMock(return_value=result)
    backend = await ready_backend(graphiti)

    ack = await backend.add_paper_note(PaperNoteEpisodeIn(paper=PAPER, note_text="n"))
    assert ack.created


async def test_graphiti_is_built_lazily_and_init_is_retryable() -> None:
    graphiti = make_graphiti()
    graphiti.build_indices_and_constraints.side_effect = [ConnectionError("down"), None]
    built = []

    def factory():
        built.append(1)
        return graphiti

    backend = GraphitiPaperMemoryBackend(factory)
    assert built == []
    await backend.close()  # closing before init is a no-op
    with pytest.raises(RuntimeError):
        await backend.add_paper_note(PaperNoteEpisodeIn(paper=PAPER, note_text="n"))

    with pytest.raises(ConnectionError):
        await backend.init()
    await backend.init()
    assert built == [1]
