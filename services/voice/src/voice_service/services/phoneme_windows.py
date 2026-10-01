"""The named Kokoro windowing helper (CLAUDE.md §7 ALLOWED form).

Kokoro-82M accepts at most KOKORO_MAX_PHONEMES phonemes per inference. The full token stream is
PARTITIONED into windows under that bound: nothing is dropped, so the full text is spoken.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from voice_service.core.errors import PhonemeWindowError
from voice_service.services.backends import PhonemeToken

# Kokoro-82M context: 512 positions minus BOS/EOS. A REAL model bound, not a clip.
KOKORO_MAX_PHONEMES = 510


@dataclass(frozen=True)
class PhonemeWindow:
    phonemes: str
    unspoken_tokens: int  # tokens with phonemes=None in this window (G2P could not pronounce)


def _piece(token: PhonemeToken) -> str:
    return ("" if token.phonemes is None else token.phonemes) + (" " if token.whitespace else "")


def _cut_after(window: list[PhonemeToken]) -> int:
    """Number of leading tokens to emit: after the last punctuation token, else the last
    whitespace-followed token. Raises when the window has no break point."""
    for wanted in (lambda t: t.is_punctuation, lambda t: t.whitespace):
        for position in range(len(window) - 1, -1, -1):
            if wanted(window[position]):
                return position + 1
    raise PhonemeWindowError(
        f"no break point inside a {len(window)}-token run that exceeds the phoneme window"
    )


def _seal(tokens: list[PhonemeToken]) -> PhonemeWindow:
    return PhonemeWindow(
        phonemes="".join(_piece(t) for t in tokens),
        unspoken_tokens=sum(1 for t in tokens if t.phonemes is None),
    )


def pack_phoneme_windows(tokens: Sequence[PhonemeToken], limit: int) -> list[PhonemeWindow]:
    """Partition the FULL token stream into consecutive windows of at most ``limit`` phonemes.

    Greedy: extend while it fits; when the next token would overflow, cut after the last
    punctuation token in the window, else after the last whitespace-followed token, else raise
    PhonemeWindowError. A single token longer than ``limit`` raises (never clipped).
    Invariant (asserted before return): the windows concatenate to the full stream, and the
    unspoken counts sum to the number of tokens without phonemes.
    """
    windows: list[PhonemeWindow] = []
    current: list[PhonemeToken] = []
    current_len = 0

    for token in tokens:
        piece_len = len(_piece(token))
        if piece_len > limit:
            raise PhonemeWindowError(f"a single token needs {piece_len} phonemes, window limit is {limit}")
        while current_len + piece_len > limit:
            cut = _cut_after(current)
            windows.append(_seal(current[:cut]))
            current = current[cut:]
            current_len = sum(len(_piece(t)) for t in current)
        current.append(token)
        current_len += piece_len
    if current:
        windows.append(_seal(current))

    if "".join(w.phonemes for w in windows) != "".join(_piece(t) for t in tokens):
        raise PhonemeWindowError("window partition lost or reordered phonemes")
    if sum(w.unspoken_tokens for w in windows) != sum(1 for t in tokens if t.phonemes is None):
        raise PhonemeWindowError("window partition miscounted unspoken tokens")
    return windows
