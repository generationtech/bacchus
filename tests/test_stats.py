from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bacchus import persistence, stats as statsmod


def test_incremental_stats_backup_line_has_spaces(capsys, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_000,
        source_size_running=2_879_170,
        dest_size_running=2_833_328,
    )
    statsmod.incremental_stats_backup("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out.strip()
    assert re.search(r"\d+k dest\.\.", out), f"expected space before dest.. in: {out!r}"
    assert re.search(r"\d+k [0-9]{2}-[0-9]{2}-[0-9]{4}", out), f"expected space before date in: {out!r}"


def test_incremental_stats_chunked_volume_one_full_line_with_last(capsys, tmp_path: Path, monkeypatch) -> None:
    """Chunked mode prints full stats from volume 1; last column uses time since incremental_timestamp."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=100,
        incremental_timestamp=400,
        incremental_timestamp_running=0,
        source_size_running=5000,
        dest_size_running=4000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 700)
    statsmod.incremental_stats_backup("test", state, "test.000001.tar", 1)
    out = capsys.readouterr().out
    assert "remain.." in out
    assert "last..5m" in out


def test_incremental_stats_legacy_volume_one_short_only(capsys, tmp_path: Path) -> None:
    """Legacy tar -cM keeps percent-only lines for the first two volumes."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="legacy",
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=100,
        incremental_timestamp=400,
        source_size_running=5000,
        dest_size_running=4000,
    )
    statsmod.incremental_stats_backup("test", state, "backupfile.tar", 1)
    out = capsys.readouterr().out.strip()
    assert "remain.." not in out
    assert "0%" in out


def test_incremental_stats_restore_line_has_spaces(capsys) -> None:
    state = persistence.RuntimeState(
        bcs_dest="/tmp",
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_000,
        source_size_running=100,
        dest_size_running=200,
    )
    statsmod.incremental_stats_restore("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out.strip()
    assert re.search(r"\d+k dest\.\.", out), f"expected space before dest.. in: {out!r}"
    assert re.search(r"\d+k [0-9]{2}-[0-9]{2}-[0-9]{4}", out), f"expected space before date in: {out!r}"


def test_incremental_stats_chunked_avoids_dest_du_rescan(tmp_path: Path, monkeypatch, capsys) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=100,
        incremental_timestamp=100,
        source_size_running=2000,
        dest_size_running=1500,
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("chunked incremental stats should not call subprocess.run for destination du")

    monkeypatch.setattr(statsmod.subprocess, "run", fail_run)
    statsmod.incremental_stats_backup("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out
    assert "dest..1500k" in out


def test_incremental_stats_legacy_keeps_dest_du_rescan(tmp_path: Path, monkeypatch, capsys) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "test.tar").write_text("x", encoding="utf-8")
    state = persistence.RuntimeState(
        archive_mode="legacy",
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=100,
        incremental_timestamp=100,
        source_size_running=2000,
        dest_size_running=100,
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="123\n123 total\n")

    monkeypatch.setattr(statsmod.subprocess, "run", fake_run)
    statsmod.incremental_stats_backup("test", state, "test.tar-3", 3)
    out = capsys.readouterr().out
    assert "dest..223k" in out


def test_incremental_stats_backup_volume_cap_exceeds_estimate(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        archive_volumes=5,
        start_timestamp=0,
        incremental_timestamp=0,
        source_size_running=10_000,
        dest_size_running=6_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 300)
    statsmod.incremental_stats_backup("test", state, "test.000010.tar", 10)
    out = capsys.readouterr().out
    assert "/10 " in out
    assert " 90%" in out
    assert "23h" not in out


def test_incremental_stats_chunked_avg_per_chunk_not_legacy_divisor(capsys, tmp_path: Path, monkeypatch) -> None:
    """Chunked mode counts every shipped chunk; do not use legacy (tar_volume - 2) average divisor."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        archive_volumes=182,
        start_timestamp=0,
        incremental_timestamp=20,
        incremental_timestamp_running=0,
        source_size_running=10_000,
        dest_size_running=5_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 30)
    statsmod.incremental_stats_backup("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out
    assert "avg..10s" in out
    assert "avg..30s" not in out


def test_completion_stats_chunked_skips_du_uses_dest_running_only(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "extra.bin").write_bytes(b"x" * 5000)
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        source_size_total=200,
        source_size_running=200,
        dest_size_running=100,
        start_timestamp=1000,
    )

    def boom_run(*args, **kwargs):
        raise AssertionError("chunked completion must not invoke subprocess.run (du)")

    monkeypatch.setattr(statsmod.subprocess, "run", boom_run)
    statsmod.completion_stats_backup(state, tar_volume=2)
    out = capsys.readouterr().out
    assert "Overall compression ratio:     50%" in out
    assert "Total size of destinations:    100k" in out


def test_completion_stats_chunked_total_runtime_uses_wall_clock(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="chunked",
        bcs_dest=str(dest),
        source_size_total=200,
        source_size_running=200,
        dest_size_running=100,
        start_timestamp=1000,
        wall_clock_start_timestamp=100,
    )

    monkeypatch.setattr(statsmod.time, "time", lambda: 400)

    def boom_run(*args, **kwargs):
        raise AssertionError("chunked completion must not invoke subprocess.run (du)")

    monkeypatch.setattr(statsmod.subprocess, "run", boom_run)
    statsmod.completion_stats_backup(state, tar_volume=2)
    out = capsys.readouterr().out
    assert "Total runtime:                 5m" in out


def test_completion_stats_legacy_still_uses_du(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        archive_mode="legacy",
        bcs_dest=str(dest),
        source_size_total=200,
        source_size_running=200,
        dest_size_running=0,
        start_timestamp=1000,
    )

    def fake_run(cmd, **kwargs):
        assert "du" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="0\n100 total\n")

    monkeypatch.setattr(statsmod.subprocess, "run", fake_run)
    statsmod.completion_stats_backup(state, tar_volume=2)
    out = capsys.readouterr().out
    assert "Overall compression ratio:     50%" in out
