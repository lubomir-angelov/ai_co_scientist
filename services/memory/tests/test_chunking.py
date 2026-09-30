from __future__ import annotations

import pytest

from memory_service.chunking import chunk_text


def test_short_text_is_single_chunk() -> None:
    assert chunk_text("A microring resonator.", 100) == ["A microring resonator."]


def test_paragraphs_are_packed_up_to_limit() -> None:
    text = "aaaa\n\nbbbb\n\ncccc"
    assert chunk_text(text, 10) == ["aaaa\n\nbbbb", "cccc"]


def test_long_paragraph_splits_on_whitespace() -> None:
    chunks = chunk_text("one two three four five", 9)
    assert chunks == ["one two", "three", "four five"]
    assert all(len(c) <= 9 for c in chunks)


def test_overlong_word_is_hard_split() -> None:
    assert chunk_text("x" * 25, 10) == ["x" * 10, "x" * 10, "x" * 5]


def test_blank_text_has_no_chunks() -> None:
    assert chunk_text("  \n\n  ", 10) == []


def test_chunking_is_deterministic() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20))
    assert chunk_text(text, 500) == chunk_text(text, 500)


def test_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        chunk_text("text", 0)
