import pytest

from voice_service.core.errors import UnknownBlockRefError
from voice_service.services.block_policy import BLOCK_POLICY, BlockDisposition, disposition

OBSERVED_REFS = [
    "text", "sub_title", "title", "image", "image_caption", "equation", "table", "table_caption", "table_footnote",
]


@pytest.mark.parametrize("ref", OBSERVED_REFS)
def test_every_observed_ref_has_a_disposition(ref: str) -> None:
    assert isinstance(disposition(ref, 1), BlockDisposition)


def test_policy_covers_exactly_the_observed_refs() -> None:
    assert set(BLOCK_POLICY) == set(OBSERVED_REFS)


def test_headings_and_speech() -> None:
    assert disposition("title", 1) is BlockDisposition.HEADING
    assert disposition("sub_title", 1) is BlockDisposition.HEADING
    assert disposition("text", 1) is BlockDisposition.SPEAK
    assert disposition("table", 1) is BlockDisposition.OMIT


def test_unknown_ref_raises_with_ref_and_page() -> None:
    with pytest.raises(UnknownBlockRefError) as info:
        disposition("footnote_x", 7)
    assert info.value.ref == "footnote_x" and info.value.page_number == 7
    assert "'footnote_x'" in str(info.value) and "page 7" in str(info.value)
