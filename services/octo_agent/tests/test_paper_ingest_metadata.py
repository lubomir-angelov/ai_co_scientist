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
    title, publication_date_text=None, year=None, month=None, month_text=None, day=None
) -> Page1TitleAndDate:
    return Page1TitleAndDate(
        title=title,
        publication_date_text=publication_date_text,
        year=year,
        month=month,
        month_text=month_text,
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
    # No day token in the date text, so the year+month window is exactly the whole text.
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "March 2024", year=2024, month=3, month_text="March")
    )
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
        _titled_date(
            "Solid-State Photonics",
            f"March {future_year}",
            year=future_year,
            month=3,
            month_text="March",
        )
    )
    with pytest.raises(MetadataExtractionError, match="future"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_feb_30_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 30 February 2024\n\nAbstract..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "30 February 2024",
            year=2024,
            month=2,
            month_text="February",
            day=30,
        )
    )
    with pytest.raises(MetadataExtractionError, match="invalid calendar date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_publication_date_text_without_year_raises() -> None:
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "12 March 2024"))
    with pytest.raises(MetadataExtractionError, match="without a year"):
        resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)


# ---- grounding / token-window binding checks (leg-2 H1/H2; date-month-grounding) -------


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
    # "2019" has no window of size 2 (year + month), so no single printed date matches.
    page1 = "Solid-State Photonics\n\nPublished 2019\n\nAbstract: we study..."
    engine = _FakeEngine(_titled_date("Solid-State Photonics", "2019", year=2021, month=5))
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_day_not_in_digit_runs_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 14 July 2023\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "14 July 2023", year=2023, month=7, day=15)
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_numeric_month_mismatch_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 2023-07-14\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "2023-07-14", year=2023, month=8, day=14)
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
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
        _titled_date(
            "Solid-State Photonics",
            "14 July 2023",
            year=2023,
            month=7,
            month_text="July",
            day=14,
        )
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


# ---- token-window binding (date-month-grounding design) --------------------------------

# The live regression fixture (file:opticaq-3-5-445): the model copies the whole
# received/revised/accepted/published line as `publication_date_text`.
_OPTICA_DATES_LINE = (
    "Received 3 June 2025; revised 8 September 2025; accepted 9 September 2025; "
    "published 6 October 2025"
)
_OPTICA_PAGE1 = (
    "Ultra-Low-Loss Photonic Waveguides\n\n" + _OPTICA_DATES_LINE + "\n\nAbstract: we study..."
)


def test_full_multidate_line_binds_to_the_published_date() -> None:
    # Fails on the old digit-run heuristic (leftover "3, 8, 9" all sit in 1..12); the
    # token-window binds year/month/day to the one October window regardless.
    engine = _FakeEngine(
        _titled_date(
            "Ultra-Low-Loss Photonic Waveguides",
            _OPTICA_DATES_LINE,
            year=2025,
            month=10,
            month_text="October",
            day=6,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, _OPTICA_PAGE1, engine)
    assert meta.published_at == datetime(2025, 10, 6, tzinfo=UTC)


def test_narrow_published_date_substring_binds() -> None:
    engine = _FakeEngine(
        _titled_date(
            "Ultra-Low-Loss Photonic Waveguides",
            "6 October 2025",
            year=2025,
            month=10,
            month_text="October",
            day=6,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, _OPTICA_PAGE1, engine)
    assert meta.published_at == datetime(2025, 10, 6, tzinfo=UTC)


def test_day_from_a_different_printed_date_is_rejected() -> None:
    # day=3 belongs to "Received 3 June 2025", not to the October window.
    engine = _FakeEngine(
        _titled_date(
            "Ultra-Low-Loss Photonic Waveguides",
            _OPTICA_DATES_LINE,
            year=2025,
            month=10,
            month_text="October",
            day=3,
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, _OPTICA_PAGE1, engine)


def test_month_from_a_different_printed_date_is_rejected() -> None:
    # "June" is adjacent to day 3, not day 6.
    engine = _FakeEngine(
        _titled_date(
            "Ultra-Low-Loss Photonic Waveguides",
            _OPTICA_DATES_LINE,
            year=2025,
            month=6,
            month_text="June",
            day=6,
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, _OPTICA_PAGE1, engine)


def test_leftover_digit_no_longer_confuses_month_binding() -> None:
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "12 March 2024",
            year=2024,
            month=3,
            month_text="March",
            day=12,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, _PAGE1, engine)
    assert meta.published_at == datetime(2024, 3, 12, tzinfo=UTC)


def test_us_month_day_year_order_resolves() -> None:
    page1 = "Solid-State Photonics\n\nPublished October 6, 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "October 6, 2025",
            year=2025,
            month=10,
            month_text="October",
            day=6,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2025, 10, 6, tzinfo=UTC)


def test_abbreviated_month_with_punctuation_resolves() -> None:
    page1 = "Solid-State Photonics\n\nPublished 6 Oct. 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "6 Oct. 2025",
            year=2025,
            month=10,
            month_text="Oct.",
            day=6,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2025, 10, 6, tzinfo=UTC)


def test_numeric_dot_separated_date_resolves() -> None:
    page1 = "Solid-State Photonics\n\nPublished 14.07.2023\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "14.07.2023", year=2023, month=7, day=14)
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2023, 7, 14, tzinfo=UTC)


def test_numeric_month_without_month_text_is_rejected_for_word_month() -> None:
    page1 = "Solid-State Photonics\n\nPublished 6 October 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "6 October 2025", year=2025, month=10, day=6)
    )
    with pytest.raises(MetadataExtractionError, match="month=10"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_month_text_naming_the_wrong_word_is_rejected() -> None:
    page1 = "Solid-State Photonics\n\nPublished 6 October 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "6 October 2025",
            year=2025,
            month=11,
            month_text="November",
            day=6,
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_multi_word_month_text_is_rejected() -> None:
    page1 = "Solid-State Photonics\n\nPublished 6 October 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "6 October 2025",
            year=2025,
            month=10,
            month_text="October 6",
            day=6,
        )
    )
    with pytest.raises(MetadataExtractionError, match="single printed word"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_month_text_without_month_number_raises() -> None:
    page1 = "Solid-State Photonics\n\nPublished 6 October 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "6 October 2025",
            year=2025,
            month=None,
            month_text="October",
        )
    )
    with pytest.raises(MetadataExtractionError, match="without a month number"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_numeric_day_month_order_is_the_models_claim() -> None:
    # Documents the stated §3 non-guarantee: numeric day/month order is taken as given.
    page1 = "Solid-State Photonics\n\nPublished 03/04/2024\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "03/04/2024", year=2024, month=4, day=3)
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2024, 4, 3, tzinfo=UTC)


def test_year_only_window_from_multidate_line() -> None:
    engine = _FakeEngine(
        _titled_date("Ultra-Low-Loss Photonic Waveguides", _OPTICA_DATES_LINE, year=2025)
    )
    meta = resolve_metadata(_FILE_IDENTITY, _OPTICA_PAGE1, engine)
    assert meta.published_at is None
    assert meta.year == 2025


def test_adjacent_iso_dates_cannot_straddle() -> None:
    # Straddle signature: window [03, 2025, 10] has the year in the middle — the year of
    # the first date sits between the second date's day and month. Must be rejected.
    page1 = "Solid-State Photonics\n\n2025-06-03 2025-10-06\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "2025-06-03 2025-10-06",
            year=2025,
            month=10,
            day=3,
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_adjacent_word_dates_cannot_straddle() -> None:
    # Straddle signature: window [june, 2025, 6] has the year in the middle — the year of
    # the first date sits between the first date's month and the second date's day.
    page1 = "Solid-State Photonics\n\n3 June 2025 / 6 October 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "3 June 2025 / 6 October 2025",
            year=2025,
            month=6,
            month_text="June",
            day=6,
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)


def test_adjacent_iso_dates_bind_to_one_date() -> None:
    # Positive control: year-first window [2025, 10, 06] is one real printed date.
    page1 = "Solid-State Photonics\n\n2025-06-03 2025-10-06\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "2025-06-03 2025-10-06",
            year=2025,
            month=10,
            day=6,
        )
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2025, 10, 6, tzinfo=UTC)


def test_year_month_window_is_trusted_boundary() -> None:
    # Documents the stated §3 non-guarantee: a 2-token year+month window has no middle, so
    # no structural check catches the year pairing with an unrelated digit (mirrors
    # test_numeric_day_month_order_is_the_models_claim).
    page1 = "Solid-State Photonics\n\nVolume 3, 2025\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date("Solid-State Photonics", "Volume 3, 2025", year=2025, month=3)
    )
    meta = resolve_metadata(_FILE_IDENTITY, page1, engine)
    assert meta.published_at == datetime(2025, 3, 1, tzinfo=UTC)


def test_month_range_raises() -> None:
    # Documented honest-raise class: the year is adjacent to only one month of the range.
    page1 = "Solid-State Photonics\n\nJanuary–February 2024\n\nAbstract: we study..."
    engine = _FakeEngine(
        _titled_date(
            "Solid-State Photonics",
            "January–February 2024",
            year=2024,
            month=1,
            month_text="January",
        )
    )
    with pytest.raises(MetadataExtractionError, match="no single printed date"):
        resolve_metadata(_FILE_IDENTITY, page1, engine)
