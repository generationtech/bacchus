from __future__ import annotations

import re
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
