"""Paper identity and arXiv-date derivation — structural filename parsing, no natural language.

``paper_id`` is the one identifier used end to end: it is the OCR ``doc_id``, the state-file
name, and the ``PaperMeta.paper_id`` sent to memory.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from shared_library.data_contracts import DocId

# The one definition of a legal document id (shared with OCR and voice): checked at discovery
# time so an unusable filename fails the whole run up front, not at the first OCR call.
_DOC_ID = TypeAdapter(DocId)

# arXiv new-scheme filename: YYMM.NNNN[N] with an optional version suffix, stripped before
# building paper_id. YY < 7 predates the 2007 new numbering scheme, so it is not an arXiv id.
_ARXIV_STEM_RE = re.compile(r"^(?P<yy>\d{2})(?P<mm>\d{2})\.(?P<seq>\d{4,5})(?:v\d+)?$")
_MIN_NEW_SCHEME_YY = 7


@dataclass(frozen=True)
class PaperIdentity:
    """A discovered PDF's identity: its stable id, its file, and its filename-derived date."""

    paper_id: str
    source_path: Path
    arxiv_published_at: datetime | None

    def __post_init__(self) -> None:
        try:
            _DOC_ID.validate_python(self.paper_id)
        except ValidationError as exc:
            raise ValueError(
                f"{self.source_path.name}: derived paper_id {self.paper_id!r} is not a valid DocId: {exc}"
            ) from exc


def _parse_arxiv_stem(stem: str) -> tuple[str, datetime] | None:
    """Return (arxiv_id, month-precision published_at) when ``stem`` is an arXiv id, else None."""
    match = _ARXIV_STEM_RE.match(stem)
    if match is None:
        return None
    yy = int(match.group("yy"))
    mm = int(match.group("mm"))
    if yy < _MIN_NEW_SCHEME_YY or not (1 <= mm <= 12):
        return None
    arxiv_id = f"{match.group('yy')}{match.group('mm')}.{match.group('seq')}"
    published_at = datetime(2000 + yy, mm, 1, tzinfo=UTC)
    return arxiv_id, published_at


def identify(pdf: Path) -> PaperIdentity:
    """Derive a PaperIdentity from a PDF's filename stem (version suffix stripped for arXiv ids)."""
    parsed = _parse_arxiv_stem(pdf.stem)
    if parsed is not None:
        arxiv_id, published_at = parsed
        return PaperIdentity(
            paper_id=f"arxiv:{arxiv_id}", source_path=pdf, arxiv_published_at=published_at
        )
    return PaperIdentity(paper_id=f"file:{pdf.stem}", source_path=pdf, arxiv_published_at=None)


def discover(input_dir: Path, exclude: Sequence[str] = ()) -> list[PaperIdentity]:
    """Discover every PDF in ``input_dir`` (non-recursive, sorted by name) as a PaperIdentity.

    Raises ``ValueError`` before any work is done when an ``exclude`` name is not an actual
    file in ``input_dir`` (catches typos), or when two files map to the same paper_id.
    """
    exclude_set = set(exclude)
    present_names = {p.name for p in input_dir.iterdir() if p.is_file()}
    missing = sorted(exclude_set - present_names)
    if missing:
        raise ValueError(f"--exclude names not found in {input_dir}: {missing}")

    pdfs = sorted(
        p
        for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf" and p.name not in exclude_set
    )
    identities = [identify(pdf) for pdf in pdfs]

    seen: dict[str, Path] = {}
    for identity in identities:
        collision = seen.get(identity.paper_id)
        if collision is not None:
            raise ValueError(
                f"paper_id collision {identity.paper_id!r}: "
                f"{collision} and {identity.source_path}"
            )
        seen[identity.paper_id] = identity.source_path

    return identities
