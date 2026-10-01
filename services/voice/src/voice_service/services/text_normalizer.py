"""Structural normalisation of one OCR text block into speakable text.

Structural scanning only (HTML tags, math delimiters, Unicode superscript mapping): no word
lists, no regular expressions on prose (CLAUDE.md §4). OCR hyphenation artifacts ("electro- optic") are deliberately NOT repaired:
repair needs lexical knowledge. Citation markers are deliberately NOT stripped either: OCR output
carries no structural citation signal, and the character classes inside ``<sup>`` / ``[...]`` are
exactly those of unit exponents (cm⁻¹), Miller indices ([1, 1, 0]), intervals ([0, 1]) and powers,
so deleting them would delete content. Citation numbers are spoken as written.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from pylatexenc.latex2text import LatexNodes2Text

_LATEX = LatexNodes2Text()

# Math delimiters, longest opener first so "$$" is tried before "$".
_MATH_DELIMITERS: tuple[tuple[str, str], ...] = (("\\(", "\\)"), ("\\[", "\\]"), ("$$", "$$"), ("$", "$"))

# <sup> content is rendered with Unicode superscripts.
_SUPERSCRIPT = str.maketrans("0123456789+-()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾")


@dataclass(frozen=True)
class NormalizedText:
    text: str
    math_spans_converted: int


class _FragmentParser(HTMLParser):
    """Unwraps every tag; yields ("text", s) pieces and ("sup", s) pieces for <sup> elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[tuple[str, str]] = []
        self._sup_depth = 0
        self._sup_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "sup":
            self._sup_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "sup" and self._sup_depth > 0:
            self._sup_depth -= 1
            if self._sup_depth == 0:
                self.pieces.append(("sup", "".join(self._sup_buffer)))
                self._sup_buffer = []

    def handle_data(self, data: str) -> None:
        if self._sup_depth > 0:
            self._sup_buffer.append(data)
        else:
            self.pieces.append(("text", data))

    def finish(self) -> list[tuple[str, str]]:
        self.close()
        if self._sup_depth > 0:
            self.pieces.append(("sup", "".join(self._sup_buffer)))
            self._sup_depth = 0
            self._sup_buffer = []
        return self.pieces


def _split_math(raw: str) -> list[tuple[bool, str]]:
    """Split ``raw`` into (is_math, text) segments; math text excludes its delimiters.

    An opener without a matching closer is not a math span and stays literal text.
    """
    segments: list[tuple[bool, str]] = []
    literal: list[str] = []
    i = 0
    while i < len(raw):
        matched = False
        for opener, closer in _MATH_DELIMITERS:
            if not raw.startswith(opener, i):
                continue
            inner, found, after = raw[i + len(opener) :].partition(closer)
            if not found:
                continue
            if literal:
                segments.append((False, "".join(literal)))
                literal = []
            segments.append((True, inner))
            i = len(raw) - len(after)
            matched = True
            break
        if not matched:
            literal.append(raw[i])
            i += 1
    if literal:
        segments.append((False, "".join(literal)))
    return segments


def normalize_block_text(raw: str) -> NormalizedText:
    out: list[str] = []
    math_spans = 0

    for is_math, segment in _split_math(raw):
        if is_math:
            out.append(_LATEX.latex_to_text(segment).strip())
            math_spans += 1
            continue
        parser = _FragmentParser()
        parser.feed(segment)
        for kind, piece in parser.finish():
            out.append(piece if kind == "text" else piece.translate(_SUPERSCRIPT))

    return NormalizedText(text=" ".join("".join(out).split()), math_spans_converted=math_spans)
