"""Page-1 metadata extraction — grounded against the page text, never fabricated.

A missing or ungrounded title fails the paper (CLAUDE.md §1/§2/§3): a filename-stem title
would be a stand-in, and a later correction would change the memory episode hash and
duplicate every chunk (see the design's §8). Grounding uses only NFKC normalisation,
casefold and whitespace removal — no natural-language matching (CLAUDE.md §4).

The publication date is bound the same way, at the token level. `_date_tokens` splits the
date text into maximal digit runs and maximal letter (\\p{L}) runs — structural character-class
tokenisation only, never a word list (CLAUDE.md §4). `_find_date_window` requires the claimed
year to sit at the first or last position of the matching token window — the year-at-edge
ordering, not a post-hoc filter over every permutation — because every real printed date layout
(d-m-y, m-d-y, y-m-d, y-d-m) puts the year at an edge; a year landing in the *middle* of a
window is exactly the signature of a window straddling two adjacent printed dates.

Guaranteed: the claimed components are adjacent tokens of `publication_date_text` with the
year at the first or last position of that window. With a day claimed (3-token window) this
rejects windows straddling two adjacent dates, labelled or not — so a page with several dates
(received/revised/accepted/published) can't have its day and month satisfied by mixing digits
from two different printed dates. A numeric month must equal a printed digit token of that
same date; a word month is accepted only when the model names the printed word via `month_text`
and it sits in that same window.

Not guaranteed (semantic, trusted to the model — no NL check is possible under CLAUDE.md §4):
that `month_text` actually denotes `month` (e.g. the model copies "October" and says 9); that
the chosen date is the *publication* date rather than a received/accepted date — the model
picks one printed date and code verifies only that it is one real printed date; numeric
day/month order (`03/04/2024`) — the model's own assignment is taken as given, both orders
pass; a printed day the model leaves out is not detected (existing month-precision behaviour);
a year+month-only claim (2-token window) can still pair the year with a digit from a
neighbouring date or non-date — e.g. `"2025-06-03 2025-10-06"` with month=3, or
`"Volume 3, 2025"` with month=3, both resolve to 2025-03-01. Two tokens have no middle, so no
structural check exists; the model's month is trusted here, exactly as the old digit-run check
trusted it.

Honest raises (known false-reject classes — the paper fails loudly and is retried on rerun,
never silently accepted): ordinal days (`"6th October 2025"`, `"October 6th, 2025"` — `6th`
tokenises to `6`, `th`); CJK `年/月/日` dates (`年`/`月`/`日` are letter tokens interleaved
between the digits, so the components are never adjacent); OCR-split tokens (`"20 25"`); a
word month given without `month_text`; month ranges / bimonthly issues
(`"January–February 2024"` — the year is adjacent to only one month).
"""

from __future__ import annotations

import itertools
import unicodedata
from collections.abc import Callable
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
            "The paper's publication date copied exactly as printed on the page, or null. "
            "If the page lists several dates (e.g. received, revised, accepted, published), "
            "copy only the publication date itself — not the other dates and not their "
            "labels. Never a date of a cited work."
        )
    )
    year: int | None = Field(ge=1900, le=2100)
    month: int | None = Field(ge=1, le=12)
    month_text: str | None = Field(
        description=(
            "If the publication date's month is printed as a word or abbreviation, that "
            "word copied exactly as printed (e.g. 'October', 'Oct.'); null if the month is "
            "printed as a number or not printed."
        )
    )
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


def _date_tokens(text: str) -> list[str]:
    """Maximal digit runs and maximal letter (\\p{L}) runs of NFKC+casefolded text, in order.

    Everything else (whitespace, punctuation, symbols) is a separator and yields no token.
    Structural only: character classes, never words (CLAUDE.md §4). Whitespace is a
    separator here (unlike `_norm`), so "Published October" stays two tokens.
    """
    normed = unicodedata.normalize("NFKC", text).casefold()

    def _char_class(c: str) -> str | None:
        if c.isdecimal():
            return "d"
        if c.isalpha():
            return "l"
        return None

    return [
        "".join(group)
        for key, group in itertools.groupby(normed, key=_char_class)
        if key is not None
    ]


def _digit_component(value: int) -> Callable[[str], bool]:
    """A window predicate: token is a digit run whose integer value equals `value`."""
    return lambda token: token.isdecimal() and int(token) == value


def _letter_component(word: str) -> Callable[[str], bool]:
    """A window predicate: token equals the given (already NFKC+casefolded) letter run."""
    return lambda token: token == word


def _find_date_window(
    tokens: list[str],
    year: Callable[[str], bool],
    others: list[Callable[[str], bool]],
) -> bool:
    """True iff some contiguous window of `tokens` matches all components one-to-one with the
    year at the first or last position — the only layouts real dates use; a year in the middle
    is the signature of a window straddling two adjacent dates."""
    k = 1 + len(others)
    for start in range(len(tokens) - k + 1):
        window = tokens[start : start + k]
        for perm_others in itertools.permutations(others):
            for ordering in ((year, *perm_others), (*perm_others, year)):
                if all(check(token) for check, token in zip(ordering, window, strict=True)):
                    return True
    return False


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
    month_text = result.month_text
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

    if month_text is not None and month is None:
        raise MetadataExtractionError(f"month_text {month_text!r} given without a month number")

    _require_grounded("publication_date_text", text, page1_text)

    # Token-window binding: the year, day (if given) and month (as a digit, or as the exact
    # letter token copied into month_text) must be adjacent tokens of one printed date, year at
    # an edge (CLAUDE.md §1/§6 — see the module docstring).
    others: list[Callable[[str], bool]] = []
    if month is not None:
        if month_text is not None:
            month_tokens = _date_tokens(month_text)
            if len(month_tokens) != 1 or not month_tokens[0].isalpha():
                raise MetadataExtractionError(
                    f"month_text must be a single printed word, got {month_text!r}"
                )
            others.append(_letter_component(month_tokens[0]))
        else:
            others.append(_digit_component(month))
    if day is not None:
        others.append(_digit_component(day))

    if not _find_date_window(_date_tokens(text), _digit_component(year), others):
        month_desc = repr(month_text) if month_text is not None else month
        raise MetadataExtractionError(
            f"no single printed date in {text!r} has year={year} month={month_desc} day={day}"
        )

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
