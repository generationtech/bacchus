"""Shared restore helpers: locate chunk artifacts and prompt when media is missing."""

from __future__ import annotations

import re
from pathlib import Path

from bacchus.restore_sizing import chunk_member_name


def artifact_path(src_dir: Path, member: str, compress: bool, password: str) -> Path:
    p = src_dir / member
    if compress:
        p = Path(str(p) + ".gz")
    if password:
        p = Path(str(p) + ".gpg")
    return p


def prompt_new_source(expected: Path, current: Path) -> Path:
    print(f"\nArchive chunk: {expected.name}\nNOT FOUND in:   {current}\n")
    print("Place the file or enter a new source directory path (empty = retry):\n")
    np = input().strip()
    return Path(np) if np else current


def ensure_chunk_artifact(
    member: str,
    *,
    initial_src: Path,
    compress: bool,
    password: str,
) -> tuple[Path, Path]:
    """
    Return ``(src_dir, artifact_path)`` once ``artifact_path`` exists.

    Updates ``src_dir`` when the user enters a new directory at the prompt.
    """
    src_dir = initial_src
    while True:
        art = artifact_path(src_dir, member, compress, password)
        if art.is_file():
            return src_dir, art
        src_dir = prompt_new_source(art, src_dir)


def chunk_seq_from_member(member: str, basename: str) -> int:
    m = re.search(rf"^{re.escape(basename)}\.(\d{{6}})\.tar$", member)
    if not m:
        raise ValueError(f"Not a chunk member name: {member!r}")
    return int(m.group(1), 10)


def chunk_seq_from_chunk_path(path: Path, basename: str) -> int:
    return chunk_seq_from_member(chunk_member_name(path, basename), basename)
