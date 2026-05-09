"""Restore tmpfs peak sizing."""

import gzip
import subprocess
from pathlib import Path

from bacchus import restore_sizing


def test_restore_ramdisk_size_bytes_slack_and_minimum() -> None:
    """1% slack over peak KiB; floor at 1024 KiB."""
    kb = 1024
    base = kb * 1024
    assert restore_sizing.restore_ramdisk_size_bytes(kb) == base + base // 100

    small = 100
    floor_kb = 1024
    floor_base = floor_kb * 1024
    assert restore_sizing.restore_ramdisk_size_bytes(small) == floor_base + floor_base // 100


def test_gzip_uncompressed_bytes_roundtrip(tmp_path: Path) -> None:
    raw = b"hello bacchus restore peak sizing\n" * 50
    gz_path = tmp_path / "blob.gz"
    gz_path.write_bytes(gzip.compress(raw))
    assert restore_sizing.gzip_uncompressed_bytes(gz_path) == len(raw)


def test_restore_intermediate_peak_kb_compress_only(tmp_path: Path) -> None:
    raw = b"x" * 5000
    member = "demo.000001.tar"
    gz_path = tmp_path / f"{member}.gz"
    gz_path.write_bytes(gzip.compress(raw))

    peak = restore_sizing.restore_intermediate_peak_kb(
        gz_path, member, tmp_path / "scratch", compress=True, password=""
    )
    gz_kb = int(
        subprocess.check_output(["du", "-sk", "--apparent-size", str(gz_path)], text=True).split()[0]
    )
    uncomp_kb = (len(raw) + 1023) // 1024
    assert peak == gz_kb + uncomp_kb


def test_max_restore_peak_kb_takes_max(tmp_path: Path) -> None:
    basename = "demo"
    src = tmp_path / "src"
    scratch = tmp_path / "scratch"
    src.mkdir()
    scratch.mkdir()

    small_raw = b"a" * 100
    big_raw = b"b" * 8000
    for idx, raw in ((1, small_raw), (2, big_raw)):
        member = f"{basename}.{idx:06d}.tar"
        (src / f"{member}.gz").write_bytes(gzip.compress(raw))

    paths = [src / f"{basename}.000001.tar.gz", src / f"{basename}.000002.tar.gz"]
    m = restore_sizing.max_restore_peak_kb(paths, basename, src, compress=True, password="", scratch=scratch)

    p1 = restore_sizing.restore_intermediate_peak_kb(
        src / f"{basename}.000001.tar.gz", f"{basename}.000001.tar", scratch, compress=True, password=""
    )
    p2 = restore_sizing.restore_intermediate_peak_kb(
        src / f"{basename}.000002.tar.gz", f"{basename}.000002.tar", scratch, compress=True, password=""
    )
    assert m == max(p1, p2)
