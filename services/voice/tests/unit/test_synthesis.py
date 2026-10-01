import asyncio
import time

import numpy as np
import pytest
from conftest import FAKE_SAMPLE_RATE, SAMPLES_PER_PHONEME, FakeTts

from voice_service.core.errors import NothingToSpeakError
from voice_service.models.schemas import OmittedBlock, ScriptSection, ScriptSegment
from voice_service.services.gpu_gate import GpuGate
from voice_service.services.synthesis import (
    HEADING_PAUSE_SECONDS,
    OMITTED_BLOCK_PAUSE_SECONDS,
    SEGMENT_PAUSE_SECONDS,
    SpeechUnit,
    SynthesisStats,
    synthesize_units,
    units_for_section,
)

pytestmark = pytest.mark.anyio


async def collect_pcm(tts: FakeTts, gate: GpuGate, units: list[SpeechUnit], stats: SynthesisStats) -> np.ndarray:
    return np.concatenate([chunk async for chunk in synthesize_units(tts, gate, units, stats)])


async def test_pauses_have_exact_sample_counts_and_stats_are_correct() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    units = [SpeechUnit("ab", HEADING_PAUSE_SECONDS), SpeechUnit("cde", SEGMENT_PAUSE_SECONDS)]

    pcm = await collect_pcm(tts, gate, units, stats)

    pause = round(HEADING_PAUSE_SECONDS * FAKE_SAMPLE_RATE)
    expected = 2 * SAMPLES_PER_PHONEME + pause + 3 * SAMPLES_PER_PHONEME
    assert len(pcm) == expected and stats.samples == expected
    assert stats.windows == 2 and stats.unspoken_tokens == 0
    assert np.all(pcm[2 * SAMPLES_PER_PHONEME : 2 * SAMPLES_PER_PHONEME + pause] == 0)
    assert stats.synth_seconds > 0 and stats.phonemize_seconds > 0
    assert stats.audio_seconds == expected / FAKE_SAMPLE_RATE


async def test_every_backend_call_runs_under_the_gate() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)  # asserts the gate is held and off-loop inside phonemize/synthesize
    await collect_pcm(tts, gate, [SpeechUnit("hello", 0.0)], SynthesisStats(sample_rate=FAKE_SAMPLE_RATE))
    assert tts.phonemize_calls == ["hello"] and tts.synthesize_calls == ["hello"]
    assert not gate._semaphore.locked()


async def test_long_text_is_split_into_windows_without_loss() -> None:
    gate = GpuGate()
    tts = FakeTts(max_phonemes=10, gate=gate)
    text = "aaaa bbbb cccc dddd eeee"
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    await collect_pcm(tts, gate, [SpeechUnit(text, 0.0)], stats)
    assert stats.windows == len(tts.synthesize_calls) > 1
    assert "".join(tts.synthesize_calls).replace(" ", "") == text.replace(" ", "")
    assert all(len(w) <= 10 for w in tts.synthesize_calls)


async def test_unspoken_tokens_counted_and_blank_windows_skipped() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    await collect_pcm(tts, gate, [SpeechUnit("a~b", 0.0), SpeechUnit("~~", 0.0)], stats)
    assert stats.unspoken_tokens == 3
    assert tts.synthesize_calls == ["ab"]  # the all-unspoken unit is not synthesized


async def test_silence_only_unit_yields_pause_without_synthesis() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    units = [SpeechUnit("a", 0.0), SpeechUnit("", OMITTED_BLOCK_PAUSE_SECONDS), SpeechUnit("b", 0.0)]
    pcm = await collect_pcm(tts, gate, units, stats)
    assert stats.windows == 2
    assert len(pcm) == 2 * SAMPLES_PER_PHONEME + round(OMITTED_BLOCK_PAUSE_SECONDS * FAKE_SAMPLE_RATE)


async def test_first_chunk_is_available_before_the_rest() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    chunks = synthesize_units(
        tts, gate, [SpeechUnit("a", 0.1), SpeechUnit("b", 0.0)], SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    )
    first = await anext(chunks)
    assert len(first) == SAMPLES_PER_PHONEME and tts.synthesize_calls == ["a"]
    await chunks.aclose()


def test_units_interleave_segments_and_omissions_in_source_order() -> None:
    section = ScriptSection(
        index=0,
        heading="H",
        page_start=1,
        page_end=1,
        speakable=True,
        segments=[
            ScriptSegment(kind="heading", page_number=1, block_index=0, text="H"),
            ScriptSegment(kind="body", page_number=1, block_index=2, text="body"),
        ],
        omitted=[OmittedBlock(page_number=1, block_index=1, ref="table")],
        math_spans_converted=0,
        spoken_char_count=5,
    )
    assert units_for_section(section) == [
        SpeechUnit("H", HEADING_PAUSE_SECONDS),
        SpeechUnit("", OMITTED_BLOCK_PAUSE_SECONDS),
        SpeechUnit("body", SEGMENT_PAUSE_SECONDS),
    ]


async def test_first_chunk_is_a_synthesized_window_and_leading_silence_is_absent() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    units = [SpeechUnit("", OMITTED_BLOCK_PAUSE_SECONDS), SpeechUnit("ab", 0.0), SpeechUnit("c", 0.0)]
    chunks = [c async for c in synthesize_units(tts, gate, units, stats)]
    expected = await asyncio.to_thread(FakeTts().synthesize, "ab")  # ungated twin, off-loop
    assert np.array_equal(chunks[0], expected)
    assert len(chunks[0]) == 2 * SAMPLES_PER_PHONEME
    # the omitted block's pause is leading (dropped); "ab" -> "c" has a zero pause between them
    assert len(chunks) == 2 and stats.samples == 3 * SAMPLES_PER_PHONEME


async def test_pause_between_windows_includes_an_omitted_blocks_pause() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    units = [SpeechUnit("a", 0.25), SpeechUnit("", OMITTED_BLOCK_PAUSE_SECONDS), SpeechUnit("b", 0.0)]
    chunks = [c async for c in synthesize_units(tts, gate, units, stats)]
    assert [len(c) for c in chunks] == [
        SAMPLES_PER_PHONEME,
        round((0.25 + OMITTED_BLOCK_PAUSE_SECONDS) * FAKE_SAMPLE_RATE),
        SAMPLES_PER_PHONEME,
    ]


async def test_nothing_speakable_raises() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    with pytest.raises(NothingToSpeakError):
        await collect_pcm(tts, gate, [SpeechUnit("~~~", 0.5), SpeechUnit("", 1.0)], stats)
    assert stats.windows == 0 and stats.unspoken_tokens == 3


async def test_phonemize_and_synthesize_seconds_are_tracked_separately() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    stats = SynthesisStats(sample_rate=FAKE_SAMPLE_RATE)
    original = tts.synthesize

    def slow_synthesize(phonemes: str) -> np.ndarray:
        time.sleep(0.05)
        return original(phonemes)

    tts.synthesize = slow_synthesize  # type: ignore[method-assign]
    await collect_pcm(tts, gate, [SpeechUnit("ab", 0.0)], stats)
    assert stats.synth_seconds >= 0.05
    assert 0 < stats.phonemize_seconds < 0.05


async def test_mismatched_stats_sample_rate_raises() -> None:
    gate = GpuGate()
    tts = FakeTts(gate=gate)
    with pytest.raises(ValueError, match="sample_rate"):
        await anext(synthesize_units(tts, gate, [SpeechUnit("a", 0.0)], SynthesisStats(sample_rate=16000)))
