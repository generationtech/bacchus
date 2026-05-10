"""Shared restore helpers: locate chunk artifacts and prompt when media is missing."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path

from bacchus.restore_sizing import chunk_member_name


class RestoreNoMoreChunks(Exception):
    """User signaled that no further archive chunks exist (typed ``end`` / ``done`` at prompt)."""

    def __init__(self, member: str) -> None:
        super().__init__(member)
        self.member = member


def find_chunk_artifact(
    member: str, roots: list[Path], compress: bool, password: str
) -> tuple[Path, Path] | None:
    """Return ``(root_dir, artifact_path)`` if the chunk exists under any ``roots`` entry."""
    for root in roots:
        r = root.resolve()
        art = artifact_path(r, member, compress, password)
        if art.is_file():
            return r, art
    return None


def artifact_path(src_dir: Path, member: str, compress: bool, password: str) -> Path:
    p = src_dir / member
    if compress:
        p = Path(str(p) + ".gz")
    if password:
        p = Path(str(p) + ".gpg")
    return p


def max_chunk_seq_on_disk(root: Path, basename: str) -> int:
    """Largest ``NNNNNN`` chunk index present under ``root`` (0 if none)."""
    rx = re.compile(rf"^{re.escape(basename)}\.(\d{{6}})\.tar(?:\.gz)?(?:\.gpg)?$")
    best = 0
    try:
        for p in root.iterdir():
            if not p.is_file():
                continue
            m = rx.match(p.name)
            if m:
                best = max(best, int(m.group(1), 10))
    except OSError:
        return best
    return best


def max_chunk_seq_across_roots(roots: list[Path], basename: str) -> int:
    return max((max_chunk_seq_on_disk(r, basename) for r in roots), default=0)


def prompt_new_source(expected: Path, current_roots: list[Path]) -> Path | None:
    loc = current_roots[0] if current_roots else Path(".")
    print(f"\nArchive chunk: {expected.name}\nNOT FOUND under: {loc}")
    if len(current_roots) > 1:
        print(f"(also tried {len(current_roots) - 1} other director{'ies' if len(current_roots) > 2 else 'y'})")
    print(
        "Place the file or enter a new source directory path "
        "(empty = retry, type end when no more chunks remain):\n"
    )
    np = input().strip()
    if np.lower() in ("end", "done"):
        return None
    return Path(np) if np else loc


def ensure_chunk_artifact(
    member: str,
    *,
    search_roots: list[Path],
    compress: bool,
    password: str,
    record_prompt_idle: Callable[[int], None] | None = None,
) -> tuple[Path, Path]:
    """
    Return ``(src_dir, artifact_path)`` once ``artifact_path`` exists.

    Tries each directory in ``search_roots`` (extended when the user supplies a new path).
    """
    if not search_roots:
        raise ValueError("search_roots must not be empty")

    resolved_set = {r.resolve() for r in search_roots}

    while True:
        hit = find_chunk_artifact(member, search_roots, compress, password)
        if hit:
            return hit

        t0 = time.time()
        expected = artifact_path(search_roots[0], member, compress, password)
        np = prompt_new_source(expected, search_roots)
        idle = int(time.time()) - t0
        if record_prompt_idle and idle > 0:
            record_prompt_idle(idle)
        if np is None:
            raise RestoreNoMoreChunks(member)
        if np != search_roots[0]:
            cand = np.expanduser().resolve()
            if cand.is_dir() and cand not in resolved_set:
                search_roots.append(cand)
                resolved_set.add(cand)


def chunk_seq_from_member(member: str, basename: str) -> int:
    m = re.search(rf"^{re.escape(basename)}\.(\d{{6}})\.tar$", member)
    if not m:
        raise ValueError(f"Not a chunk member name: {member!r}")
    return int(m.group(1), 10)


def chunk_seq_from_chunk_path(path: Path, basename: str) -> int:
    return chunk_seq_from_member(chunk_member_name(path, basename), basename)
