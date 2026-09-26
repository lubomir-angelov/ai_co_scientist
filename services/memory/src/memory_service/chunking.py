"""Split OCR section text into episode-sized chunks on paragraph boundaries."""

from __future__ import annotations


def chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Pack paragraphs (blank-line separated) into chunks of at most ``max_chars``.

    Paragraphs longer than ``max_chars`` are split on whitespace; a single word
    longer than ``max_chars`` is hard-split. Chunking is deterministic, which keeps
    re-ingestion of the same paper idempotent.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    pieces: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            pieces.extend(_split_long(paragraph, max_chars))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    parts: list[str] = []
    current = ""
    for word in paragraph.split():
        while len(word) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(word[:max_chars])
            word = word[max_chars:]
        if not word:
            continue
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            parts.append(current)
            current = word
    if current:
        parts.append(current)
    return parts
