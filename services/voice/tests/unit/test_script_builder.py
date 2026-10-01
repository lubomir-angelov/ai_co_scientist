from datetime import UTC, datetime

import pytest
from conftest import load_ocr_fixture
from shared_library.data_contracts import OCRBlock, OCRPage, OCRResponse

from voice_service.core.errors import SectionNotFoundError, SectionNotSpeakableError, UnknownBlockRefError
from voice_service.services import script_builder
from voice_service.services.script_builder import build_script, speakable_section

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_sections_split_on_headings_across_pages() -> None:
    script = build_script(load_ocr_fixture(), NOW)
    assert [s.heading for s in script.sections] == [None, "A Photonic Paper", "Methods", "Only A Table", "Results"]
    assert [s.index for s in script.sections] == [0, 1, 2, 3, 4]


def test_front_matter_has_no_heading_and_is_speakable() -> None:
    front = build_script(load_ocr_fixture(), NOW).sections[0]
    assert front.heading is None and front.speakable
    assert [seg.text for seg in front.segments] == ["Alice Example, Bob Sample"]


def test_heading_segment_and_body_normalised() -> None:
    section = build_script(load_ocr_fixture(), NOW).sections[1]
    assert [seg.kind for seg in section.segments] == ["heading", "body"]
    body = section.segments[1].text
    assert "Light²⁵" in body and "10⁶" in body and "[3–5]" in body and "&" in body and "Ω" in body
    assert section.math_spans_converted == 1
    assert section.spoken_char_count == sum(len(s.text) for s in section.segments)


def test_omitted_blocks_recorded_with_page_and_index() -> None:
    script = build_script(load_ocr_fixture(), NOW)
    assert [(o.page_number, o.block_index, o.ref) for o in script.sections[1].omitted] == [(1, 3, "image")]
    assert [(o.page_number, o.block_index, o.ref) for o in script.sections[2].omitted] == [
        (2, 1, "table"),
        (2, 2, "table_caption"),
    ]
    assert [o.ref for o in script.sections[4].omitted] == ["equation"]


def test_heading_followed_only_by_table_is_not_speakable() -> None:
    script = build_script(load_ocr_fixture(), NOW)
    assert script.sections[3].speakable is False
    with pytest.raises(SectionNotSpeakableError):
        speakable_section(script, 3)
    assert speakable_section(script, 2).heading == "Methods"


def test_speakable_section_out_of_range() -> None:
    script = build_script(load_ocr_fixture(), NOW)
    with pytest.raises(SectionNotFoundError):
        speakable_section(script, 99)


def test_page_range_from_member_blocks() -> None:
    script = build_script(load_ocr_fixture(), NOW)
    assert (script.sections[1].page_start, script.sections[1].page_end) == (1, 1)
    assert (script.sections[2].page_start, script.sections[2].page_end) == (2, 2)


def test_whitespace_collapsed_in_body() -> None:
    assert build_script(load_ocr_fixture(), NOW).sections[2].segments[1].text == "We measure things carefully."


def test_hashes_are_deterministic_and_independent_of_built_at() -> None:
    a = build_script(load_ocr_fixture(), NOW)
    b = build_script(load_ocr_fixture(), datetime(2030, 1, 1, tzinfo=UTC))
    assert a.script_sha256 == b.script_sha256 and a.ocr_sha256 == b.ocr_sha256


def test_builder_version_is_recorded() -> None:
    assert build_script(load_ocr_fixture(), NOW).builder_version == script_builder.SCRIPT_BUILDER_VERSION


def test_changed_ocr_changes_hashes() -> None:
    changed = load_ocr_fixture()
    changed.pages[0].blocks[0] = OCRBlock(ref="text", bbox=None, text="Someone Else")
    a, b = build_script(load_ocr_fixture(), NOW), build_script(changed, NOW)
    assert a.ocr_sha256 != b.ocr_sha256 and a.script_sha256 != b.script_sha256


def test_unknown_ref_fails_with_page() -> None:
    resp = load_ocr_fixture()
    resp.pages[1] = OCRPage(page_number=2, blocks=[OCRBlock(ref="margin_note", bbox=None, text="x")])
    with pytest.raises(UnknownBlockRefError, match="page 2"):
        build_script(resp, NOW)


def test_no_pages_gives_no_sections() -> None:
    resp = load_ocr_fixture()
    resp.pages.clear()
    resp.metadata["page_count"] = 0
    assert build_script(resp, NOW).sections == []


def test_heading_block_with_empty_text_gives_empty_heading_not_none() -> None:
    resp = OCRResponse(
        doc_id="d",
        sections=[],
        tables=[],
        pages=[
            OCRPage(
                page_number=1,
                blocks=[
                    OCRBlock(ref="title", bbox=None, text=""),
                    OCRBlock(ref="text", bbox=None, text="body"),
                ],
            )
        ],
        metadata={"page_count": 1},
    )
    assert [s.heading for s in build_script(resp, NOW).sections] == [""]


def test_ocr_fingerprint_is_the_script_ocr_hash() -> None:
    resp = load_ocr_fixture()
    assert build_script(resp, NOW).ocr_sha256 == script_builder.ocr_fingerprint(resp)
