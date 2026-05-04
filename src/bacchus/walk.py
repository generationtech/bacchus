"""Deterministic walk order aligned with GNU tar --sort=name archive member names."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterator, List, Tuple


def iter_source_paths_tar_order(source: Path) -> List[Path]:
    """
    Return paths under source (including source dir itself and empty dirs),
    sorted the same way GNU tar --sort=name orders member names when archiving `source`.

    Member names in the archive are path.relative_to(source.parent) as POSIX strings
    (e.g. ``mydir/file`` when source is ``.../mydir``).
    """
    root = source.resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    parent = root.parent

    paths: List[Path] = []
    if root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames.sort()
            filenames.sort()
            dp = Path(dirpath)
            paths.append(dp)
            for fn in filenames:
                paths.append(dp / fn)
    else:
        paths.append(root)

    def sort_key(p: Path) -> str:
        try:
            rel = p.resolve().relative_to(parent)
        except ValueError:
            rel = p.resolve()
        return rel.as_posix()

    paths.sort(key=sort_key)
    return paths


def iter_files_with_sizes(source: Path) -> Iterator[Tuple[Path, int]]:
    """Yield (path, logical size in bytes) for regular files and symlinks only (chunk sizing)."""
    for p in iter_source_paths_tar_order(source):
        try:
            st = p.lstat()
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
            yield p, st.st_size
