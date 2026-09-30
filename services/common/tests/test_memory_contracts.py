from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared_library.data_contracts import (
    ConceptQuery,
    EpisodeKind,
    FactChangesQuery,
    HypothesisEpisodeIn,
    MemoryFact,
    PaperIngestRequest,
)


def test_concept_query_defaults_exclude_invalidated_facts():
    q = ConceptQuery(query_text="microring")
    assert q.include_invalidated is False
    assert q.limit == 30


def test_memory_fact_new_fields_are_optional_for_backwards_compatibility():
    fact = MemoryFact(fact="Q = 1.2e6")
    assert fact.source_kinds == [] and fact.uuid is None and fact.relation is None

    fact = MemoryFact(fact="x", source_kinds=["paper_section", "hypothesis"])
    assert fact.source_kinds == [EpisodeKind.paper_section, EpisodeKind.hypothesis]


def test_fact_changes_window_validation_handles_mixed_timezones():
    FactChangesQuery(query_text="x", since=datetime(2024, 1, 1), until=datetime(2024, 6, 1, tzinfo=timezone.utc))
    with pytest.raises(ValidationError, match="since"):
        FactChangesQuery(query_text="x", since=datetime(2025, 1, 1), until=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_hypothesis_version_and_confidence_bounds():
    with pytest.raises(ValidationError):
        HypothesisEpisodeIn(hypothesis_id="H1", version=0, statement="s")
    with pytest.raises(ValidationError):
        HypothesisEpisodeIn(hypothesis_id="H1", version=1, statement="s", confidence=1.5)


def test_paper_ingest_requires_sections():
    with pytest.raises(ValidationError):
        PaperIngestRequest(paper={"paper_id": "p", "title": "t"}, sections=[])
