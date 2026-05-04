"""End-to-end chunked backup/restore (requires tar, pigz optional)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> None:
    subprocess.check_call([sys.executable, "-m", "bacchus", *args])


def test_chunked_no_compress_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (tmp_path / "tard").mkdir()
    (tmp_path / "comp").mkdir()
    (tmp_path / "dec").mkdir()
    (src / "hello.txt").write_text("world", encoding="utf-8")
    _run(
        "backup",
        "-s",
        str(src),
        "-d",
        str(dst),
        "-b",
        "t",
        "-v",
        "100",
        "-z",
        "off",
        "-r",
        "off",
        "-t",
        str(tmp_path / "tard"),
        "-c",
        str(tmp_path / "comp"),
        "-C",
        "off",
        "-E",
        "off",
        "-S",
        "off",
        "-W",
        "off",
        "-X",
        "off",
        "-u",
        "off",
        "--archive-mode",
        "chunked",
    )
    _run(
        "restore",
        "-s",
        str(dst),
        "-d",
        str(out),
        "-b",
        "t",
        "-z",
        "off",
        "-r",
        "off",
        "-e",
        str(tmp_path / "dec"),
        "-C",
        "off",
        "-E",
        "off",
        "-S",
        "off",
        "-W",
        "off",
        "-X",
        "off",
        "-u",
        "off",
        "--archive-mode",
        "chunked",
    )
    # restored path preserves source directory name prefix
    hits = list(out.rglob("hello.txt"))
    assert hits, f"expected hello.txt under {out}"
    assert hits[0].read_text(encoding="utf-8") == "world"


def test_legacy_roundtrip(tmp_path: Path) -> None:
    if not shutil.which("tar"):
        return
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (tmp_path / "tard").mkdir()
    (tmp_path / "comp").mkdir()
    (tmp_path / "dec").mkdir()
    (src / "a.txt").write_text("legacy", encoding="utf-8")
    _run(
        "backup",
        "-s",
        str(src),
        "-d",
        str(dst),
        "-b",
        "leg",
        "-v",
        "500",
        "-z",
        "off",
        "-r",
        "off",
        "-t",
        str(tmp_path / "tard"),
        "-c",
        str(tmp_path / "comp"),
        "-C",
        "off",
        "-E",
        "off",
        "-S",
        "off",
        "-W",
        "off",
        "-X",
        "off",
        "-u",
        "off",
        "--archive-mode",
        "legacy",
    )
    _run(
        "restore",
        "-s",
        str(dst),
        "-d",
        str(out),
        "-b",
        "leg",
        "-z",
        "off",
        "-r",
        "off",
        "-e",
        str(tmp_path / "dec"),
        "-C",
        "off",
        "-E",
        "off",
        "-S",
        "off",
        "-W",
        "off",
        "-X",
        "off",
        "-u",
        "off",
        "--archive-mode",
        "legacy",
    )
    hits = list(out.rglob("a.txt"))
    assert hits
    assert hits[0].read_text(encoding="utf-8") == "legacy"
