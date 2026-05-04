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
