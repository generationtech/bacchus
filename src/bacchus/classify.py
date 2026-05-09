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


def _parse_tar_record_size(block: bytes) -> int | None:
    """Size field at offset 124 (ustar); GNU base-256 if high bit of first size byte is set."""
    dig = block[124:136]
    if len(dig) < 12:
        return None
    if dig[0] & 0x80:
        v = 0
        for b in dig[1:12]:
            v = (v << 8) | b
        return v
    try:
        raw = dig.split(b"\0")[0].strip().split()[0]
        return int(raw, 8) if raw else 0
    except ValueError:
        return None


def _extension_header_span(block: bytes) -> int:
    """
    Bytes consumed starting at this 512-byte block for PAX ``x``/``g`` or GNU ``L``/``K`` records.

    Returns 0 if this is not an extension header we skip.
    """
    tf = block[156:157]
    if tf not in (b"x", b"g", b"L", b"K"):
        return 0
    try:
        raw = block[124:136].split(b"\0")[0].strip().split()[0]
        if not raw:
            return 0
        payload = int(raw, 8)
    except ValueError:
        return 0
    return BLOCK + ((payload + 511) // BLOCK) * BLOCK


def _first_member_exceeds_file(data: bytes) -> bool:
    """
    True when the first non-extension member cannot fit in ``data`` (partial inner MV slice).

    Tier-3 inner ``tar -cM`` volume 1 uses a normal ``0`` header; the slice is padded and may end
    with a ustar trailer while the declared member size still spans later volumes.
    """
    n = len(data)
    off = 0
    for _ in range(128):
        if off + BLOCK > n:
            return False
        block = data[off : off + BLOCK]
        tf = block[156:157]
        if tf == b"M":
            return False
        if tf in (b"x", b"g", b"L", b"K"):
            span = _extension_header_span(block)
            off += span if span > 0 else BLOCK
            continue
        rec_sz = _parse_tar_record_size(block)
        if rec_sz is None:
            return False
        member_total = BLOCK + ((rec_sz + 511) // BLOCK) * BLOCK
        return off + member_total > n
    return False


def classify_tar_segment(path: Path) -> TarSegmentKind:
    """
    Inspect decoded (uncompressed) tar bytes.

    - Complete POSIX/ustar archive ends with two 512-byte zero blocks.
    - GNU multi-volume continuation volumes start with typeflag 'M' (GNUTYPE_MULTIVOL)
      at byte index 156 of the first tar record.
    - First volume of a multi-volume split has a normal header and no zero trailer until the last slice.

    Inner ``tar -cM`` **first** slices may end with a ustar trailer but declare a member larger than
    this file; those are classified as ``MV_START``. Restore still coerces a trailing slice that
    looks ``STANDALONE`` while an MV buffer is open to ``MV_END``.
    """
    data = path.read_bytes()
    size = len(data)
    if size < BLOCK:
        raise ValueError(f"tar segment too small: {path}")

    typeflag = data[156:157]
    ends = _ends_with_zero_trailer(data)

    if typeflag == b"M":
        if ends:
            return TarSegmentKind.MV_END
        return TarSegmentKind.MV_MIDDLE

    if _first_member_exceeds_file(data):
        return TarSegmentKind.MV_START

    if ends:
        return TarSegmentKind.STANDALONE
    return TarSegmentKind.MV_START
