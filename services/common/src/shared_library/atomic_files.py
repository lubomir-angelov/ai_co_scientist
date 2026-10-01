"""Atomic file replacement: the one sanctioned way to write a file that readers may observe.

Safe-by-construction (CLAUDE.md §6): callers never call ``os.replace`` / ``os.rename`` directly;
a unique temp file next to the target is fully written and fsynced, then renamed over the target,
so a reader sees either the old complete file or the new complete file, never a partial one.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _fsync_path(path: Path, flags: int) -> None:
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def atomic_replace(path: Path) -> Iterator[Path]:
    """Yield a unique temp path beside ``path``; on clean exit, publish it atomically as ``path``.

    On any exception the temp file is removed and the exception propagates; ``path`` is untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        _fsync_path(tmp, os.O_RDONLY)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_path(path.parent, os.O_RDONLY | os.O_DIRECTORY)
