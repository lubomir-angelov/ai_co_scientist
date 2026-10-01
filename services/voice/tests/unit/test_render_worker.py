import asyncio
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
import soundfile as sf
from conftest import ExitRecorder, FakeStt, FakeTts, load_ocr_fixture, make_manifest

from voice_service.core.errors import (
    RenderQueueFullError,
    ScriptNotPreparedError,
    SectionNotFoundError,
    SectionNotSpeakableError,
    StoreIntegrityError,
)
from voice_service.services.gpu_gate import GpuGate
from voice_service.services.model_registry import ModelRegistry
from voice_service.services.render_store import RenderStore
from voice_service.services.render_worker import RenderQueue
from voice_service.services.script_builder import build_script

pytestmark = pytest.mark.anyio

DOC = "paper-1"


class Harness:
    def __init__(self, tmp_path: Path, exit_recorder: ExitRecorder, queue_max: int = 4) -> None:
        manifest = make_manifest(tmp_path)
        self.gate = GpuGate()
        self.tts = FakeTts(gate=self.gate)
        self.store = RenderStore(tmp_path / "data")
        self.exit_recorder = exit_recorder
        self.registry = ModelRegistry(manifest, lambda: self.tts, FakeStt, exit_recorder)
        self.queue = RenderQueue(
            store=self.store, registry=self.registry, gate=self.gate, queue_max=queue_max,
            tts_model=manifest.tts.identity(), voice="af_heart", speed=1.0, exit_process=exit_recorder,
        )
        self.store.save_script(build_script(load_ocr_fixture(), datetime.now(UTC)))

    async def start(self) -> None:
        await self.registry.load_all()
        self.queue.start()

    async def wait_idle(self, key: str) -> None:
        for _ in range(500):
            if self.queue.find_active(DOC, key) is None:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("render job did not finish")


@pytest.fixture
async def harness(tmp_path: Path, exit_recorder: ExitRecorder):
    h = Harness(tmp_path, exit_recorder)
    await h.start()
    yield h
    await h.queue.stop()


async def test_submit_renders_files_and_manifest(harness: Harness) -> None:
    job = await harness.queue.submit(DOC, [1, 2])
    await harness.wait_idle(job.render_key)

    manifest = harness.store.find_manifest(DOC, job.render_key)
    assert manifest is not None and sorted(manifest.sections) == [1, 2]
    for index, record in manifest.sections.items():
        assert record.status == "rendered" and record.windows and record.windows > 0
        assert harness.store.verify_rendered(DOC, job.render_key, record).is_file()
    assert manifest.sections[1].audio_seconds is not None and manifest.sections[1].audio_seconds > 0
    assert harness.exit_recorder.codes == []


async def test_resubmit_skips_rendered_sections(harness: Harness) -> None:
    job = await harness.queue.submit(DOC, [1])
    await harness.wait_idle(job.render_key)
    calls = len(harness.tts.synthesize_calls)

    again = await harness.queue.submit(DOC, [1])
    await harness.wait_idle(again.render_key)

    assert again.render_key == job.render_key
    assert len(harness.tts.synthesize_calls) == calls


async def test_failed_section_stops_the_job_and_resubmit_retries_it(harness: Harness) -> None:
    harness.tts.fail_on = lambda ph: "Methods" in ph or ph.startswith("Methods")
    job = await harness.queue.submit(DOC, [2, 4])
    await harness.wait_idle(job.render_key)

    manifest = harness.store.find_manifest(DOC, job.render_key)
    assert manifest is not None and list(manifest.sections) == [2]
    failed = manifest.sections[2]
    assert failed.status == "failed" and failed.error is not None and "synthetic synthesis failure" in failed.error
    assert failed.file_name is None and 4 not in manifest.sections  # later section never attempted

    harness.tts.fail_on = None
    retry = await harness.queue.submit(DOC, [2, 4])
    await harness.wait_idle(retry.render_key)
    manifest = harness.store.find_manifest(DOC, job.render_key)
    assert manifest is not None
    assert {i: r.status for i, r in manifest.sections.items()} == {2: "rendered", 4: "rendered"}
    assert harness.exit_recorder.codes == []


async def test_active_key_merges_new_indices(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    h = Harness(tmp_path, exit_recorder)
    await h.registry.load_all()  # worker NOT started: the job stays queued
    first = await h.queue.submit(DOC, [1])
    second = await h.queue.submit(DOC, [1, 2])
    assert second is first and first.requested == [1, 2] and list(first.pending) == [1, 2]
    assert h.queue.queued_position(first) == 0
    h.queue.start()
    await h.wait_idle(first.render_key)
    manifest = h.store.find_manifest(DOC, first.render_key)
    assert manifest is not None and sorted(manifest.sections) == [1, 2]
    assert h.queue.queued_position(first) is None
    await h.queue.stop()


async def test_full_queue_raises(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    h = Harness(tmp_path, exit_recorder, queue_max=1)
    await h.registry.load_all()
    h.store.save_script(
        build_script(load_ocr_fixture().model_copy(update={"doc_id": "paper-2"}), datetime.now(UTC))
    )
    await h.queue.submit(DOC, [1])
    with pytest.raises(RenderQueueFullError):
        await h.queue.submit("paper-2", [1])


async def test_validation_errors(harness: Harness) -> None:
    with pytest.raises(ScriptNotPreparedError):
        await harness.queue.submit("absent", [0])
    with pytest.raises(SectionNotFoundError):
        await harness.queue.submit(DOC, [99])
    with pytest.raises(SectionNotSpeakableError):
        await harness.queue.submit(DOC, [3])


async def test_missing_file_behind_rendered_record_raises_integrity(harness: Harness) -> None:
    job = await harness.queue.submit(DOC, [1])
    await harness.wait_idle(job.render_key)
    harness.store.section_path(DOC, job.render_key, 1).unlink()
    with pytest.raises(StoreIntegrityError, match="missing"):
        await harness.queue.submit(DOC, [1])


async def test_worker_death_exits_the_process(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    h = Harness(tmp_path, exit_recorder)
    await h.registry.load_all()
    await h.queue.submit(DOC, [1])
    # A manifest write failure is outside section scope: the worker must die loudly.
    h.store.save_manifest = lambda manifest: (_ for _ in ()).throw(OSError("disk gone"))  # type: ignore[method-assign]
    h.queue.start()
    for _ in range(200):
        if exit_recorder.codes:
            break
        await asyncio.sleep(0.01)
    assert exit_recorder.codes == [1]


async def test_rendered_file_decodes_to_the_recorded_duration(harness: Harness) -> None:
    job = await harness.queue.submit(DOC, [2])
    await harness.wait_idle(job.render_key)
    manifest = harness.store.find_manifest(DOC, job.render_key)
    assert manifest is not None
    record = manifest.sections[2]
    assert record.audio_seconds is not None
    path = harness.store.verify_rendered(DOC, job.render_key, record)
    decoded, rate = sf.read(io.BytesIO(path.read_bytes()))
    assert abs(len(decoded) / rate - record.audio_seconds) <= 0.1
    assert record.phonemize_seconds is not None and record.phonemize_seconds > 0
    assert record.bytes == path.stat().st_size


async def test_failed_render_leaves_no_tmp_and_no_section_file(harness: Harness, tmp_path: Path) -> None:
    harness.tts.fail_on = lambda ph: True
    job = await harness.queue.submit(DOC, [2])
    await harness.wait_idle(job.render_key)
    assert list((tmp_path / "data").rglob("*.tmp")) == []
    assert list((tmp_path / "data").rglob("*.mp3")) == []


async def test_unpronounceable_section_is_a_failed_record_naming_the_error(harness: Harness) -> None:
    script = harness.store.load_script(DOC)
    for segment in script.sections[2].segments:
        segment.text = "~~~"
    harness.store.save_script(script)
    job = await harness.queue.submit(DOC, [2])
    await harness.wait_idle(job.render_key)
    manifest = harness.store.find_manifest(DOC, job.render_key)
    assert manifest is not None
    failed = manifest.sections[2]
    assert failed.status == "failed" and failed.error is not None and "NothingToSpeakError" in failed.error
    assert list(harness.store.section_path(DOC, job.render_key, 2).parent.glob("*")) == [
        harness.store.section_path(DOC, job.render_key, 2).parent / "manifest.json"
    ]
