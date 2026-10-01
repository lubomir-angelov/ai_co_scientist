from pathlib import Path

import pytest
from conftest import ExitRecorder, FakeStt, FakeTts, make_manifest

from voice_service.core.errors import ModelsLoadingError
from voice_service.services.model_registry import ModelRegistry

pytestmark = pytest.mark.anyio


async def test_loads_both_and_reports_ready(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    registry = ModelRegistry(make_manifest(tmp_path), FakeTts, FakeStt, exit_recorder)
    assert not registry.tts_loaded and not registry.stt_loaded
    with pytest.raises(ModelsLoadingError):
        registry.require_tts()
    with pytest.raises(ModelsLoadingError):
        registry.require_stt()

    await registry.load_all()

    assert registry.tts_loaded and registry.stt_loaded
    assert isinstance(registry.require_tts(), FakeTts) and isinstance(registry.require_stt(), FakeStt)
    assert exit_recorder.codes == []


async def test_load_failure_exits_the_process(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    def broken() -> FakeTts:
        raise RuntimeError("CUDA requested but unavailable")

    registry = ModelRegistry(make_manifest(tmp_path), broken, FakeStt, exit_recorder)
    await registry.load_all()
    assert exit_recorder.codes == [1]
    assert not registry.tts_loaded and not registry.stt_loaded
