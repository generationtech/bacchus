"""Classify a tar segment as standalone vs GNU multi-volume slice (manifestless restore)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class TarSegmentKind(Enum):
    STANDALONE = "standalone"
    MV_START = "mv_start"
    MV_MIDDLE = "mv_middle"
    MV_END = "mv_end"


BLOCK = 512
ZERO_TRAILER = b"\x00" * (BLOCK * 2)


def _ends_with_zero_trailer(data: bytes) -> bool:
    return len(data) >= len(ZERO_TRAILER) and data.endswith(ZERO_TRAILER)


def classify_tar_segment(path: Path) -> TarSegmentKind:
    """
    Inspect decoded (uncompressed) tar bytes.

    - Complete POSIX/ustar archive ends with two 512-byte zero blocks.
    - GNU multi-volume continuation volumes start with typeflag 'M' (GNUTYPE_MULTIVOL)
      at byte index 156 of the first tar record.
    - First volume of a multi-volume split has a normal header and no zero trailer until the last slice.

    The last slice of an inner GNU ``tar -cM`` stream may still present as ``STANDALONE`` here while
    extraction requires earlier slices; chunked restore treats that when an MV buffer is already open.
    """
    size = path.stat().st_size
    if size < BLOCK:
        raise ValueError(f"tar segment too small: {path}")

    with open(path, "rb") as f:
        first = f.read(BLOCK)

    if len(first) != BLOCK:
        raise ValueError(f"short read: {path}")

    typeflag = first[156:157]

    data = path.read_bytes()
    ends = _ends_with_zero_trailer(data)

    if typeflag == b"M":
        if ends:
            return TarSegmentKind.MV_END
        return TarSegmentKind.MV_MIDDLE
    if ends:
        return TarSegmentKind.STANDALONE
    return TarSegmentKind.MV_START
