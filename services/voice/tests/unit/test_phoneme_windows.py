import random

import pytest

from voice_service.core.errors import PhonemeWindowError
from voice_service.services.backends import PhonemeToken
from voice_service.services.phoneme_windows import KOKORO_MAX_PHONEMES, pack_phoneme_windows


def tok(p: str | None, ws: bool = False, punct: bool = False) -> PhonemeToken:
    return PhonemeToken(phonemes=p, whitespace=ws, is_punctuation=punct)


def full_stream(tokens: list[PhonemeToken]) -> str:
    return "".join(("" if t.phonemes is None else t.phonemes) + (" " if t.whitespace else "") for t in tokens)


def test_kokoro_bound_is_510() -> None:
    assert KOKORO_MAX_PHONEMES == 510


def test_short_stream_is_one_window() -> None:
    tokens = [tok("ab", True), tok("cd")]
    windows = pack_phoneme_windows(tokens, 50)
    assert [w.phonemes for w in windows] == ["ab cd"]


def test_empty_stream_has_no_windows() -> None:
    assert pack_phoneme_windows([], 10) == []


def test_cut_prefers_punctuation_over_whitespace() -> None:
    tokens = [tok("aaa", True), tok("bb"), tok(".", True, True), tok("cccc", True), tok("dddd")]
    windows = pack_phoneme_windows(tokens, 12)
    assert windows[0].phonemes == "aaa bb. "
    assert "".join(w.phonemes for w in windows) == full_stream(tokens)


def test_cut_falls_back_to_whitespace() -> None:
    tokens = [tok("aaa", True), tok("bbb", True), tok("ccc", True), tok("ddd")]
    windows = pack_phoneme_windows(tokens, 9)
    assert windows[0].phonemes == "aaa bbb "
    assert all(len(w.phonemes) <= 9 for w in windows)


def test_oversized_single_token_raises() -> None:
    with pytest.raises(PhonemeWindowError, match="single token"):
        pack_phoneme_windows([tok("x" * 11)], 10)


def test_run_without_break_point_raises() -> None:
    with pytest.raises(PhonemeWindowError, match="no break point"):
        pack_phoneme_windows([tok("aaaa"), tok("bbbb"), tok("cccc")], 10)


def test_unspoken_tokens_are_counted_per_window() -> None:
    tokens = [tok("aa", True), tok(None, True), tok("bb", True), tok(None, True), tok("cc")]
    windows = pack_phoneme_windows(tokens, 6)
    assert sum(w.unspoken_tokens for w in windows) == 2
    assert all(len(w.phonemes) <= 6 for w in windows)


def test_partition_is_lossless() -> None:
    rng = random.Random(1234)
    for _ in range(200):
        tokens = [
            PhonemeToken(
                phonemes=None if rng.random() < 0.1 else "x" * rng.randint(1, 6),
                whitespace=rng.random() < 0.7,
                is_punctuation=rng.random() < 0.15,
            )
            for _ in range(rng.randint(0, 80))
        ]
        limit = rng.randint(8, 40)
        try:
            windows = pack_phoneme_windows(tokens, limit)
        except PhonemeWindowError:
            continue  # an unbreakable run is a legal, loud failure; losslessness is for successes
        assert all(len(w.phonemes) <= limit for w in windows)
        assert "".join(w.phonemes for w in windows) == full_stream(tokens)
        assert sum(w.unspoken_tokens for w in windows) == sum(1 for t in tokens if t.phonemes is None)
