from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from shared_library.data_contracts import (
    OCR_FULLTEXT_SECTION,
    OCRBlock,
    OCRPage,
    OCRResponse,
    OCRSection,
    ocr_page_section_name,
)

import paper_ingest.phases as phases_module
from paper_ingest.identity import PaperIdentity
from paper_ingest.metadata import Page1TitleAndDate
from paper_ingest.phases import (
    OCRContractError,
    WorkDirIntegrityError,
    _EtaTracker,
    page_sections,
    run_ingest_phase,
    run_ocr_phase,
)
from paper_ingest.state import OcrDone, PaperState, StageFailed, StateStore
from service_errors import MemoryServiceError, OCRServiceError


def _ocr_response(doc_id: str, page_texts: list[str]) -> OCRResponse:
    pages = [
        OCRSection(name=ocr_page_section_name(i + 1), text=t) for i, t in enumerate(page_texts)
    ]
    combined = "\n\n".join(t for t in page_texts if t.strip())
    sections = ([OCRSection(name=OCR_FULLTEXT_SECTION, text=combined)] if combined else []) + pages
    return OCRResponse(
        doc_id=doc_id,
        sections=sections,
        tables=[],
        pages=[
            OCRPage(page_number=i + 1, blocks=[OCRBlock(ref="text", bbox=None, text=t)])
            for i, t in enumerate(page_texts)
        ],
        metadata={"page_count": len(page_texts)},
    )


class FakeOCRTool:
    """Mimics Document_Parser_OCR_Tool.execute: writes the cache file the batch expects."""

    def __init__(self, store: StateStore, outcomes: dict[str, OCRResponse | Exception]):
        self.store = store
        self.outcomes = outcomes
        self.calls: list[str] = []
        self.output_dir: str | None = None
        self.wrong_path = False

    def set_custom_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir

    def execute(self, *, input_path_or_url, doc_id, timeout_s, save_artifacts):
        self.calls.append(doc_id)
        outcome = self.outcomes[doc_id]
        if isinstance(outcome, Exception):
            raise outcome

        cache_path = self.store.ocr_cache_path(doc_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(outcome.model_dump_json(), encoding="utf-8")
        json_path = str(cache_path) + (".WRONG" if self.wrong_path else "")
        return {
            "doc_id": outcome.doc_id,
            "sections": [s.model_dump(mode="json") for s in outcome.sections],
            "tables": [],
            "pages": [p.model_dump(mode="json") for p in outcome.pages],
            "metadata": outcome.metadata,
            "artifacts": {"json_path": json_path, "markdown_path": None},
        }


class FakeEngine:
    def __init__(self, response: Page1TitleAndDate):
        self.response = response
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return self.response


class FakeMemoryTool:
    def __init__(self, outcomes: dict[str, dict | Exception]):
        self.outcomes = outcomes
        self.calls: list[dict] = []

    def execute(self, action, **kwargs):
        self.calls.append(kwargs)
        paper_id = kwargs["paper"]["paper_id"]
        outcome = self.outcomes[paper_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _identity(name: str) -> PaperIdentity:
    return PaperIdentity(
        paper_id=f"file:{name}", source_path=Path(f"/papers/{name}.pdf"), arxiv_published_at=None
    )


# ---- page_sections --------------------------------------------------------------------


def test_page_sections_drops_fulltext_and_keeps_pages_in_order() -> None:
    resp = _ocr_response("d1", ["one", "two", "three"])
    pages = page_sections(resp)
    assert [p.name for p in pages] == ["Page 1", "Page 2", "Page 3"]
    assert all(p.name != OCR_FULLTEXT_SECTION for p in pages)


def test_page_sections_drift_raises() -> None:
    resp = OCRResponse(
        doc_id="d1",
        sections=[OCRSection(name="Page 1", text="x")],
        tables=[],
        pages=[OCRPage(page_number=1, blocks=[]), OCRPage(page_number=2, blocks=[])],
        metadata={"page_count": 2},
    )
    with pytest.raises(OCRContractError, match="contract violated"):
        page_sections(resp)


# ---- run_ocr_phase ---------------------------------------------------------------------


def test_skips_already_done_paper(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.save(
        PaperState(
            paper_id="file:a",
            source_file="/papers/a.pdf",
            ocr=OcrDone(status="done", finished_at=datetime.now(UTC), seconds=1.0, page_count=3),
        )
    )
    tool = FakeOCRTool(store, {})

    summary = run_ocr_phase([_identity("a")], tool, store, ocr_timeout_seconds=10)

    assert tool.calls == []
    assert summary.outcomes[0].outcome == "already_done"
    assert summary.exit_code == 0


def test_retries_previously_failed_paper(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.save(
        PaperState(
            paper_id="file:a",
            source_file="/papers/a.pdf",
            ocr=StageFailed(
                status="failed",
                finished_at=datetime.now(UTC),
                seconds=1.0,
                error="boom",
                status_code=404,
            ),
        )
    )
    tool = FakeOCRTool(store, {"file:a": _ocr_response("file:a", ["hello"])})

    summary = run_ocr_phase([_identity("a")], tool, store, ocr_timeout_seconds=10)

    assert tool.calls == ["file:a"]
    assert summary.outcomes[0].outcome == "done"
    assert isinstance(store.load("file:a").ocr, OcrDone)


def test_records_4xx_failure_and_continues_to_next_paper(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    tool = FakeOCRTool(
        store,
        {
            "file:a": OCRServiceError("bad request", status_code=400),
            "file:b": _ocr_response("file:b", ["hello"]),
        },
    )

    summary = run_ocr_phase([_identity("a"), _identity("b")], tool, store, ocr_timeout_seconds=10)

    assert tool.calls == ["file:a", "file:b"]
    outcomes = {o.paper_id: o.outcome for o in summary.outcomes}
    assert outcomes == {"file:a": "failed", "file:b": "done"}
    assert summary.exit_code == 1
    assert isinstance(store.load("file:a").ocr, StageFailed)


@pytest.mark.parametrize("status_code", [None, 503])
def test_aborts_run_on_unknown_or_backend_down_status(tmp_path: Path, status_code) -> None:
    store = StateStore(tmp_path)
    tool = FakeOCRTool(
        store,
        {
            "file:a": OCRServiceError("down", status_code=status_code),
            "file:b": _ocr_response("file:b", ["hello"]),
        },
    )

    with pytest.raises(OCRServiceError):
        run_ocr_phase([_identity("a"), _identity("b")], tool, store, ocr_timeout_seconds=10)

    assert tool.calls == ["file:a"]  # never reached paper b
    assert isinstance(store.load("file:a").ocr, StageFailed)


def test_all_empty_pages_is_a_failure_not_an_abort(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    tool = FakeOCRTool(store, {"file:a": _ocr_response("file:a", ["   ", "\n"])})

    summary = run_ocr_phase([_identity("a")], tool, store, ocr_timeout_seconds=10)

    assert summary.outcomes[0].outcome == "failed"
    assert "no text" in summary.outcomes[0].error
    assert summary.exit_code == 1


def test_ocr_output_drift_from_expected_cache_path_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    tool = FakeOCRTool(store, {"file:a": _ocr_response("file:a", ["hello"])})
    tool.wrong_path = True

    with pytest.raises(AssertionError, match="cache writer"):
        run_ocr_phase([_identity("a")], tool, store, ocr_timeout_seconds=10)


def test_non_domain_exception_propagates_and_is_not_recorded_as_failure(tmp_path: Path) -> None:
    store = StateStore(tmp_path)

    class _BuggyTool(FakeOCRTool):
        def execute(self, **kwargs):
            raise KeyError("programming bug")

    tool = _BuggyTool(store, {})

    with pytest.raises(KeyError):
        run_ocr_phase([_identity("a")], tool, store, ocr_timeout_seconds=10)

    assert store.load("file:a") is None  # nothing was ever recorded for this paper


# ---- run_ingest_phase -------------------------------------------------------------------


def _ocr_done_state(paper_id: str, source_file: str, page_count: int = 1) -> PaperState:
    return PaperState(
        paper_id=paper_id,
        source_file=source_file,
        ocr=OcrDone(
            status="done", finished_at=datetime.now(UTC), seconds=1.0, page_count=page_count
        ),
    )


def test_blocked_when_ocr_failed(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.save(
        PaperState(
            paper_id="file:a",
            source_file="/papers/a.pdf",
            ocr=StageFailed(
                status="failed",
                finished_at=datetime.now(UTC),
                seconds=1.0,
                error="x",
                status_code=400,
            ),
        )
    )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="T", publication_date_text=None, year=None, month=None, month_text=None, day=None
        )
    )
    memory_tool = FakeMemoryTool({})

    summary = run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10)

    assert summary.outcomes[0].outcome == "blocked"
    assert memory_tool.calls == []


def test_meta_is_persisted_before_ingest_and_reused_on_retry(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF fake")
    store.save(_ocr_done_state("file:a", str(source)))
    store.ocr_cache_path("file:a").parent.mkdir(parents=True, exist_ok=True)
    store.ocr_cache_path("file:a").write_text(
        _ocr_response("file:a", ["Hello Title page text"]).model_dump_json(), encoding="utf-8"
    )

    engine1 = FakeEngine(
        Page1TitleAndDate(
            title="Hello Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool_fail = FakeMemoryTool(
        {"file:a": MemoryServiceError("backend down", status_code=404)}
    )
    run_ingest_phase(engine1, memory_tool_fail, store, ingest_seconds_per_page=10)

    assert engine1.calls == 1
    persisted = store.load("file:a")
    assert persisted.meta is not None
    assert persisted.meta.title == "Hello Title"
    assert isinstance(persisted.ingest, StageFailed)

    engine2 = FakeEngine(
        Page1TitleAndDate(
            title="SHOULD NOT BE CALLED",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool_ok = FakeMemoryTool(
        {
            "file:a": {
                "paper_id": "file:a",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "created": True,
                        "nodes_extracted": 1,
                        "facts_extracted": 1,
                    }
                ],
            }
        }
    )
    summary = run_ingest_phase(engine2, memory_tool_ok, store, ingest_seconds_per_page=10)

    assert engine2.calls == 0  # meta was reused, engine never called again
    assert summary.outcomes[0].outcome == "done"
    assert store.load("file:a").meta.title == "Hello Title"


def test_ingest_timeout_is_seconds_per_page_times_page_count(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF fake")
    store.save(_ocr_done_state("file:a", str(source), page_count=3))
    store.ocr_cache_path("file:a").parent.mkdir(parents=True, exist_ok=True)
    store.ocr_cache_path("file:a").write_text(
        _ocr_response("file:a", ["p1 Title text", "p2", "p3"]).model_dump_json(), encoding="utf-8"
    )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool = FakeMemoryTool(
        {
            "file:a": {
                "paper_id": "file:a",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "created": True,
                        "nodes_extracted": 1,
                        "facts_extracted": 1,
                    }
                ],
            }
        }
    )

    run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=37)

    assert memory_tool.calls[0]["timeout_s"] == 37 * 3


def test_zero_episodes_is_a_failure_that_does_not_abort_the_run(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    for name in ("a", "b"):
        source = tmp_path / f"{name}.pdf"
        source.write_bytes(b"%PDF fake")
        store.save(_ocr_done_state(f"file:{name}", str(source)))
        store.ocr_cache_path(f"file:{name}").parent.mkdir(parents=True, exist_ok=True)
        store.ocr_cache_path(f"file:{name}").write_text(
            _ocr_response(f"file:{name}", ["Title text"]).model_dump_json(), encoding="utf-8"
        )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool = FakeMemoryTool(
        {
            "file:a": {"paper_id": "file:a", "episodes": []},
            "file:b": {
                "paper_id": "file:b",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "created": True,
                        "nodes_extracted": 1,
                        "facts_extracted": 1,
                    }
                ],
            },
        }
    )

    summary = run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10)

    outcomes = {o.paper_id: o for o in summary.outcomes}
    assert outcomes["file:a"].outcome == "failed"
    assert "no episodes" in outcomes["file:a"].error
    assert outcomes["file:b"].outcome == "done"  # the run continued past the failure
    assert summary.exit_code == 1
    assert store.load("file:a").ingest.status_code is None


def test_missing_cache_for_done_ocr_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.save(_ocr_done_state("file:a", "/papers/a.pdf"))
    engine = FakeEngine(
        Page1TitleAndDate(
            title="T", publication_date_text=None, year=None, month=None, month_text=None, day=None
        )
    )
    memory_tool = FakeMemoryTool({})

    with pytest.raises(WorkDirIntegrityError, match="missing"):
        run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10)


def test_identity_drift_between_state_and_source_file_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    source = tmp_path / "b.pdf"  # filename no longer matches the paper_id recorded in state
    source.write_bytes(b"%PDF fake")
    store.save(_ocr_done_state("file:a", str(source)))
    store.ocr_cache_path("file:a").parent.mkdir(parents=True, exist_ok=True)
    store.ocr_cache_path("file:a").write_text(
        _ocr_response("file:a", ["Title text"]).model_dump_json(), encoding="utf-8"
    )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool = FakeMemoryTool({})

    with pytest.raises(WorkDirIntegrityError, match="identity drift"):
        run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10)


def test_eta_is_page_based_across_papers_of_different_sizes(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    for name, page_count in (("a", 10), ("b", 30)):
        source = tmp_path / f"{name}.pdf"
        source.write_bytes(b"%PDF fake")
        store.save(_ocr_done_state(f"file:{name}", str(source), page_count=page_count))
        store.ocr_cache_path(f"file:{name}").parent.mkdir(parents=True, exist_ok=True)
        store.ocr_cache_path(f"file:{name}").write_text(
            _ocr_response(f"file:{name}", ["Title text"] * page_count).model_dump_json(),
            encoding="utf-8",
        )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )
    memory_tool = FakeMemoryTool(
        {
            f"file:{name}": {
                "paper_id": f"file:{name}",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "created": True,
                        "nodes_extracted": 1,
                        "facts_extracted": 1,
                    }
                ],
            }
            for name in ("a", "b")
        }
    )
    # run_started, started_a, finished_a (elapsed=100), started_b, finished_b (elapsed=100),
    # final wall-clock read for the returned PhaseSummary.
    clock_values = iter([0.0, 0.0, 100.0, 100.0, 200.0, 200.0])

    def fake_clock() -> float:
        return next(clock_values)

    logged: list[dict] = []

    def _capture(**kwargs):
        logged.append(kwargs)

    with patch.object(phases_module, "_log_paper_line", side_effect=_capture):
        run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10, clock=fake_clock)

    # After paper "a" (10 pages, 100s -> 10 s/page), 30 pages remain: 10 * 30 == 300.
    assert logged[0]["eta_seconds"] == pytest.approx(300.0)
    assert logged[0]["remaining_pages"] == 30


def test_non_domain_exception_in_ingest_propagates_without_being_recorded(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF fake")
    store.save(_ocr_done_state("file:a", str(source)))
    store.ocr_cache_path("file:a").parent.mkdir(parents=True, exist_ok=True)
    store.ocr_cache_path("file:a").write_text(
        _ocr_response("file:a", ["Title text"]).model_dump_json(), encoding="utf-8"
    )
    engine = FakeEngine(
        Page1TitleAndDate(
            title="Title",
            publication_date_text=None,
            year=None,
            month=None,
            month_text=None,
            day=None,
        )
    )

    class _BuggyMemoryTool(FakeMemoryTool):
        def execute(self, action, **kwargs):
            raise KeyError("programming bug")

    memory_tool = _BuggyMemoryTool({})

    with pytest.raises(KeyError):
        run_ingest_phase(engine, memory_tool, store, ingest_seconds_per_page=10)

    assert store.load("file:a").ingest is None


# ---- ETA -------------------------------------------------------------------------------


def test_eta_is_none_before_first_completion_this_run() -> None:
    tracker = _EtaTracker()
    assert tracker.estimate(5) is None
    tracker.record(1, 10.0)
    assert tracker.estimate(5) == 50.0
