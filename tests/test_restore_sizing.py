"""Restore tmpfs peak sizing."""

import gzip
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from bacchus import restore_sizing


def test_restore_ramdisk_size_bytes_slack_and_minimum() -> None:
    """5% slack over peak KiB; floor at 1024 KiB."""
    kb = 1024
    base = kb * 1024
    assert restore_sizing.restore_ramdisk_size_bytes(kb) == base + base // 20

    small = 100
    floor_kb = 1024
    floor_base = floor_kb * 1024
    assert restore_sizing.restore_ramdisk_size_bytes(small) == floor_base + floor_base // 20


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


def test_largest_chunk_artifact_by_size(tmp_path: Path) -> None:
    basename = "demo"
    src = tmp_path / "src"
    src.mkdir()

    small_raw = b"a" * 100
    big_raw = b"b" * 8000
    for idx, raw in ((1, small_raw), (2, big_raw)):
        member = f"{basename}.{idx:06d}.tar"
        (src / f"{member}.gz").write_bytes(gzip.compress(raw))

    paths = [src / f"{basename}.000001.tar.gz", src / f"{basename}.000002.tar.gz"]
    art, member = restore_sizing.largest_chunk_artifact(paths, basename, src, compress=True, password="")
    assert member == f"{basename}.000002.tar"
    assert art == src / f"{basename}.000002.tar.gz"


def test_largest_chunk_artifact_tie_lexicographic(tmp_path: Path) -> None:
    basename = "demo"
    src = tmp_path / "src"
    src.mkdir()
    raw = gzip.compress(b"x")
    for idx in (1, 2):
        member = f"{basename}.{idx:06d}.tar"
        (src / f"{member}.gz").write_bytes(raw)

    paths = [src / f"{basename}.000002.tar.gz", src / f"{basename}.000001.tar.gz"]
    art, member = restore_sizing.largest_chunk_artifact(paths, basename, src, compress=True, password="")
    assert member == f"{basename}.000001.tar"
    assert art == src / f"{basename}.000001.tar.gz"


def test_largest_chunk_artifact_across_roots_picks_max(tmp_path: Path) -> None:
    basename = "demo"
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / f"{basename}.000001.tar.gz").write_bytes(gzip.compress(b"small"))
    (b / f"{basename}.000099.tar.gz").write_bytes(gzip.compress(b"x" * 9000))
    art, member = restore_sizing.largest_chunk_artifact_across_roots(
        [a, b], basename, compress=True, password=""
    )
    assert member == f"{basename}.000099.tar"
    assert art == b / f"{basename}.000099.tar.gz"


def test_worst_peak_is_max_per_chunk_not_max_ciphertext(tmp_path: Path) -> None:
    """Tiny ``.gz`` + huge logical tar beats larger on-disk chunk with smaller uncompressed."""
    basename = "demo"
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / f"{basename}.000001.tar.gz").write_bytes(gzip.compress(b"\x00" * (500 * 1024), compresslevel=9))
    (b / f"{basename}.000002.tar.gz").write_bytes(gzip.compress(os.urandom(100 * 1024), compresslevel=9))

    def one_peak(artifact: Path, member: str) -> int:
        sub = Path(tempfile.mkdtemp(dir=str(tmp_path)))
        try:
            return restore_sizing.restore_intermediate_peak_kb(
                artifact, member, sub, compress=True, password=""
            )
        finally:
            shutil.rmtree(sub, ignore_errors=True)

    p1 = one_peak(a / f"{basename}.000001.tar.gz", f"{basename}.000001.tar")
    p2 = one_peak(b / f"{basename}.000002.tar.gz", f"{basename}.000002.tar")

    big_on_disk, _ = restore_sizing.largest_chunk_artifact_across_roots(
        [a, b], basename, compress=True, password=""
    )
    assert big_on_disk.parent == b

    parent = Path(tempfile.mkdtemp(dir=str(tmp_path)))
    try:
        worst = restore_sizing.worst_restore_intermediate_peak_kb_across_roots(
            [a, b], basename, compress=True, password="", scratch_parent=parent
        )
    finally:
        shutil.rmtree(parent, ignore_errors=True)

    uncomp1_kb = (500 * 1024 + 1023) // 1024
    uncomp2_kb = (100 * 1024 + 1023) // 1024
    slack = max(uncomp1_kb, uncomp2_kb)
    assert worst == max(p1, p2) + slack
    assert p1 > p2
