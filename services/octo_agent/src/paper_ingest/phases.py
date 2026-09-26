"""Phase 1 (OCR) and Phase 2 (metadata + memory ingest) loops, the page-section contract,
the one abort policy, and the progress/summary renderer shared with the ``status`` command.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from shared_library.data_contracts import (
    OCR_FULLTEXT_SECTION,
    OCRResponse,
    OCRSection,
    PaperMeta,
    ocr_page_section_name,
)

from paper_ingest.identity import PaperIdentity, identify
from paper_ingest.metadata import MetadataExtractionError, StructuredEngine, resolve_metadata
from paper_ingest.state import IngestDone, OcrDone, PaperState, StageFailed, StateStore
from service_errors import ServiceCallError

logger = logging.getLogger(__name__)

Outcome = Literal["done", "already_done", "failed", "blocked", "never_attempted"]


class OCRContractError(ValueError):
    """The OCR response violates the shared page-section contract."""


class WorkDirIntegrityError(RuntimeError):
    """The work directory is inconsistent with the state store (a bug or manual tampering).

    Never recorded as a per-paper failure and never caught by the abort policy — it means a
    guess about the paper's status would be worse than stopping the run outright.
    """


class EmptyIngestError(RuntimeError):
    """Memory accepted the request but produced zero episodes — a per-paper content failure,
    not a service outage."""


# The only exception types the per-paper loop treats as a paper-level (not run-level) failure.
# Anything else is a bug and crashes the run (CLAUDE.md §1).
_CAUGHT_FAILURE_TYPES = (
    ServiceCallError,
    ValidationError,
    OCRContractError,
    MetadataExtractionError,
    EmptyIngestError,
)

_ABORT_STATUS_CODES = frozenset({502, 503, 504})


def _must_abort(exc: BaseException) -> bool:
    """Whether a caught per-paper failure means the whole run must stop.

    ``status_code is None`` (timeout / connection refused) means the service may still be
    processing this request; queuing the next paper behind orphaned work cascades timeouts.
    502/503/504 mean the service or its model dependency is down, so every remaining paper
    would fail identically. Anything else is specific to this paper's content and the run
    continues.
    """
    if not isinstance(exc, ServiceCallError):
        return False
    return exc.status_code is None or exc.status_code in _ABORT_STATUS_CODES


def page_sections(resp: OCRResponse) -> list[OCRSection]:
    """The paper's page sections in order, with FullText dropped (it duplicates every page).

    Raises OCRContractError when ``metadata.page_count`` is missing/non-int, or when the
    section names don't match ``ocr_page_section_name(1..page_count)`` exactly.
    """
    try:
        page_count = resp.metadata["page_count"]
    except KeyError as exc:
        raise OCRContractError(
            f"OCR metadata for doc_id={resp.doc_id!r} is missing page_count"
        ) from exc
    if not isinstance(page_count, int):
        raise OCRContractError(
            f"OCR metadata.page_count for doc_id={resp.doc_id!r} is not an int: {page_count!r}"
        )

    expected = [ocr_page_section_name(i) for i in range(1, page_count + 1)]
    actual_sections = [s for s in resp.sections if s.name != OCR_FULLTEXT_SECTION]
    actual_names = [s.name for s in actual_sections]
    if actual_names != expected:
        raise OCRContractError(
            f"OCR page-section contract violated for doc_id={resp.doc_id!r}: "
            f"expected {expected}, got {actual_names}"
        )
    return actual_sections


@dataclass(frozen=True)
class PaperOutcome:
    paper_id: str
    stage: Literal["ocr", "ingest"]
    outcome: Outcome
    pages: int | None
    seconds: float | None
    error: str | None = None


@dataclass(frozen=True)
class PhaseSummary:
    stage: Literal["ocr", "ingest", "status"]
    outcomes: list[PaperOutcome]
    wall_seconds: float

    @property
    def exit_code(self) -> int:
        return 1 if any(o.outcome in ("failed", "blocked") for o in self.outcomes) else 0


class _EtaTracker:
    """Mean seconds-per-unit over units completed *in this run*. None until the first one."""

    def __init__(self) -> None:
        self._completed_units = 0.0
        self._completed_seconds = 0.0

    def record(self, units: float, seconds: float) -> None:
        self._completed_units += units
        self._completed_seconds += seconds

    def estimate(self, remaining_units: float) -> float | None:
        if self._completed_units <= 0:
            return None
        return (self._completed_seconds / self._completed_units) * remaining_units


def _load_all_states(store: StateStore) -> list[PaperState]:
    """Every known paper's state, loaded once. Raises if a listed state file vanishes before
    it can be loaded — a listing/load race is work-dir tampering, not a paper to skip (§1)."""
    states = []
    for paper_id in store.known_paper_ids():
        state = store.load(paper_id)
        if state is None:
            raise WorkDirIntegrityError(
                f"state file for {paper_id!r} vanished between listing and load"
            )
        states.append(state)
    return states


def _log_paper_line(
    *,
    index: int,
    total: int,
    paper_id: str,
    stage: str,
    verb: str,
    pages: int | None,
    seconds: float | None,
    counts: dict[str, int],
    remaining: int,
    remaining_pages: int | None,
    eta_seconds: float | None,
    eta_unit: str,
) -> None:
    pages_txt = f"{pages}p" if pages is not None else "?p"
    seconds_txt = f"{seconds:.0f}s" if seconds is not None else "?s"
    remaining_txt = (
        f"remaining={remaining} papers/{remaining_pages} pages"
        if remaining_pages is not None
        else f"remaining={remaining} papers"
    )
    eta_txt = (
        f"ETA {eta_seconds / 60:.0f}min (by {eta_unit})"
        if eta_seconds is not None
        else f"ETA n/a (no {eta_unit} completed yet this run)"
    )
    logger.info(
        "[%d/%d] %s %s %s (%s, %s) · done=%d failed=%d blocked=%d %s · %s",
        index,
        total,
        paper_id,
        stage,
        verb,
        pages_txt,
        seconds_txt,
        counts["done"],
        counts["failed"],
        counts["blocked"],
        remaining_txt,
        eta_txt,
    )


def run_ocr_phase(
    identities: list[PaperIdentity],
    tool: Any,
    store: StateStore,
    ocr_timeout_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> PhaseSummary:
    """Phase 1: OCR every not-yet-done paper and validate its page-section contract."""
    tool.set_custom_output_dir(str(store.ocr_dir))
    total = len(identities)
    outcomes: list[PaperOutcome] = []
    counts = {"done": 0, "failed": 0, "blocked": 0}
    eta = _EtaTracker()
    run_started = clock()

    for index, identity in enumerate(identities, start=1):
        paper_id = identity.paper_id
        state = store.load(paper_id)
        if state is None:
            state = PaperState(paper_id=paper_id, source_file=str(identity.source_path))
        remaining = total - index

        if isinstance(state.ocr, OcrDone):
            outcomes.append(
                PaperOutcome(paper_id, "ocr", "already_done", state.ocr.page_count, None)
            )
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ocr",
                verb="skipped",
                pages=state.ocr.page_count,
                seconds=None,
                counts=counts,
                remaining=remaining,
                remaining_pages=None,
                eta_seconds=eta.estimate(remaining),
                eta_unit="paper",
            )
            continue

        started = clock()
        try:
            result = tool.execute(
                input_path_or_url=str(identity.source_path),
                doc_id=paper_id,
                timeout_s=ocr_timeout_seconds,
                save_artifacts=True,
            )
            _assert_ocr_output_matches_layout(result, paper_id, store)
            resp = OCRResponse.model_validate(
                {
                    "doc_id": result["doc_id"],
                    "sections": result["sections"],
                    "tables": result["tables"],
                    "metadata": result["metadata"],
                }
            )
            pages = page_sections(resp)
            if all(not p.text.strip() for p in pages):
                raise OCRContractError("OCR produced no text")

            elapsed = clock() - started
            state.ocr = OcrDone(
                status="done", finished_at=datetime.now(UTC), seconds=elapsed, page_count=len(pages)
            )
            store.save(state)
            eta.record(1, elapsed)
            counts["done"] += 1
            outcomes.append(PaperOutcome(paper_id, "ocr", "done", len(pages), elapsed))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ocr",
                verb="done",
                pages=len(pages),
                seconds=elapsed,
                counts=counts,
                remaining=remaining,
                remaining_pages=None,
                eta_seconds=eta.estimate(remaining),
                eta_unit="paper",
            )
        except _CAUGHT_FAILURE_TYPES as exc:
            elapsed = clock() - started
            status_code = getattr(exc, "status_code", None)
            state.ocr = StageFailed(
                status="failed",
                finished_at=datetime.now(UTC),
                seconds=elapsed,
                error=str(exc),
                status_code=status_code,
            )
            store.save(state)
            logger.error("Phase 1 (OCR) failed for %s", paper_id, exc_info=True)
            counts["failed"] += 1
            outcomes.append(PaperOutcome(paper_id, "ocr", "failed", None, elapsed, str(exc)))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ocr",
                verb="failed",
                pages=None,
                seconds=elapsed,
                counts=counts,
                remaining=remaining,
                remaining_pages=None,
                eta_seconds=eta.estimate(remaining),
                eta_unit="paper",
            )
            if _must_abort(exc):
                partial = PhaseSummary(
                    stage="ocr", outcomes=outcomes, wall_seconds=clock() - run_started
                )
                logger.error("Aborting phase 1 (OCR) run:\n%s", render_summary(partial))
                raise

    return PhaseSummary(stage="ocr", outcomes=outcomes, wall_seconds=clock() - run_started)


def _assert_ocr_output_matches_layout(
    result: dict[str, Any], paper_id: str, store: StateStore
) -> None:
    expected_path = str(store.ocr_cache_path(paper_id))
    if result["artifacts"]["json_path"] != expected_path:
        raise AssertionError(
            f"OCR tool wrote its cache to {result['artifacts']['json_path']!r}, "
            f"expected {expected_path!r} — the tool is meant to be the only cache writer"
        )
    if result["doc_id"] != paper_id:
        raise AssertionError(
            f"OCR tool returned doc_id {result['doc_id']!r}, expected paper_id {paper_id!r}"
        )


def run_ingest_phase(
    engine: StructuredEngine,
    memory_tool: Any,
    store: StateStore,
    ingest_seconds_per_page: float,
    clock: Callable[[], float] = time.monotonic,
) -> PhaseSummary:
    """Phase 2: resolve metadata (once, reused on retry) and ingest every OCR-done paper."""
    states = _load_all_states(store)
    total = len(states)
    outcomes: list[PaperOutcome] = []
    counts = {"done": 0, "failed": 0, "blocked": 0}
    eta = _EtaTracker()
    run_started = clock()
    # Pages known to remain (OCR-done, not yet ingested), so phase 2's ETA is page-based —
    # the unit it actually measures — instead of the per-paper estimate that ignores wildly
    # different page counts across papers.
    pages_remaining = sum(
        s.ocr.page_count
        for s in states
        if isinstance(s.ocr, OcrDone) and not isinstance(s.ingest, IngestDone)
    )

    for index, state in enumerate(states, start=1):
        paper_id = state.paper_id
        remaining = total - index

        if isinstance(state.ingest, IngestDone):
            page_count = state.ocr.page_count if isinstance(state.ocr, OcrDone) else None
            outcomes.append(PaperOutcome(paper_id, "ingest", "already_done", page_count, None))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ingest",
                verb="skipped",
                pages=page_count,
                seconds=None,
                counts=counts,
                remaining=remaining,
                remaining_pages=pages_remaining,
                eta_seconds=eta.estimate(pages_remaining),
                eta_unit="page",
            )
            continue

        if not isinstance(state.ocr, OcrDone):
            counts["blocked"] += 1
            outcomes.append(PaperOutcome(paper_id, "ingest", "blocked", None, None, "OCR not done"))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ingest",
                verb="blocked",
                pages=None,
                seconds=None,
                counts=counts,
                remaining=remaining,
                remaining_pages=pages_remaining,
                eta_seconds=eta.estimate(pages_remaining),
                eta_unit="page",
            )
            continue

        cache_path = store.ocr_cache_path(paper_id)
        if not cache_path.is_file():
            raise WorkDirIntegrityError(
                f"{paper_id}: state says ocr.status=='done' but {cache_path} is missing; "
                f"delete {store.state_path(paper_id)} to redo phase 1 for this paper"
            )

        started = clock()
        try:
            resp = OCRResponse.model_validate_json(cache_path.read_text(encoding="utf-8"))
            pages = page_sections(resp)

            if state.meta is None:
                identity = identify(Path(state.source_file))
                if identity.paper_id != state.paper_id:
                    raise WorkDirIntegrityError(
                        f"identity drift: {state.source_file} now identifies as "
                        f"{identity.paper_id!r}, state has {state.paper_id!r}"
                    )
                state.meta = resolve_metadata(identity, pages[0].text, engine)
                store.save(state)

            paper_meta = PaperMeta(
                paper_id=paper_id,
                title=state.meta.title,
                published_at=state.meta.published_at,
                year=state.meta.year,
            )
            timeout_s = ingest_seconds_per_page * len(pages)
            response = memory_tool.execute(
                "ingest_paper",
                timeout_s=timeout_s,
                paper=paper_meta.model_dump(mode="json"),
                sections=[s.model_dump(mode="json") for s in pages],
            )
            episodes = response["episodes"]
            if len(episodes) == 0:
                raise EmptyIngestError(
                    f"memory produced no episodes for {paper_id} ({len(pages)} sections sent)"
                )

            elapsed = clock() - started
            created = sum(1 for ep in episodes if ep["created"])
            state.ingest = IngestDone(
                status="done",
                finished_at=datetime.now(UTC),
                seconds=elapsed,
                episodes=len(episodes),
                created=created,
            )
            store.save(state)
            eta.record(len(pages), elapsed)
            pages_remaining -= state.ocr.page_count
            counts["done"] += 1
            outcomes.append(PaperOutcome(paper_id, "ingest", "done", len(pages), elapsed))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ingest",
                verb="done",
                pages=len(pages),
                seconds=elapsed,
                counts=counts,
                remaining=remaining,
                remaining_pages=pages_remaining,
                eta_seconds=eta.estimate(pages_remaining),
                eta_unit="page",
            )
        except _CAUGHT_FAILURE_TYPES as exc:
            elapsed = clock() - started
            status_code = getattr(exc, "status_code", None)
            state.ingest = StageFailed(
                status="failed",
                finished_at=datetime.now(UTC),
                seconds=elapsed,
                error=str(exc),
                status_code=status_code,
            )
            store.save(state)
            logger.error("Phase 2 (ingest) failed for %s", paper_id, exc_info=True)
            pages_remaining -= state.ocr.page_count
            counts["failed"] += 1
            outcomes.append(PaperOutcome(paper_id, "ingest", "failed", None, elapsed, str(exc)))
            _log_paper_line(
                index=index,
                total=total,
                paper_id=paper_id,
                stage="ingest",
                verb="failed",
                pages=None,
                seconds=elapsed,
                counts=counts,
                remaining=remaining,
                remaining_pages=pages_remaining,
                eta_seconds=eta.estimate(pages_remaining),
                eta_unit="page",
            )
            if _must_abort(exc):
                partial = PhaseSummary(
                    stage="ingest", outcomes=outcomes, wall_seconds=clock() - run_started
                )
                logger.error("Aborting phase 2 (ingest) run:\n%s", render_summary(partial))
                raise

    return PhaseSummary(stage="ingest", outcomes=outcomes, wall_seconds=clock() - run_started)


def render_summary(summary: PhaseSummary) -> str:
    """The final per-run summary: totals per outcome, total pages, wall time, and every
    failed/blocked paper_id with its stage and full error. Shared by ``status`` (§5.7)."""
    lines = [f"Phase {summary.stage}: wall time {summary.wall_seconds:.0f}s"]
    outcome_names = sorted({o.outcome for o in summary.outcomes})
    for outcome_name in outcome_names:
        matching = [o for o in summary.outcomes if o.outcome == outcome_name]
        pages = sum(o.pages for o in matching if o.pages is not None)
        lines.append(f"  {outcome_name}: {len(matching)} papers, {pages} pages")

    needs_attention = [
        o for o in summary.outcomes if o.outcome in ("failed", "blocked", "never_attempted")
    ]
    if needs_attention:
        lines.append("Papers needing attention:")
        for o in needs_attention:
            lines.append(f"  {o.paper_id} [{o.stage}] {o.outcome}: {o.error}")
    return "\n".join(lines)


def render_status(store: StateStore) -> str:
    """Read-only per-paper status table for the ``status`` subcommand (no network calls)."""
    outcomes: list[PaperOutcome] = []
    for state in _load_all_states(store):
        outcomes.append(_state_to_outcome(state, "ocr", state.ocr))
        outcomes.append(_state_to_outcome(state, "ingest", state.ingest))
    return render_summary(PhaseSummary(stage="status", outcomes=outcomes, wall_seconds=0.0))


def _state_to_outcome(
    state: PaperState,
    stage: Literal["ocr", "ingest"],
    stage_state: OcrDone | IngestDone | StageFailed | None,
) -> PaperOutcome:
    if stage_state is None:
        return PaperOutcome(state.paper_id, stage, "never_attempted", None, None, "never attempted")
    if isinstance(stage_state, StageFailed):
        return PaperOutcome(
            state.paper_id, stage, "failed", None, stage_state.seconds, stage_state.error
        )
    pages = stage_state.page_count if isinstance(stage_state, OcrDone) else None
    return PaperOutcome(state.paper_id, stage, "done", pages, stage_state.seconds)
