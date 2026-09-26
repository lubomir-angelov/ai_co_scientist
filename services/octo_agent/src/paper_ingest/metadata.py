"""Page-1 metadata extraction — grounded against the page text, never fabricated.

A missing or ungrounded title fails the paper (CLAUDE.md §1/§2/§3): a filename-stem title
would be a stand-in, and a later correction would change the memory episode hash and
duplicate every chunk (see the design's §8). Grounding uses only NFKC normalisation,
casefold and whitespace removal — no natural-language matching (CLAUDE.md §4). The date's
year/day are additionally checked against the digit runs of the grounded date text itself
(also structural, not linguistic), so a value is never accepted merely because *some* text
was found on the page — the specific digits claimed must actually be present.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field

from paper_ingest.identity import PaperIdentity
from paper_ingest.state import ResolvedMeta


class Page1Title(BaseModel):
    title: str | None = Field(
        description=(
            "The paper's own title copied character-for-character from the page text, "
            "or null if the page shows no paper title."
        )
    )


class Page1TitleAndDate(Page1Title):
    publication_date_text: str | None = Field(
        description=(
            "The publication date exactly as printed on the page (not received/accepted "
            "dates, not dates of cited works), or null."
        )
    )
    year: int | None = Field(ge=1900, le=2100)
    month: int | None = Field(ge=1, le=12)
    day: int | None = Field(ge=1, le=31)


class MetadataExtractionError(RuntimeError):
    """Page-1 metadata could not be honestly resolved (missing title, or an ungrounded claim)."""


class StructuredEngine(Protocol):
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = ...,
        temperature: float = ...,
        max_tokens: int = ...,
        response_format: type[BaseModel] | None = ...,
    ) -> BaseModel: ...


_TITLE_SYSTEM_PROMPT = (
    "You transcribe metadata from the first page of a scientific paper. Copy values "
    "exactly as printed; answer null for anything not actually shown on the page."
)


def _norm(s: str) -> str:
    """NFKC + casefold + whitespace removal — absorbs OCR spacing artefacts, no NL matching."""
    return "".join(c for c in unicodedata.normalize("NFKC", s).casefold() if not c.isspace())


def _require_grounded(field: str, candidate: str, page1_text: str) -> str:
    """Return the normalized candidate, or raise if it is empty or not on page 1."""
    normed = _norm(candidate)
    if not normed:
        raise MetadataExtractionError(f"{field} is empty after normalization: {candidate!r}")
    if normed not in _norm(page1_text):
        raise MetadataExtractionError(f"{field} not found verbatim on page 1: {candidate!r}")
    return normed


def _date_digit_runs(normed_date_text: str) -> list[int]:
    """The digit runs in a normalized date string, in order. Structural only — no NL."""
    return [int(run) for run in re.findall(r"\d+", normed_date_text)]


def resolve_metadata(
    identity: PaperIdentity, page1_text: str, engine: StructuredEngine
) -> ResolvedMeta:
    """Extract and ground the paper's title (and, absent a filename date, its date)."""
    has_filename_date = identity.arxiv_published_at is not None
    schema: type[Page1Title] = Page1Title if has_filename_date else Page1TitleAndDate

    prompt = f"Page 1 text:\n\n{page1_text}"
    result = engine.generate(
        prompt,
        system_prompt=_TITLE_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=1024,
        response_format=schema,
    )

    if result.title is None:
        raise MetadataExtractionError("no title on page 1")
    _require_grounded("title", result.title, page1_text)

    if has_filename_date:
        return ResolvedMeta(
            title=result.title,
            published_at=identity.arxiv_published_at,
            year=identity.arxiv_published_at.year,
            published_at_source="arxiv_filename",
        )

    if not isinstance(result, Page1TitleAndDate):
        raise TypeError(f"expected Page1TitleAndDate, got {type(result).__name__}")
    published_at, year = _resolve_date(result, page1_text)
    source = "page1_llm" if (published_at is not None or year is not None) else None
    return ResolvedMeta(
        title=result.title, published_at=published_at, year=year, published_at_source=source
    )


def _resolve_date(result: Page1TitleAndDate, page1_text: str) -> tuple[datetime | None, int | None]:
    text = result.publication_date_text
    year = result.year
    month = result.month
    day = result.day

    if text is None and year is None and month is None and day is None:
        return None, None

    if text is None and (year is not None or month is not None or day is not None):
        raise MetadataExtractionError(
            "structured date given without the printed date text it came from"
        )

    # From here on `text` is guaranteed set (the branch above already raised otherwise).
    if year is None:
        raise MetadataExtractionError(f"model gave publication_date_text {text!r} without a year")

    if day is not None and month is None:
        raise MetadataExtractionError("model gave day without month")

    normed = _require_grounded("publication_date_text", text, page1_text)

    # Structural digit check: the year and (if given) day the model claims must actually be
    # among the digit runs of the date string it says it copied. This catches a model that
    # names a real, grounded-looking date string but attaches a year/day it invented.
    runs = _date_digit_runs(normed)
    if year not in runs:
        raise MetadataExtractionError(f"year {year} not present in printed date {text!r}")
    runs.remove(year)

    if day is not None:
        if day not in runs:
            raise MetadataExtractionError(f"day {day} not present in printed date {text!r}")
        runs.remove(day)

    if month is not None:
        numeric_month_candidates = [r for r in runs if 1 <= r <= 12]
        if numeric_month_candidates and month not in numeric_month_candidates:
            raise MetadataExtractionError(
                f"month {month} not present among the remaining printed digits in {text!r}"
            )
        # If no run in 1-12 remains, the month was printed as text (e.g. "March") and can't
        # be checked by structure alone. Its year (and day, if given) are already verified
        # and the date string itself is grounded on page 1, so we accept it as the one
        # residual trust boundary — stated honestly here, not a fallback.

    if month is None:
        if year > datetime.now(UTC).year:
            raise MetadataExtractionError(f"publication year is in the future: {year}")
        return None, year

    try:
        published_at = datetime(year, month, day or 1, tzinfo=UTC)
    except ValueError as exc:
        raise MetadataExtractionError(f"invalid calendar date: {exc}") from exc
    if published_at > datetime.now(UTC):
        raise MetadataExtractionError(f"publication date is in the future: {published_at}")

    return published_at, year
