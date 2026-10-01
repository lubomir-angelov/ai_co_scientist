import ast
from pathlib import Path

import pytest

from voice_service.services import text_normalizer
from voice_service.services.text_normalizer import normalize_block_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2 μm<sup>2</sup>", "2 μm²"),
        ("3 dB cm<sup>-1</sup>", "3 dB cm⁻¹"),
        ("a [100]-oriented wafer along [1, 1, 0]", "a [100]-oriented wafer along [1, 1, 0]"),
        ("range [0, 1]", "range [0, 1]"),
        ("x<sup>2</sup> + y", "x² + y"),
        ("text<sup>25</sup>", "text²⁵"),
        ("effect<sup>25</sup> is known", "effect²⁵ is known"),
        ("as shown [3–5] earlier", "as shown [3–5] earlier"),
        ("x<sup>n</sup>", "xn"),
        ("item [a] and []", "item [a] and []"),
    ],
)
def test_content_is_never_dropped_as_a_citation(raw: str, expected: str) -> None:
    assert normalize_block_text(raw).text == expected


def test_inline_math_converted_to_unicode() -> None:
    result = normalize_block_text(r"the \(\Omega_1\) mode")
    assert "Ω" in result.text and "\\" not in result.text
    assert result.math_spans_converted == 1


def test_display_and_dollar_math_delimiters() -> None:
    result = normalize_block_text(r"a \[ \alpha \] b $\beta$ c")
    assert result.math_spans_converted == 2
    assert "α" in result.text and "β" in result.text


def test_unmatched_dollar_stays_literal() -> None:
    result = normalize_block_text("costs $5 total")
    assert result.text == "costs $5 total"
    assert result.math_spans_converted == 0


def test_math_with_angle_bracket_does_not_break_html_parsing() -> None:
    assert "<" in normalize_block_text(r"if \(a < b\) then").text


def test_entities_unescaped_tags_unwrapped_whitespace_collapsed() -> None:
    result = normalize_block_text("<center>R&amp;D   is\n\tgood</center>")
    assert result.text == "R&D is good"


def test_empty_text() -> None:
    assert normalize_block_text("").text == ""


def test_module_does_not_import_re() -> None:
    tree = ast.parse(Path(text_normalizer.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "re" not in imported
