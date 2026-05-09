"""Tests for tar segment classification."""

from __future__ import annotations

import tarfile
from pathlib import Path

from bacchus.classify import TarSegmentKind, classify_tar_segment


def test_standalone_small_tar(tmp_path: Path) -> None:
    p = tmp_path / "one.tar"
    with tarfile.open(p, "w", format=tarfile.PAX_FORMAT) as tf:
        data = b"hello"
        ti = tarfile.TarInfo(name="hello.txt")
        ti.size = len(data)
        tf.addfile(ti, __import__("io").BytesIO(data))
    assert classify_tar_segment(p) == TarSegmentKind.STANDALONE


def _gnu_base256_size_field(n: int) -> bytes:
    out = bytearray(12)
    out[0] = 0x80
    x = n
    for i in range(11, 0, -1):
        out[i] = x & 0xFF
        x >>= 8
    return bytes(out)


def test_inner_mv_first_slice_base256_size_with_trailer(tmp_path: Path) -> None:
    """Huge member sizes use GNU base-256 in the ustar size field (e.g. proc pagemap)."""
    block = bytearray(512)
    block[0:8] = b"pagemap\x00"
    block[156:157] = b"0"
    block[124:136] = _gnu_base256_size_field(14_915_207_168)
    block[257:263] = b"ustar\x00"
    block[263:265] = b"00"
    body = bytes(block) + b"\x00" * 512 + (b"\x00" * (512 * 2))
    p = tmp_path / "slice.bin"
    p.write_bytes(body)
    assert classify_tar_segment(p) == TarSegmentKind.MV_START


def test_inner_mv_first_slice_huge_member_with_ustar_trailer(tmp_path: Path) -> None:
    """Inner ``tar -cM`` volume 1 can end with two zero blocks yet omit most member bytes."""
    block = bytearray(512)
    block[0:8] = b"pagemap\x00"
    block[156:157] = b"0"
    size_oct = f"{10_000_000:o}".encode()
    block[124 : 124 + len(size_oct)] = size_oct
    block[257:263] = b"ustar\x00"
    block[263:265] = b"00"
    body = bytes(block) + b"\x00" * 512 + (b"\x00" * (512 * 2))
    p = tmp_path / "slice.tar"
    p.write_bytes(body)
    assert classify_tar_segment(p) == TarSegmentKind.MV_START


def test_mv_start_truncated_no_trailer(tmp_path: Path) -> None:
    p = tmp_path / "trunc.tar"
    with tarfile.open(p, "w", format=tarfile.PAX_FORMAT) as tf:
        data = b"x" * 2048
        ti = tarfile.TarInfo(name="big.bin")
        ti.size = len(data)
        tf.addfile(ti, __import__("io").BytesIO(data))
    raw = p.read_bytes()
    # Remove all trailing 512-byte zero blocks (ustar end-of-archive marker)
    while raw.endswith(b"\x00" * 512):
        raw = raw[:-512]
    p.write_bytes(raw)
    assert classify_tar_segment(p) == TarSegmentKind.MV_START
