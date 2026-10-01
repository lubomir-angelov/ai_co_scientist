from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from paper_ingest.identity import discover, identify


def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"%PDF-1.4 fake")
    return path


@pytest.mark.parametrize(
    ("filename", "expected_paper_id", "expected_date"),
    [
        ("2510.15511v3.pdf", "arxiv:2510.15511", datetime(2025, 10, 1, tzinfo=UTC)),
        ("2201.12740v3.pdf", "arxiv:2201.12740", datetime(2022, 1, 1, tzinfo=UTC)),
        ("056007_1.pdf", "file:056007_1", None),
        ("28wr-w896.pdf", "file:28wr-w896", None),
        ("s41586-025-09456-3.pdf", "file:s41586-025-09456-3", None),
        ("2513.12345.pdf", "file:2513.12345", None),  # month 13: not a real arXiv id
        ("0612.01234.pdf", "file:0612.01234", None),  # 2006: predates the new scheme
    ],
)
def test_identify_maps_filename_to_paper_id_and_date(
    tmp_path: Path, filename: str, expected_paper_id: str, expected_date
) -> None:
    pdf = _touch(tmp_path, filename)
    identity = identify(pdf)
    assert identity.paper_id == expected_paper_id
    assert identity.arxiv_published_at == expected_date


def test_discover_sorts_and_filters_by_pdf_suffix(tmp_path: Path) -> None:
    _touch(tmp_path, "b.pdf")
    _touch(tmp_path, "a.pdf")
    (tmp_path / "notes.txt").write_text("not a pdf")

    identities = discover(tmp_path)

    assert [i.source_path.name for i in identities] == ["a.pdf", "b.pdf"]


def test_discover_excludes_exact_basenames(tmp_path: Path) -> None:
    _touch(tmp_path, "keep.pdf")
    _touch(tmp_path, "drop.pdf")

    identities = discover(tmp_path, exclude=["drop.pdf"])

    assert [i.source_path.name for i in identities] == ["keep.pdf"]


def test_discover_exclude_typo_raises(tmp_path: Path) -> None:
    _touch(tmp_path, "keep.pdf")

    with pytest.raises(ValueError, match="not found"):
        discover(tmp_path, exclude=["typo.pdf"])


def test_discover_paper_id_collision_raises_naming_both_files(tmp_path: Path) -> None:
    _touch(tmp_path, "2510.15511v1.pdf")
    _touch(tmp_path, "2510.15511v3.pdf")

    with pytest.raises(ValueError, match="collision") as excinfo:
        discover(tmp_path)
    assert "2510.15511v1.pdf" in str(excinfo.value)
    assert "2510.15511v3.pdf" in str(excinfo.value)


def test_filename_that_is_not_a_valid_doc_id_fails_identify_and_discover(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="a b.pdf"):
        identify(Path("a b.pdf"))
    _touch(tmp_path, "ok.pdf")
    _touch(tmp_path, "a b.pdf")
    with pytest.raises(ValueError, match="a b.pdf"):
        discover(tmp_path)
