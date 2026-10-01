"""BLOCK_POLICY: the single source of truth mapping an OCR block label to how it is spoken.

The keys are DeepSeek-OCR's own closed label vocabulary (model protocol tokens), not prose
keywords; no heading text is ever matched. An unknown label fails prepare (UnknownBlockRefError):
extending this table is a deliberate, reviewed change, never a silent guess.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from voice_service.core.errors import UnknownBlockRefError


class BlockDisposition(Enum):
    HEADING = "heading"  # starts a new logical section; heading text is spoken
    SPEAK = "speak"  # normalised and spoken
    OMIT = "omit"  # not spoken; recorded in the section's omitted[]


BLOCK_POLICY: Mapping[str, BlockDisposition] = {
    "title": BlockDisposition.HEADING,
    "sub_title": BlockDisposition.HEADING,
    "text": BlockDisposition.SPEAK,
    "image": BlockDisposition.OMIT,
    "table": BlockDisposition.OMIT,
    "equation": BlockDisposition.OMIT,
    "image_caption": BlockDisposition.OMIT,
    "table_caption": BlockDisposition.OMIT,
    "table_footnote": BlockDisposition.OMIT,
}


def disposition(ref: str, page_number: int) -> BlockDisposition:
    try:
        return BLOCK_POLICY[ref]
    except KeyError:
        raise UnknownBlockRefError(ref, page_number) from None
