"""Text units -> PCM, one GPU-gated window at a time."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

from voice_service.core.errors import NothingToSpeakError
from voice_service.models.schemas import ScriptSection
from voice_service.services.backends import TtsBackend
from voice_service.services.gpu_gate import GpuGate
from voice_service.services.phoneme_windows import pack_phoneme_windows

SEGMENT_PAUSE_SECONDS = 0.5
HEADING_PAUSE_SECONDS = 0.9
# Language-neutral audible cue for an omitted table/figure/equation (a spoken label would be
# hardcoded natural language).
OMITTED_BLOCK_PAUSE_SECONDS = 1.0


@dataclass(frozen=True)
class SpeechUnit:
    text: str  # "" = silence only (an omitted block)
    pause_after_seconds: float


@dataclass
class SynthesisStats:
    sample_rate: int  # the backend's rate: the only basis of audio_seconds
    windows: int = 0
    unspoken_tokens: int = 0
    samples: int = 0
    synth_seconds: float = 0.0  # backend.synthesize time only
    phonemize_seconds: float = 0.0  # backend.phonemize time only

    @property
    def audio_seconds(self) -> float:
        return self.samples / self.sample_rate


def units_for_section(section: ScriptSection) -> list[SpeechUnit]:
    """Segments and omission gaps interleaved in source order (page, block index)."""
    ordered: list[tuple[int, int, SpeechUnit]] = []
    for seg in section.segments:
        pause = HEADING_PAUSE_SECONDS if seg.kind == "heading" else SEGMENT_PAUSE_SECONDS
        ordered.append((seg.page_number, seg.block_index, SpeechUnit(seg.text, pause)))
    for omitted in section.omitted:
        ordered.append((omitted.page_number, omitted.block_index, SpeechUnit("", OMITTED_BLOCK_PAUSE_SECONDS)))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [unit for _, _, unit in ordered]


_Arg = TypeVar("_Arg")
_Result = TypeVar("_Result")


def _timed(fn: Callable[[_Arg], _Result], arg: _Arg) -> tuple[_Result, float]:
    """Runs inside the gate's worker thread, so the elapsed time excludes gate-wait time."""
    started = time.perf_counter()
    result = fn(arg)
    return result, time.perf_counter() - started


def _silence(seconds: float, sample_rate: int) -> np.ndarray:
    return np.zeros(round(seconds * sample_rate), dtype=np.float32)


async def synthesize_units(
    backend: TtsBackend, gate: GpuGate, units: Sequence[SpeechUnit], stats: SynthesisStats
) -> AsyncIterator[np.ndarray]:
    """Yield PCM chunks (speech windows and pauses) for ``units``, updating ``stats``.

    The first yielded chunk is always a backend-synthesized window: pauses accumulate and are
    emitted only between speech windows, so leading silence is never produced (it would be
    inaudible, just as the trailing pause after the last unit is never emitted). Windows inside
    one unit are back-to-back. Every backend call goes through ``gate``. Tokens the G2P could not
    pronounce are counted in ``stats.unspoken_tokens`` (the explicit, contracted degraded path),
    never faked. Raises ``NothingToSpeakError`` when no window could be synthesized.
    """
    if stats.sample_rate != backend.sample_rate:
        raise ValueError(
            f"stats.sample_rate {stats.sample_rate} does not match backend.sample_rate {backend.sample_rate}"
        )
    pending_pause = 0.0
    for unit in units:
        if unit.text:
            tokens, phonemize_seconds = await gate.run(_timed, backend.phonemize, unit.text)
            stats.phonemize_seconds += phonemize_seconds
            for window in pack_phoneme_windows(tokens, backend.max_phonemes):
                stats.unspoken_tokens += window.unspoken_tokens
                if not window.phonemes.strip():
                    continue
                if stats.windows > 0 and pending_pause > 0:
                    silence = _silence(pending_pause, backend.sample_rate)
                    stats.samples += len(silence)
                    yield silence
                pending_pause = 0.0
                pcm, elapsed = await gate.run(_timed, backend.synthesize, window.phonemes)
                stats.windows += 1
                stats.synth_seconds += elapsed
                stats.samples += len(pcm)
                yield pcm
        pending_pause += unit.pause_after_seconds
    if stats.windows == 0:
        raise NothingToSpeakError("the text produced no speakable audio")
