from __future__ import annotations

import re
from pathlib import Path

from bacchus import persistence, stats as statsmod


def _assert_incremental_line_gutters(line: str, *, expect_mv: bool) -> None:
    """Progress %% → remain.. uses exactly two spaces; dest column → timestamp uses two spaces."""
    gap = statsmod.STATS_INCREMENTAL_COL_GAP
    assert len(gap) == 2 and gap == "  "
    ridx = line.index("remain..")
    pct_pct = line[:ridx].rfind("%")
    assert pct_pct != -1
    assert line[pct_pct + 1 : ridx] == gap, (
        f"expected {gap!r} after progress percent before remain.., got {line[pct_pct:ridx]!r}"
    )
    ts_m = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line)
    assert ts_m is not None
    dstart = ts_m.start()
    assert line[dstart - 2 : dstart] == gap, (
        f"expected {gap!r} before timestamp, got {line[dstart - 4 : dstart + 4]!r}"
    )
    tail = line[ts_m.end() :]
    if expect_mv:
        assert tail.startswith(gap + "["), f"expected {gap!r}+'[' after timestamp, got {tail[:8]!r}"
    else:
        assert not tail.strip(), f"unexpected trailing content: {tail!r}"


def test_incremental_stats_backup_line_has_spaces(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        source_size_total=10_000_000,
        start_timestamp=1_000,
        incremental_timestamp=1_000,
        source_size_running=2_879_170,
        dest_size_running=2_833_328,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 1_050)
    statsmod.incremental_stats_backup("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out.strip()
    assert re.search(r"source\.\..+\s+dest\.\..+\s+[0-9]{4}-[0-9]{2}-[0-9]{2}", out), (
        f"expected space before date in: {out!r}"
    )
    _assert_incremental_line_gutters(out, expect_mv=False)


def test_incremental_stats_backup_gutters_single_digit_pct_and_tier3_tail(capsys, tmp_path: Path, monkeypatch) -> None:
    """Matches live layout: fixed-width ``  9%  remain..`` and ``…:42  [L1 MV 1]``."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=100,
        source_size_total=1_000_000,
        start_timestamp=0,
        incremental_timestamp=0,
        source_size_running=50_000,
        dest_size_running=40_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 100)
    statsmod.incremental_stats_backup(
        "test", state, "test.000001.tar", 1, tier3_mv_group=1, tier3_inner_mv_vol=1
    )
    out = capsys.readouterr().out.strip()
    assert re.search(r"/\d+\s+  5%  remain\.\.", out), f"expected fixed-width pct before remain.. in {out!r}"
    _assert_incremental_line_gutters(out, expect_mv=True)


def test_incremental_stats_chunked_volume_one_full_line_with_last(capsys, tmp_path: Path, monkeypatch) -> None:
    """Chunked mode prints full stats from volume 1; last column uses time since incremental_timestamp."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
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


def test_incremental_stats_backup_short_line_when_no_bytes_shipped(capsys, tmp_path: Path) -> None:
    """No incremental line until the first chunk has non-zero shipped source size."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        start_timestamp=100,
        incremental_timestamp=400,
        source_size_running=0,
        dest_size_running=0,
    )
    statsmod.incremental_stats_backup("test", state, "test.000001.tar", 1)
    out = capsys.readouterr().out.strip()
    assert "remain.." not in out
    assert "  0%" in out


def test_incremental_stats_restore_line_has_spaces(capsys, monkeypatch) -> None:
    monkeypatch.setattr(statsmod.time, "time", lambda: 1_060)
    state = persistence.RuntimeState(
        bcs_dest="/tmp",
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_030,
        incremental_timestamp_running=0,
        source_size_total=50_000,
        source_size_running=100,
        dest_size_running=200,
    )
    statsmod.incremental_stats_restore("test", state, "test.000003.tar", 3)
    out = capsys.readouterr().out.strip()
    assert re.search(r"source\.\.\S+\s+dest\.\.\S+\s+[0-9]{4}-[0-9]{2}", out), (
        f"expected scaled source/dest and space before date in: {out!r}"
    )


def test_incremental_stats_restore_volume_one_shows_remain(capsys, monkeypatch) -> None:
    monkeypatch.setattr(statsmod.time, "time", lambda: 1_100)
    state = persistence.RuntimeState(
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_000,
        incremental_timestamp_running=0,
        source_size_total=100_000,
        source_size_running=5_000,
        dest_size_running=4_000,
    )
    statsmod.incremental_stats_restore("test", state, "test.000001.tar", 1)
    out = capsys.readouterr().out
    assert "remain..15m" in out


def test_incremental_stats_restore_tier3_suffix(capsys, monkeypatch) -> None:
    monkeypatch.setattr(statsmod.time, "time", lambda: 1_500)
    state = persistence.RuntimeState(
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_400,
        incremental_timestamp_running=0,
        source_size_total=100_000,
        source_size_running=10_000,
        dest_size_running=9_000,
    )
    statsmod.incremental_stats_restore(
        "test",
        state,
        "test.000017.tar",
        17,
        tier3_mv_group=2,
        tier3_inner_mv_vol=4,
    )
    out = capsys.readouterr().out
    assert "[L2 MV 4]" in out
    assert re.search(r"\d{2}:\d{2}:\d{2}  \[L2 MV 4\]", out)


def test_incremental_stats_restore_last_reflects_incremental_timestamp(capsys, monkeypatch) -> None:
    clock = [1_200]

    def bump_clock() -> int:
        return clock[0]

    monkeypatch.setattr(statsmod.time, "time", bump_clock)
    state = persistence.RuntimeState(
        archive_volumes=10,
        start_timestamp=1_000,
        incremental_timestamp=1_150,
        incremental_timestamp_running=0,
        source_size_total=100_000,
        source_size_running=5_000,
        dest_size_running=4_000,
    )
    statsmod.incremental_stats_restore("test", state, "test.000001.tar", 1)
    out1 = capsys.readouterr().out
    assert "last..50s" in out1

    clock[0] = 1_210
    state.incremental_timestamp = 1_200
    state.source_size_running = 10_000
    state.dest_size_running = 8_000
    statsmod.incremental_stats_restore("test", state, "test.000002.tar", 2)
    out2 = capsys.readouterr().out
    assert "last..10s" in out2


def test_incremental_stats_chunked_avoids_dest_du_rescan(tmp_path: Path, monkeypatch, capsys) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        source_size_total=100_000,
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
    assert "dest..1.5M" in out


def test_incremental_stats_backup_volume_cap_exceeds_estimate(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=5,
        source_size_total=100_000,
        start_timestamp=0,
        incremental_timestamp=0,
        source_size_running=90_000,
        dest_size_running=6_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 300)
    statsmod.incremental_stats_backup("test", state, "test.000010.tar", 10)
    out = capsys.readouterr().out
    assert "/12 " in out
    assert "90%" in out
    assert "23h" not in out


def test_incremental_stats_chunked_volume_slash_matches_source_pct(capsys, tmp_path: Path, monkeypatch) -> None:
    """At vol 77 and 37% source progress, /NNN uses byte-ratio ceil(77*10000/3700) == 209."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=182,
        source_size_total=10_000,
        start_timestamp=0,
        incremental_timestamp=0,
        source_size_running=3_700,
        dest_size_running=1_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 100)
    statsmod.incremental_stats_backup("test", state, "test.000077.tar", 77)
    out = capsys.readouterr().out
    assert "37%" in out
    assert "/209 " in out


def test_incremental_stats_chunked_avg_per_chunk_not_old_divisor(capsys, tmp_path: Path, monkeypatch) -> None:
    """Average elapsed time divides by shipped chunk count, not (tar_volume - 2)."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
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


def test_incremental_stats_chunked_remain_shows_zero_at_full_progress(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        source_size_total=1000,
        start_timestamp=0,
        incremental_timestamp=0,
        incremental_timestamp_running=0,
        source_size_running=1000,
        dest_size_running=500,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 1000)
    statsmod.incremental_stats_backup("test", state, "test.000010.tar", 10)
    out = capsys.readouterr().out
    assert "100%" in out
    assert "remain..0s" in out


def test_incremental_stats_chunked_remain_fallback_when_volume_cap_equals_tar(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    """If chunk denominator says no volumes left but source pct < 100, use byte-based chunk estimate."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        source_size_total=100_000,
        start_timestamp=0,
        incremental_timestamp=0,
        incremental_timestamp_running=0,
        source_size_running=99_000,
        dest_size_running=50_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 1000)
    monkeypatch.setattr(statsmod, "_chunked_volume_total_display", lambda st, tv: tv)
    statsmod.incremental_stats_backup("test", state, "test.000010.tar", 10)
    out = capsys.readouterr().out
    assert "99%" in out
    assert re.search(r"remain\.\.[1-9]", out), f"expected non-zero remain duration in {out!r}"


def test_incremental_stats_backup_tier3_shows_inner_mv_volume(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=10,
        source_size_total=100_000,
        start_timestamp=0,
        incremental_timestamp=0,
        source_size_running=50_000,
        dest_size_running=40_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 500)
    statsmod.incremental_stats_backup(
        "test", state, "test.000005.tar", 5, tier3_mv_group=1, tier3_inner_mv_vol=3
    )
    out = capsys.readouterr().out
    assert "[L1 MV 3]" in out
    assert "test.000005.tar [L" not in out
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  \[L1 MV 3\]", out)


def test_completion_stats_chunked_skips_du_uses_dest_running_only(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "extra.bin").write_bytes(b"x" * 5000)
    state = persistence.RuntimeState(
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
    assert "Destination:" in out
    assert str(dest) in out
    assert "Overall compression ratio:" in out
    assert re.search(r"Overall compression ratio:\s+50%", out)
    assert "Total size of destinations:" in out
    assert "100K" in out
    assert re.search(r"Large files \(MV\):\s+0", out)


def test_completion_stats_chunked_large_file_count_nonzero(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        source_size_total=200,
        source_size_running=200,
        dest_size_running=100,
        start_timestamp=1000,
        tier3_large_file_count=4,
    )

    def boom_run(*args, **kwargs):
        raise AssertionError("chunked completion must not invoke subprocess.run (du)")

    monkeypatch.setattr(statsmod.subprocess, "run", boom_run)
    statsmod.completion_stats_backup(state, tar_volume=2)
    out = capsys.readouterr().out
    assert re.search(r"Large files \(MV\):\s+4", out)


def test_completion_stats_chunked_total_runtime_uses_wall_clock(capsys, tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
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
    assert re.search(r"Total runtime:\s+5m", out)


def test_fmt_kb_scaled() -> None:
    assert statsmod._fmt_kb_scaled(0) == "0K"
    assert statsmod._fmt_kb_scaled(999) == "999K"
    assert statsmod._fmt_kb_scaled(1000) == "1M"
    assert statsmod._fmt_kb_scaled(1024) == "1M"
    assert statsmod._fmt_kb_scaled(1500) == "1.5M"
    assert statsmod._fmt_kb_scaled(991_700) == "968.5M"


def test_fmt_kb_signed_scaled() -> None:
    assert statsmod._fmt_kb_signed_scaled(0) == "0K"
    assert statsmod._fmt_kb_signed_scaled(1000) == "1M"
    assert statsmod._fmt_kb_signed_scaled(-1000) == "-1M"


def test_fmt_stats_pct_fixed_width() -> None:
    assert statsmod._fmt_stats_pct(0) == "  0%"
    assert statsmod._fmt_stats_pct(5) == "  5%"
    assert statsmod._fmt_stats_pct(42) == " 42%"
    assert statsmod._fmt_stats_pct(100) == "100%"


def test_fmt_compr_ratio_pct_natural_width() -> None:
    assert statsmod._fmt_compr_ratio_pct(0) == "0%"
    assert statsmod._fmt_compr_ratio_pct(8) == "8%"
    assert statsmod._fmt_compr_ratio_pct(42) == "42%"
    assert statsmod._fmt_compr_ratio_pct(100) == "100%"


def test_fmt_stats_compr_segment_fixed_width() -> None:
    assert statsmod._fmt_stats_compr_segment(0) == "compr..  0%"
    assert statsmod._fmt_stats_compr_segment(8) == "compr..  8%"
    assert len(statsmod._fmt_stats_compr_segment(3)) == len(statsmod._fmt_stats_compr_segment(100))


def test_incremental_stats_elapsed_column_seeded_from_first_remain(capsys, tmp_path: Path, monkeypatch) -> None:
    """First full line sets ``elapsed..`` width from that line's remain; no pre-run preseed."""
    dest = tmp_path / "dest"
    dest.mkdir()
    state = persistence.RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=22,
        source_size_total=17_000_000,
        start_timestamp=0,
        incremental_timestamp=0,
        incremental_timestamp_running=0,
        source_size_running=863_000,
        dest_size_running=796_000,
    )
    monkeypatch.setattr(statsmod.time, "time", lambda: 8)
    statsmod.incremental_stats_backup("test", state, "test.000001.tar", 1)
    out = capsys.readouterr().out.rstrip()
    gap = statsmod.STATS_INCREMENTAL_COL_GAP
    i_el = out.index("elapsed..")
    i_last = out.index("last..")
    assert out[i_el - 2 : i_el] == gap, "remain.. cell → elapsed.. uses two-space gutter"
    # Elapsed column width matches first-line remain ceiling, not an oversized preseed.
    assert i_last - i_el == len("elapsed..2m:48s") + len(gap), (
        f"expected tight elapsed→last boundary in {out!r}, span {i_last - i_el}"
    )
    i_src = out.index("source..")
    assert out[i_src - 2 : i_src] == gap
    assert out[i_src - 3] != " ", "compr..→source.. must not have a third padding space"


def test_backup_progress_pct() -> None:
    st = persistence.RuntimeState(source_size_total=1000, source_size_running=250)
    assert statsmod._backup_progress_pct(st) == 25
    st2 = persistence.RuntimeState(source_size_total=100, source_size_running=500)
    assert statsmod._backup_progress_pct(st2) == 100
    st3 = persistence.RuntimeState(source_size_total=0, source_size_running=100)
    assert statsmod._backup_progress_pct(st3) == 0


def test_chunked_volume_total_display() -> None:
    st0 = persistence.RuntimeState(
        archive_volumes=182, source_size_total=10_000, source_size_running=0
    )
    assert statsmod._chunked_volume_total_display(st0, 3) == 182

    st1 = persistence.RuntimeState(
        archive_volumes=182,
        source_size_total=10_000,
        source_size_running=3_700,
        chunk_total_display_smooth=0,
    )
    assert statsmod._chunked_volume_total_display(st1, 77) == 209
    assert st1.chunk_total_display_smooth == 209

    st2 = persistence.RuntimeState(
        archive_volumes=182,
        source_size_total=10_000,
        source_size_running=10_000,
        chunk_total_display_smooth=999,
    )
    assert statsmod._chunked_volume_total_display(st2, 50) == 50
    assert st2.chunk_total_display_smooth == 50

    st3 = persistence.RuntimeState(
        archive_volumes=5, source_size_total=100_000, source_size_running=90_000
    )
    assert statsmod._chunked_volume_total_display(st3, 10) == 12


def test_chunked_volume_total_display_ema_smoothing() -> None:
    st = persistence.RuntimeState(
        archive_volumes=100,
        source_size_total=10_000,
        source_size_running=5000,
        chunk_total_display_smooth=200,
    )
    raw = max(20, 100, (20 * 10_000 + 5000 - 1) // 5000)
    blended = (3 * 200 + raw + 2) // 4
    expected = max(20, 100, blended)
    assert statsmod._chunked_volume_total_display(st, 20) == expected
    assert st.chunk_total_display_smooth == expected
