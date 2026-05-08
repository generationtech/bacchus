"""
Tests for GNU tar wrappers (``--null -T`` list file avoids ``OSError: [Errno 7] Argument list too long``).

After changes here, re-run a large-tree backup (e.g. metalshop programming tree with multi-GB chunks)
to confirm chunk 12+ completes; that scenario used to exceed ``ARG_MAX`` when paths were passed on argv.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from bacchus import extern


def test_tar_create_archive_uses_null_files_from_not_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_run_check(cmd, env=None, **kwargs):
        captured.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(extern, "run_check", fake_run_check)
    archive = tmp_path / "out.tar"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    paths = [f"deep/sub/file{i}.txt" for i in range(5000)]
    extern.tar_create_archive(paths, archive, cwd, verbose=False)
    assert len(captured) == 1
    cmd = captured[0]
    assert "--null" in cmd
    assert "-T" in cmd
    t_idx = cmd.index("-T")
    assert t_idx == len(cmd) - 2
    assert cmd[-1].endswith(".lst")
    assert not any(a.startswith("deep/sub") for a in cmd)


def test_tar_create_file_archive_uses_null_files_from_not_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_run_check(cmd, env=None, **kwargs):
        captured.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(extern, "run_check", fake_run_check)
    archive = tmp_path / "out.tar"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    paths = [f"a{i}.txt" for i in range(3000)]
    extern.tar_create_file_archive(paths, archive, cwd, append=False, verbose=True)
    assert len(captured) == 1
    cmd = captured[0]
    assert "-c" in cmd
    assert "-v" in cmd
    assert "--null" in cmd and "-T" in cmd
    assert cmd[-1].endswith(".lst")


def test_tar_create_archive_many_members_roundtrip(tmp_path: Path) -> None:
    """Smoke: real tar can read NUL list; avoids E2BIG regression on huge trees."""
    if not shutil.which("tar"):
        pytest.skip("no tar")
    root = tmp_path / "src"
    root.mkdir()
    for i in range(400):
        p = root / f"n{i:04d}.txt"
        p.write_text("x", encoding="utf-8")
    rels = sorted(p.relative_to(tmp_path).as_posix() for p in root.iterdir())
    archive = tmp_path / "bundle.tar"
    extern.tar_create_archive(rels, archive, tmp_path, verbose=False)
    out = tmp_path / "extracted"
    out.mkdir()
    subprocess.run(["tar", "-xf", str(archive), "-C", str(out)], check=True)
    for i in range(400):
        assert (out / "src" / f"n{i:04d}.txt").read_text() == "x"
