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
