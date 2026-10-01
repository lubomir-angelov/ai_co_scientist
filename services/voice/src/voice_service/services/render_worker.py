"""RenderQueue: bounded queue, one worker, idempotent resume.

In-memory jobs are lost on process exit, which is the honest state: the manifest shows what was
rendered and re-submitting the same request resumes. Nothing auto-resumes at boot.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from voice_service.core.errors import RenderQueueFullError
from voice_service.models.schemas import (
    ModelIdentity,
    PaperScript,
    RenderManifest,
    SectionRenderRecord,
)
from voice_service.services import render_store as store_layout
from voice_service.services.audio_encode import Mp3FileWriter
from voice_service.services.backends import TtsBackend
from voice_service.services.gpu_gate import GpuGate
from voice_service.services.model_registry import ModelRegistry
from voice_service.services.render_store import RenderStore, file_digest
from voice_service.services.script_builder import speakable_section
from voice_service.services.synthesis import SynthesisStats, synthesize_units, units_for_section

logger = logging.getLogger(__name__)


@dataclass
class RenderJob:
    script: PaperScript
    render_key: str
    requested: list[int]
    pending: deque[int]
    current_index: int | None = None

    @property
    def doc_id(self) -> str:
        return self.script.doc_id


class RenderQueue:
    def __init__(
        self,
        *,
        store: RenderStore,
        registry: ModelRegistry,
        gate: GpuGate,
        queue_max: int,
        tts_model: ModelIdentity,
        voice: str,
        speed: float,
        exit_process: Callable[[int], NoReturn],
    ) -> None:
        self._store = store
        self._registry = registry
        self._gate = gate
        self._tts_model = tts_model
        self._voice = voice
        self._speed = speed
        self._exit_process = exit_process
        self._queue: asyncio.Queue[RenderJob] = asyncio.Queue(maxsize=queue_max)
        self._waiting: list[RenderJob] = []
        self._active: dict[tuple[str, str], RenderJob] = {}
        self._task: asyncio.Task[None] | None = None

    # ---- lifecycle ------------------------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="render-worker")
        self._task.add_done_callback(self._on_worker_done)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)

    def _on_worker_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        logger.error("render worker died", exc_info=task.exception())
        self._exit_process(1)

    # ---- submission -----------------------------------------------------------------------

    def render_key_for(self, script: PaperScript) -> str:
        return store_layout.render_key(
            script.script_sha256,
            self._tts_model,
            self._voice,
            self._speed,
            self._registry.require_tts().sample_rate,
        )

    def find_active(self, doc_id: str, key: str) -> RenderJob | None:
        return self._active.get((doc_id, key))

    def queued_position(self, job: RenderJob) -> int | None:
        return self._waiting.index(job) if job in self._waiting else None

    async def submit(self, doc_id: str, indices: list[int]) -> RenderJob:
        script = self._store.load_script(doc_id)
        for index in indices:
            speakable_section(script, index)

        key = self.render_key_for(script)
        manifest = self._store.find_manifest(doc_id, key)
        if manifest is not None:
            for index in indices:
                record = manifest.sections.get(index)
                if record is not None and record.status == "rendered":
                    await asyncio.to_thread(self._store.verify_rendered, doc_id, key, record)

        # No await below: the active-check and the enqueue are one atomic step on the loop.
        active = self._active.get((doc_id, key))
        if active is not None:
            for index in indices:
                if index not in active.requested:
                    active.requested.append(index)
                    active.pending.append(index)
            return active

        job = RenderJob(script=script, render_key=key, requested=list(indices), pending=deque(indices))
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            raise RenderQueueFullError("render queue is full; retry later") from None
        self._waiting.append(job)
        self._active[(doc_id, key)] = job
        return job

    # ---- worker ---------------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            self._waiting.remove(job)
            try:
                await self._process(job)
            finally:
                job.current_index = None
                self._active.pop((job.doc_id, job.render_key), None)
                self._queue.task_done()

    async def _process(self, job: RenderJob) -> None:
        backend = self._registry.require_tts()
        manifest = self._store.find_manifest(job.doc_id, job.render_key)
        if manifest is None:
            manifest = RenderManifest(
                doc_id=job.doc_id,
                render_key=job.render_key,
                script_sha256=job.script.script_sha256,
                voice=self._voice,
                speed=self._speed,
                tts_model=self._tts_model,
                sections={},
            )
        while job.pending:
            index = job.pending.popleft()
            job.current_index = index
            existing = manifest.sections.get(index)
            if existing is not None and existing.status == "rendered":
                continue
            try:
                record = await self._render_section(job, backend, index)
            except Exception as exc:
                logger.exception(
                    "section render failed",
                    extra={"doc_id": job.doc_id, "render_key": job.render_key, "section": index},
                )
                record = SectionRenderRecord(
                    index=index,
                    status="failed",
                    file_name=None,
                    sha256=None,
                    bytes=None,
                    audio_seconds=None,
                    windows=None,
                    unspoken_tokens=None,
                    synth_seconds=None,
                    phonemize_seconds=None,
                    error=f"{type(exc).__name__}: {exc}",
                    finished_at=datetime.now(UTC),
                )
                manifest.sections[index] = record
                self._store.save_manifest(manifest)
                return  # fail fast: later sections would likely fail identically; they stay unattempted
            manifest.sections[index] = record
            self._store.save_manifest(manifest)

    async def _render_section(self, job: RenderJob, backend: TtsBackend, index: int) -> SectionRenderRecord:
        section = job.script.sections[index]
        stats = SynthesisStats(sample_rate=backend.sample_rate)
        units = units_for_section(section)
        with self._store.section_output(job.doc_id, job.render_key, index) as tmp:
            writer = await asyncio.to_thread(Mp3FileWriter, tmp, backend.sample_rate)
            try:
                async for pcm in synthesize_units(backend, self._gate, units, stats):
                    await asyncio.to_thread(writer.write, pcm)
            finally:
                await asyncio.to_thread(writer.close)
            sha256, size = await asyncio.to_thread(file_digest, tmp)
        logger.info(
            "section rendered",
            extra={
                "doc_id": job.doc_id,
                "render_key": job.render_key,
                "section": index,
                "windows": stats.windows,
                "unspoken_tokens": stats.unspoken_tokens,
                "audio_seconds": round(stats.audio_seconds, 2),
                "synth_seconds": round(stats.synth_seconds, 2),
                "phonemize_seconds": round(stats.phonemize_seconds, 2),
                "realtime_factor": round(stats.audio_seconds / stats.synth_seconds, 1),
            },
        )
        return SectionRenderRecord(
            index=index,
            status="rendered",
            file_name=store_layout.section_file_name(index),
            sha256=sha256,
            bytes=size,
            audio_seconds=stats.audio_seconds,
            windows=stats.windows,
            unspoken_tokens=stats.unspoken_tokens,
            synth_seconds=stats.synth_seconds,
            phonemize_seconds=stats.phonemize_seconds,
            error=None,
            finished_at=datetime.now(UTC),
        )
