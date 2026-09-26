from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel

from paper_ingest.identity import PaperIdentity
from paper_ingest.metadata import (
    MetadataExtractionError,
    Page1Title,
    Page1TitleAndDate,
    resolve_metadata,
)

_PAGE1 = "Solid- State Photonics\n\nPublished 12 March 2024\n\nAbstract: we study..."

_ARXIV_IDENTITY = PaperIdentity(
    paper_id="arxiv:2410.12345",
    source_path=Path("2410.12345.pdf"),
    arxiv_published_at=datetime(2024, 10, 1, tzinfo=UTC),
)
_FILE_IDENTITY = PaperIdentity(
    paper_id="file:some-paper", source_path=Path("some-paper.pdf"), arxiv_published_at=None
)


def _titled_date(
    title, publication_date_text=None, year=None, month=None, day=None
) -> Page1TitleAndDate:
    return Page1TitleAndDate(
        title=title,
        publication_date_text=publication_date_text,
        year=year,
        month=month,
        day=day,
    )


class _FakeEngine:
    def __init__(self, response: BaseModel) -> None:
        self.response = response
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return self.response


def test_arxiv_path_uses_title_only_schema_and_ignores_page1_date() -> None:
    engine = _FakeEngine(Page1Title(title="Solid-State Photonics"))
    meta = resolve_metadata(_ARXIV_IDENTITY, _PAGE1, engine)

    assert meta.title == "Solid-State Photonics"
    assert meta.published_at == _ARXIV_IDENTITY.arxiv_published_at
    assert meta.year == 2024
    assert meta.published_at_source == "arxiv_filename"


def test_grounded_title_passes_across_ocr_spacing_artifacts() -> None:
    # Title matches "Solid- State Photonics" in the page text once hyphen-spacing is absorbed.
    engine = _FakeEngine(_titled_date("Solid-State Photonics"))
    meta = resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)
    assert meta.title == "Solid-State Photonics"


def test_ungrounded_title_raises() -> None:
    engine = _FakeEngine(_titled_date("A Completely Different Title"))
    with pytest.raises(MetadataExtractionError, match="not found verbatim"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_null_title_raises() -> None:
    engine = _FakeEngine(_titled_date(None))
    with pytest.raises(MetadataExtractionError, match="no title"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_all_null_date_gives_none() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics"))
    meta = resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)
    assert meta.published_at is None
    assert meta.year is None
    assert meta.published_at_source is None


def test_month_only_gives_day_one() -> None:
    # No day digit in the date text, so the month-as-text acceptance path applies cleanly.
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "March 2024", year=2024, month=3))
    meta = resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)
    assert meta.published_at == datetime(2024, 3, 1, tzinfo=UTC)
    assert meta.published_at_source == "page1_llm"


def test_year_only_sets_year_without_published_at() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "2024", year=2024))
    meta = resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)
    assert meta.published_at is None
    assert meta.year == 2024
    assert meta.published_at_source == "page1_llm"


def test_day_without_month_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "12 March 2024", year=2024, day=12))
    with pytest.raises(MetadataExtractionError, match="day"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_ungrounded_date_text_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "1 January 1999", year=1999))
    with pytest.raises(MetadataExtractionError, match="not found verbatim"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_future_date_raises() -> None:
    future_year = (datetime.now(UTC) + timedelta(days=3650)).year
    page1 = f"Solid-State Photonics\n\nPublished March {future_year}\n\nAbstract..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", f"March {future_year}", year=future_year, month=3)
    )
    with pytest.raises(MetadataExtractionError, match="future"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_feb_30_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 30 February 2024\n\nAbstract..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "30 February 2024", year=2024, month=2, day=30)
    )
    with pytest.raises(MetadataExtractionError, match="invalid calendar date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_publication_date_text_without_year_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "12 March 2024"))
    with pytest.raises(MetadataExtractionError, match="without a year"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


# ---- grounding / digit-run checks (leg-2 remediation: H1, H2) --------------------------


def test_empty_title_raises() -> None:
    engine = _FakeEngine(_titled_date(""))
    with pytest.raises(MetadataExtractionError, match="empty after normalization"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_whitespace_title_raises() -> None:
    engine = _FakeEngine(_titled_date("   "))
    with pytest.raises(MetadataExtractionError, match="empty after normalization"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_structured_date_fields_without_printed_text_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", None, year=2024, month=3, day=1))
    with pytest.raises(MetadataExtractionError, match="without the printed date text"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_year_not_in_digit_runs_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 2019\n\nAbstract: we study..."
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "2019", year=2021, month=5))
    with pytest.raises(MetadataExtractionError, match="year 2021 not present"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_day_not_in_digit_runs_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 14 July 2023\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "14 July 2023", year=2023, month=7, day=15)
    )
    with pytest.raises(MetadataExtractionError, match="day 15 not present"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_numeric_month_mismatch_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 2023-07-14\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "2023-07-14", year=2023, month=8, day=14)
    )
    with pytest.raises(MetadataExtractionError, match="month 8 not present"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_year_only_future_raises() -> None:
    future_year = datetime.now(UTC).year + 1
    page1 = f"Solid-State Photonics\n\nPublished {future_year}\n\nAbstract: we study..."
    engine = _FakeEngine(_titled_date("Solid-State Photonics", str(future_year), year=future_year))
    with pytest.raises(MetadataExtractionError, match="future"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_whitespace_date_text_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "   ", year=2024))
    with pytest.raises(MetadataExtractionError, match="empty after normalization"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


def test_day_month_text_date_resolves() -> None:
    page1 = "Solid-State Photonics\n\nPublished 14 July 2023\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "14 July 2023", year=2023, month=7, day=14)
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2023, 7, 14, tzinfo=UTC)


def test_iso_date_resolves() -> None:
    page1 = "Solid-State Photonics\n\nPublished 2023-07-14\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "2023-07-14", year=2023, month=7, day=14)
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2023, 7, 14, tzinfo=UTC)
