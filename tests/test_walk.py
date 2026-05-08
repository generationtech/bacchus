from __future__ import annotations

from pathlib import Path

from bacchus.walk import (
    iter_files_from_ordered_paths,
    iter_files_with_sizes,
    iter_source_paths_tar_order,
)


def test_walk_order(tmp_path: Path) -> None:
    root = tmp_path / "src"
    (root / "b").mkdir(parents=True)
    (root / "a").mkdir(parents=True)
    (root / "a" / "z.txt").write_text("z")
    (root / "a" / "a.txt").write_text("a")
    (root / "b" / "m.txt").write_text("m")
    paths = iter_source_paths_tar_order(root)
    keys = [p.relative_to(tmp_path).as_posix() for p in paths]
    assert keys[0] == "src"
    assert keys[1:] == ["src/a", "src/a/a.txt", "src/a/z.txt", "src/b", "src/b/m.txt"]


def test_iter_files_from_ordered_paths_matches_iter_files_with_sizes(tmp_path: Path) -> None:
    root = tmp_path / "s"
    (root / "x").mkdir(parents=True)
    (root / "x" / "f").write_text("data")
    (root / "y").mkdir()
    ordered = iter_source_paths_tar_order(root)
    a = list(iter_files_from_ordered_paths(ordered))
    b = list(iter_files_with_sizes(root))
    assert a == b
    assert len(a) == 1
    assert a[0][0] == root / "x" / "f"
