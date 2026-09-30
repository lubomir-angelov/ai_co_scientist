from __future__ import annotations

import os
from pathlib import Path

import pytest

from paper_ingest.state import StateStore, WorkDirLockedError


def test_second_acquisition_while_held_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    with store.exclusive_lock():
        other = StateStore(tmp_path)
        with pytest.raises(WorkDirLockedError, match=str(tmp_path)), other.exclusive_lock():
            pass  # pragma: no cover - must never be entered


def test_lock_file_records_holder_pid(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    with store.exclusive_lock():
        assert store.lock_path().read_text(encoding="utf-8") == str(os.getpid())


def test_status_is_read_only_and_never_takes_the_lock(tmp_path: Path) -> None:
    """render_status (the `status` subcommand's implementation) never calls exclusive_lock,
    so it must be safely readable while a phase holds the lock — reproduced here by holding
    the lock ourselves and exercising the same read-only path `status` uses."""
    store = StateStore(tmp_path)
    with store.exclusive_lock():
        reader = StateStore(tmp_path)
        assert reader.known_paper_ids() == []  # does not raise WorkDirLockedError


def test_lock_released_after_phase_returns(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    with store.exclusive_lock():
        pass

    # A second acquisition now succeeds because the first was released on exit.
    other = StateStore(tmp_path)
    with other.exclusive_lock():
        pass


def test_lock_released_even_when_the_wrapped_block_raises(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    with pytest.raises(ValueError, match="boom"), store.exclusive_lock():
        raise ValueError("boom")

    other = StateStore(tmp_path)
    with other.exclusive_lock():
        pass
