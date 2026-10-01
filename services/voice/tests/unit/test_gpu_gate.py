import asyncio
import logging
import threading
import time

import pytest

from voice_service.services.gpu_gate import GpuGate

pytestmark = pytest.mark.anyio


async def test_cancelled_caller_keeps_the_gate_until_its_thread_finishes() -> None:
    gate = GpuGate()
    release = threading.Event()
    events: list[tuple[str, float]] = []

    def blocking() -> None:
        events.append(("first-start", time.monotonic()))
        release.wait(timeout=5)
        events.append(("first-end", time.monotonic()))

    def fast() -> None:
        events.append(("second-start", time.monotonic()))

    first = asyncio.ensure_future(gate.run(blocking))
    await asyncio.sleep(0.05)  # the worker thread is running
    first.cancel()
    second = asyncio.ensure_future(gate.run(fast))
    await asyncio.sleep(0.1)
    assert [name for name, _ in events] == ["first-start"], "second call started while the first thread was resident"
    assert not second.done()

    release.set()
    await second
    with pytest.raises(asyncio.CancelledError):
        await first
    assert [name for name, _ in events] == ["first-start", "first-end", "second-start"]
    assert events[1][1] <= events[2][1]


async def test_failure_after_cancellation_is_logged_not_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    gate = GpuGate()
    release = threading.Event()

    def failing() -> None:
        release.wait(timeout=5)
        raise RuntimeError("late gpu failure")

    task = asyncio.ensure_future(gate.run(failing))
    await asyncio.sleep(0.05)
    task.cancel()
    release.set()
    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await task
    record = next(r for r in caplog.records if "failed after its caller was cancelled" in r.message)
    assert record.exc_info is not None and str(record.exc_info[1]) == "late gpu failure"
