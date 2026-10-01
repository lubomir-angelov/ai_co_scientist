from __future__ import annotations

import threading
from pathlib import Path

import pytest
from shared_library.atomic_files import atomic_replace


def test_replace_publishes_the_new_content_and_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "doc.json"
    with atomic_replace(target) as tmp:
        assert tmp.parent == target.parent and tmp != target
        tmp.write_text("one", encoding="utf-8")
        assert not target.exists()
    assert target.read_text(encoding="utf-8") == "one"

    with atomic_replace(target) as tmp:
        tmp.write_text("two", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "two"
    assert list(target.parent.glob("*.tmp")) == []


def test_error_removes_the_tmp_keeps_the_old_file_and_reraises(tmp_path: Path) -> None:
    target = tmp_path / "doc.json"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError, match="boom"):
        with atomic_replace(target) as tmp:
            tmp.write_text("partial", encoding="utf-8")
            raise RuntimeError("boom")
    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_writers_use_distinct_tmp_names(tmp_path: Path) -> None:
    target = tmp_path / "doc.json"
    names: list[str] = []
    both_open = threading.Barrier(2, timeout=5)

    def write(content: str) -> None:
        with atomic_replace(target) as tmp:
            names.append(tmp.name)
            both_open.wait()
            tmp.write_text(content, encoding="utf-8")

    threads = [threading.Thread(target=write, args=(c,)) for c in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(names)) == 2
    assert target.read_text(encoding="utf-8") in {"a", "b"}
    assert list(tmp_path.glob("*.tmp")) == []
