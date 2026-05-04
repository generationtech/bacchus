"""Detect legacy vs chunked archives from on-disk filenames."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

ArchiveMode = Literal["chunked", "legacy"]


def infer_archive_mode(source_dir: Path, basename: str) -> ArchiveMode:
    """Infer mode from ``source_dir`` contents; raise if ambiguous."""
    rx_chunk = re.compile(rf"^{re.escape(basename)}\.\d{{6}}\.tar(?:\.gz)?(?:\.gpg)?$")
    rx_legacy = re.compile(rf"^{re.escape(basename)}\.tar(?:-[0-9]+)?(?:\.gz)?(?:\.gpg)?$")

    chunked_hits = [p for p in source_dir.iterdir() if p.is_file() and rx_chunk.match(p.name)]
    legacy_hits = [p for p in source_dir.iterdir() if p.is_file() and rx_legacy.match(p.name)]

    if chunked_hits and legacy_hits:
        raise ValueError(
            f"Ambiguous archive layout in {source_dir}: both chunked ({basename}.NNNNNN.tar*) "
            f"and legacy ({basename}.tar*) files exist. Pass --archive-mode explicitly."
        )
    if chunked_hits:
        return "chunked"
    if legacy_hits:
        return "legacy"
    raise ValueError(f"No {basename}.* archives found in {source_dir}")
