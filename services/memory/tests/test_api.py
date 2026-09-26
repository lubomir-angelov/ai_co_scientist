from __future__ import annotations

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from memory_service.app import create_app
from memory_service.config import Settings
from shared_library.data_contracts import (
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
from shared_library.memory_interface import PaperMemoryBackend

PAPER = {"paper_id": "arxiv:2105.00001", "title": "Low-loss microring resonators"}


class FakeBackend(PaperMemoryBackend):
    """In-memory stand-in that records calls and mimics idempotent episode storage."""

    def __init__(self, fail_init: bool = False) -> None:
        self.fail_init = fail_init
        self.init_calls = 0
        self.closed = False
        self.sections: dict[tuple, str] = {}
        self.raise_on_search: Exception | None = None

    async def init(self) -> None:
        self.init_calls += 1
        if self.fail_init:
            raise RedisConnectionError("falkordb down")

    async def close(self) -> None:
        self.closed = True

    async def add_paper_section(self, ep: PaperSectionEpisodeIn) -> EpisodeAck:
        key = (ep.paper.paper_id, ep.section_index, ep.chunk_index, ep.text)
        if key in self.sections:
            return EpisodeAck(episode_id=self.sections[key], created=False)
        self.sections[key] = f"ep-{len(self.sections)}"
        return EpisodeAck(episode_id=self.sections[key], created=True, facts_extracted=1)

    async def add_paper_note(self, ep: PaperNoteEpisodeIn) -> EpisodeAck:
        return EpisodeAck(episode_id="note-1", created=True)

    async def add_agent_step(self, ep: AgentStepEpisodeIn) -> EpisodeAck:
        return EpisodeAck(episode_id=f"step-{ep.run_id}-{ep.step_index}", created=True)

    async def add_hypothesis(self, ep: HypothesisEpisodeIn) -> EpisodeAck:
        return EpisodeAck(episode_id=f"hyp-{ep.hypothesis_id}-v{ep.version}", created=True)

    async def search_concepts(self, q: ConceptQuery) -> list[MemoryFact]:
        if self.raise_on_search:
            raise self.raise_on_search
        return [MemoryFact(fact=f"fact about {q.query_text}", source_kinds=["paper_section"])]

    async def fact_changes(self, q: FactChangesQuery) -> FactChanges:
        return FactChanges(added=[MemoryFact(fact="new")], invalidated=[])


def make_client(backend: FakeBackend, **settings) -> TestClient:
    settings = Settings(
        llm_model="test-model", init_retries=1, init_retry_delay_seconds=0, **settings
    )
    return TestClient(create_app(settings=settings, backend=backend), raise_server_exceptions=False)


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


def test_health_reports_ready_and_lifecycle(backend: FakeBackend) -> None:
    with make_client(backend) as client:
        body = client.get("/health").json()
    assert body == {
        "status": "ok",
        "service": "memory",
        "ready": True,
        "graph_name": "photonic_memory",
    }
    assert backend.init_calls == 1
    assert backend.closed


def test_backend_down_returns_structured_503_and_retries_lazily() -> None:
    backend = FakeBackend(fail_init=True)
    with make_client(backend) as client:
        assert client.get("/health").json()["ready"] is False

        resp = client.post("/v1/memory/concepts/search", json={"query_text": "ring"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "backend_unavailable"

        backend.fail_init = False
        resp = client.post("/v1/memory/concepts/search", json={"query_text": "ring"})
        assert resp.status_code == 200
        assert client.get("/health").json()["ready"] is True


def test_section_endpoint_is_backwards_compatible(backend: FakeBackend) -> None:
    payload = {
        "paper": PAPER,
        "section_name": "Abstract",
        "section_index": 0,
        "chunk_index": 0,
        "text": "We demonstrate Q = 1.2e6.",
    }
    with make_client(backend) as client:
        first = client.post("/v1/memory/paper/sections", json=payload).json()
        second = client.post("/v1/memory/paper/sections", json=payload).json()
    assert first["episode_id"] == second["episode_id"]
    assert first["created"] is True and second["created"] is False


def test_paper_ingest_chunks_sections_and_resumes(backend: FakeBackend) -> None:
    long_text = "\n\n".join(["alpha " * 30, "beta " * 30, "gamma " * 30])
    payload = {
        "paper": PAPER,
        "sections": [
            {"name": "Abstract", "text": "Short abstract."},
            {"name": "Empty", "text": "   "},
            {"name": "Results", "text": long_text},
        ],
    }
    with make_client(backend, chunk_max_chars=200) as client:
        first = client.post("/v1/memory/paper/ingest", json=payload)
        second = client.post("/v1/memory/paper/ingest", json=payload)

    assert first.status_code == 200
    episodes = first.json()["episodes"]
    assert len(episodes) == 4  # 1 abstract chunk + 3 results chunks, empty section skipped
    assert all(e["created"] for e in episodes)
    assert not any(e["created"] for e in second.json()["episodes"])
    assert {k[1] for k in backend.sections} == {0, 2}  # section_index keeps original order


def test_paper_ingest_rejects_empty_sections(backend: FakeBackend) -> None:
    with make_client(backend) as client:
        resp = client.post("/v1/memory/paper/ingest", json={"paper": PAPER, "sections": []})
    assert resp.status_code == 422


def test_agent_step_and_hypothesis_endpoints(backend: FakeBackend) -> None:
    with make_client(backend) as client:
        step = client.post(
            "/v1/memory/agent/steps",
            json={
                "run_id": "r1",
                "step_index": 0,
                "sub_goal": "parse pdf",
                "tool_name": "Document_Parser_OCR_Tool",
                "result_summary": "3 sections",
            },
        )
        hyp = client.post(
            "/v1/memory/hypotheses",
            json={"hypothesis_id": "H1", "version": 1, "statement": "SiN beats SOI"},
        )
        bad_hyp = client.post(
            "/v1/memory/hypotheses",
            json={"hypothesis_id": "H1", "version": 0, "statement": "x"},
        )
    assert step.json()["episode_id"] == "step-r1-0"
    assert hyp.json()["episode_id"] == "hyp-H1-v1"
    assert bad_hyp.status_code == 422


def test_search_and_changes(backend: FakeBackend) -> None:
    with make_client(backend) as client:
        facts = client.post("/v1/memory/concepts/search", json={"query_text": "ring"}).json()
        changes = client.post(
            "/v1/memory/facts/changes", json={"query_text": "ring", "since": "2024-01-01T00:00:00Z"}
        ).json()
    assert facts[0]["fact"] == "fact about ring"
    assert facts[0]["source_kinds"] == ["paper_section"]
    assert changes["added"][0]["fact"] == "new"


def test_changes_rejects_inverted_window(backend: FakeBackend) -> None:
    with make_client(backend) as client:
        resp = client.post(
            "/v1/memory/facts/changes",
            json={"query_text": "ring", "since": "2025-01-01T00:00:00Z", "until": "2024-01-01"},
        )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (
            openai.APIConnectionError(request=httpx.Request("POST", "http://llm/v1")),
            502,
            "model_unavailable",
        ),
        (RedisConnectionError("gone"), 503, "graph_unavailable"),
        (RuntimeError("secret internals"), 500, "internal_error"),
    ],
)
def test_errors_are_structured_and_do_not_leak(backend: FakeBackend, exc, status, code) -> None:
    backend.raise_on_search = exc
    with make_client(backend) as client:
        resp = client.post("/v1/memory/concepts/search", json={"query_text": "ring"})
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code
    assert "secret internals" not in resp.text


def test_missing_llm_model_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORY_LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="llm_model"):
        Settings()
