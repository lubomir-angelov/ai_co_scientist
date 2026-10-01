"""OCRResponse -> PaperScript: logical sections from heading blocks (structural, not linguistic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from shared_library.data_contracts import OCRResponse

from voice_service.core.errors import SectionNotFoundError, SectionNotSpeakableError
from voice_service.models.schemas import (
    OmittedBlock,
    PaperScript,
    ScriptSection,
    ScriptSegment,
)
from voice_service.services.block_policy import BlockDisposition, disposition
from voice_service.services.canonical import canonical_sha256
from voice_service.services.text_normalizer import normalize_block_text

# Part of the idempotency key: bump when normalisation or sectioning changes so stored
# scripts (and the renders keyed on their hash) are rebuilt.
SCRIPT_BUILDER_VERSION = 2


@dataclass
class _SectionDraft:
    heading: str | None
    segments: list[ScriptSegment] = field(default_factory=list)
    omitted: list[OmittedBlock] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    math_spans_converted: int = 0

    def seal(self, index: int) -> ScriptSection:
        return ScriptSection(
            index=index,
            heading=self.heading,
            page_start=min(self.pages),
            page_end=max(self.pages),
            speakable=any(seg.kind == "body" for seg in self.segments),
            segments=self.segments,
            omitted=self.omitted,
            math_spans_converted=self.math_spans_converted,
            spoken_char_count=sum(len(seg.text) for seg in self.segments),
        )


def _current_draft(drafts: list[_SectionDraft]) -> _SectionDraft:
    """The section being filled; blocks before the first heading open a heading-less front matter."""
    if not drafts:
        drafts.append(_SectionDraft(heading=None))
    return drafts[-1]


def ocr_fingerprint(resp: OCRResponse) -> str:
    """The one definition of "this OCR document's content" (idempotency key of a stored script)."""
    return canonical_sha256(resp.model_dump(mode="json"))


def build_script(resp: OCRResponse, built_at: datetime) -> PaperScript:
    drafts: list[_SectionDraft] = []

    for page in resp.pages:
        for block_index, block in enumerate(page.blocks):
            kind = disposition(block.ref, page.page_number)

            if kind is BlockDisposition.OMIT:
                draft = _current_draft(drafts)
                draft.pages.append(page.page_number)
                draft.omitted.append(OmittedBlock(page_number=page.page_number, block_index=block_index, ref=block.ref))
                continue

            normalized = normalize_block_text(block.text)
            if kind is BlockDisposition.HEADING:
                draft = _SectionDraft(heading=normalized.text)
                drafts.append(draft)
            else:
                draft = _current_draft(drafts)

            draft.pages.append(page.page_number)
            draft.math_spans_converted += normalized.math_spans_converted
            if normalized.text:
                draft.segments.append(
                    ScriptSegment(
                        kind="heading" if kind is BlockDisposition.HEADING else "body",
                        page_number=page.page_number,
                        block_index=block_index,
                        text=normalized.text,
                    )
                )

    sections = [draft.seal(index) for index, draft in enumerate(drafts)]
    return PaperScript(
        doc_id=resp.doc_id,
        ocr_sha256=ocr_fingerprint(resp),
        script_sha256=canonical_sha256([s.model_dump(mode="json") for s in sections]),
        builder_version=SCRIPT_BUILDER_VERSION,
        built_at=built_at,
        sections=sections,
    )


def speakable_section(script: PaperScript, index: int) -> ScriptSection:
    """The one definition of "this section may be rendered/streamed"."""
    if not 0 <= index < len(script.sections):
        raise SectionNotFoundError(f"section {index} does not exist (0..{len(script.sections) - 1})")
    section = script.sections[index]
    if not section.speakable:
        raise SectionNotSpeakableError(f"section {index} has no speakable text")
    return section
