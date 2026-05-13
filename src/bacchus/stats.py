"""Statistics and estimates (ports duration_readable, incremental_stats, completion_stats)."""

from __future__ import annotations

import glob
import os
import tempfile
from contextlib import contextmanager
import subprocess
import time
from pathlib import Path
from typing import TextIO

from bacchus import persistence

# Optional session log (same lines as incremental/completion stats on the console).
_stats_log_fp: TextIO | None = None


def create_default_stats_log_path() -> Path:
    """
    Allocate an empty statistics log path, preferring tmpfs-style directories
    (``/dev/shm``, then ``/run/user/$UID``) so the log does not pin the backup destination mount.
    """
    bases: list[Path] = []
    uid = os.getuid()
    for d in (Path("/dev/shm"), Path(f"/run/user/{uid}"), Path(tempfile.gettempdir())):
        if d.is_dir() and os.access(d, os.W_OK):
            bases.append(d)
    last_err: OSError | None = None
    for base in bases:
        try:
            fd, name = tempfile.mkstemp(prefix="bacchus-stats-", suffix=".log", dir=str(base))
            os.close(fd)
            return Path(name)
        except OSError as e:
            last_err = e
            continue
    try:
        fd, name = tempfile.mkstemp(prefix="bacchus-stats-", suffix=".log")
        os.close(fd)
        return Path(name)
    except OSError as e:
        raise OSError(
            "Could not create statistics log under /dev/shm, /run/user/$UID, or temp directories"
        ) from (last_err or e)


def start_stats_file_session(enabled: bool, path: Path | None, *, preamble: str = "") -> None:
    """
    Begin a stats log file for this backup/restore run.

    Truncates ``path`` when enabled. Sets ``BCS_STATS_LOG`` / ``BCS_STATS_LOG_PATH`` so
    subprocess hooks append to the same file. Optional ``preamble`` is written to the file
    only (already shown on the console), before any ``stats_message`` lines.
    """
    global _stats_log_fp
    end_stats_file_session()
    if not enabled or path is None:
        return
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    os.environ["BCS_STATS_LOG"] = "on"
    os.environ["BCS_STATS_LOG_PATH"] = str(path)
    _stats_log_fp = open(path, "a", encoding="utf-8", buffering=1)
    if preamble:
        _stats_log_fp.write(preamble)
        _stats_log_fp.flush()


def end_stats_file_session() -> None:
    global _stats_log_fp
    if _stats_log_fp is not None:
        try:
            _stats_log_fp.close()
        finally:
            _stats_log_fp = None
    os.environ.pop("BCS_STATS_LOG", None)
    os.environ.pop("BCS_STATS_LOG_PATH", None)


@contextmanager
def stats_file_session(enabled: bool, path: Path | None, *, preamble: str = ""):
    """Truncate/open stats log when ``enabled``; always close and clear env in ``finally``."""
    start_stats_file_session(enabled, path, preamble=preamble)
    try:
        yield
    finally:
        end_stats_file_session()


def _ensure_stats_file_sink() -> None:
    global _stats_log_fp
    if _stats_log_fp is not None:
        return
    if os.environ.get("BCS_STATS_LOG") != "on":
        return
    p = os.environ.get("BCS_STATS_LOG_PATH", "").strip()
    if not p:
        return
    lp = Path(p)
    lp.parent.mkdir(parents=True, exist_ok=True)
    _stats_log_fp = open(lp, "a", encoding="utf-8", buffering=1)


def stats_message(*args: object, sep: str = " ", end: str = "\n", flush: bool = True) -> None:
    """Print to stdout and mirror to the stats log file when a session or env is active."""
    _ensure_stats_file_sink()
    line = sep.join(str(a) for a in args)
    print(line, end=end, flush=flush)
    if _stats_log_fp is not None:
        _stats_log_fp.write(line + ("" if end is None else end))
        _stats_log_fp.flush()

# Fixed gutter between incremental stats columns (after pct field through timestamp;
# also between ``remain..`` and ``elapsed..``).
STATS_INCREMENTAL_COL_GAP = "  "

# ``Total size:`` / ``Chunks (rough):`` label column width for pre-run estimate lines.
STATS_ESTIMATE_LABEL_WIDTH = 28


def duration_readable(total_seconds: int | float) -> str:
    total_seconds = int(total_seconds)
    string_date = ""
    days = total_seconds // 3600 // 24
    if days > 0:
        string_date += f"{days}d"
    remainder = total_seconds - days * 3600 * 24
    hours = remainder // 3600
    if hours > 0:
        if string_date:
            string_date += ":"
        string_date += f"{hours}h"
    remainder = remainder - hours * 3600
    minutes = remainder // 60
    if minutes > 0:
        if string_date:
            string_date += ":"
        string_date += f"{minutes}m"
    remainder = remainder - minutes * 60
    if remainder > 0:
        if string_date:
            string_date += ":"
        string_date += f"{remainder}s"
    return string_date


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", "")


def _backup_progress_pct(state: "persistence.RuntimeState") -> int:
    """Percent of source tree covered by running tar size (KiB); cap at 100."""
    total = state.source_size_total
    if total <= 0:
        return 0
    return min(100, (state.source_size_running * 100) // total)


def _chunked_volume_total_display(state: persistence.RuntimeState, tar_volume: int) -> int:
    """
    Running estimate of total chunk count for ``/NNN``, from bytes processed vs total
    (avoids integer-percent quantization), floored by ``archive_volumes`` and ``tar_volume``,
    then lightly EMA-smoothed via ``state.chunk_total_display_smooth``.
    """
    archive_volumes = state.archive_volumes
    running = state.source_size_running
    total = state.source_size_total
    if running <= 0 or total <= 0:
        return max(archive_volumes, tar_volume) if archive_volumes else tar_volume
    pct = min(100, (running * 100) // total)
    if pct >= 100:
        state.chunk_total_display_smooth = tar_volume
        return tar_volume
    raw = max(
        tar_volume,
        archive_volumes,
        (tar_volume * total + running - 1) // running,
    )
    prev = state.chunk_total_display_smooth
    if prev <= 0:
        cap = raw
    else:
        cap = (3 * prev + raw + 2) // 4
    cap = max(tar_volume, archive_volumes, cap)
    state.chunk_total_display_smooth = cap
    return cap


def _fmt_kb_signed_scaled(kb: int) -> str:
    """Like :func:`_fmt_kb_scaled` but preserves sign for deltas (e.g. tar overhead)."""
    if kb == 0:
        return "0K"
    sign = "-" if kb < 0 else ""
    body = _fmt_kb_scaled(abs(kb))
    return sign + body


def _fmt_kb_scaled(kb: int) -> str:
    """
    Format KiB counts (``du -sk`` / ``du_sk_apparent``) with K/M/G/T/P suffix.
    Uses 1024 steps; advances to the next unit while the value is >= 1000
    (so e.g. 1000 KiB becomes ~1M, not ``1000K``).
    """
    if kb <= 0:
        return "0K"
    KB = 1024.0
    suffixes = ("K", "M", "G", "T", "P")
    v = float(kb)
    u = 0
    while u < len(suffixes) - 1 and v >= 1000:
        v /= KB
        u += 1
    rounded = round(v, 1)
    if abs(rounded - int(round(rounded))) < 1e-6:
        num = str(int(round(rounded)))
    else:
        num = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return f"{num}{suffixes[u]}"


def _fmt_stats_pct(pct: int) -> str:
    """Progress / compression percent: fixed width so ``100%`` does not shift later columns."""
    pct = max(0, min(100, pct))
    if pct == 100:
        return "100%"
    return f"{pct:>3}%"


def _stats_pct_field(pct: int) -> str:
    """Percent token only; ``STATS_INCREMENTAL_COL_GAP`` separates pct from ``remain``."""
    return _fmt_stats_pct(pct)


def _fmt_compr_ratio_pct(comp_ratio: int) -> str:
    """Compression ratio percent text alone (no ``compr..`` prefix); natural width."""
    cr = max(0, min(100, comp_ratio))
    return f"{cr}%"


def _fmt_stats_compr_segment(comp_ratio: int) -> str:
    """
    ``compr..`` stats column: single-digit uses one space after ``..`` (``compr.. 8%``),
    two-digit is flush (``compr..10%``); ``100%`` is three digits after ``..``.
    Width matches for 0–99 so the compr→source gutter stays two spaces with no pad inside compr.
    """
    cr = max(0, min(100, comp_ratio))
    if cr < 10:
        return f"compr.. {cr}%"
    return f"compr..{cr}%"


def _fmt_stats_compr_digits(comp_ratio: int) -> str:
    """Legacy digit width for ``comp_ratio_text_size_running`` / jq persistence (zero-padded)."""
    cr = max(0, min(100, comp_ratio))
    if cr == 100:
        return "100"
    return f"{cr:02d}"


def _emit_incremental_stats_full_line(
    *,
    prefix: str,
    remain_full: str,
    elapsed_seg: str,
    last_full: str,
    avg_full: str,
    compr_seg: str,
    src_seg: str,
    dst_seg: str,
    state: "persistence.RuntimeState",
    date_s: str,
    mv_tail: str,
) -> None:
    """
    Single layout path for backup and restore full incremental rows.

    Requires :attr:`~bacchus.persistence.RuntimeState.stats_line_*` widths to already
    reflect this row's segments (monotonic running maxima updated before calling).
    """
    tail = STATS_INCREMENTAL_COL_GAP.join(
        [
            elapsed_seg.ljust(state.stats_line_elapsed_seg_w),
            last_full.ljust(state.stats_line_last_seg_w),
            avg_full.ljust(state.stats_line_avg_seg_w),
            compr_seg,
            src_seg.ljust(state.stats_line_source_seg_w),
            dst_seg.ljust(state.stats_line_dest_seg_w),
        ]
    )
    body = (
        remain_full.ljust(state.stats_line_remain_seg_w)
        + STATS_INCREMENTAL_COL_GAP
        + tail
    )
    stats_message(prefix + body + STATS_INCREMENTAL_COL_GAP + date_s + mv_tail)


def incremental_stats_backup(
    basename: str,
    state: "persistence.RuntimeState",
    tar_archive: str,
    tar_volume: int,
    *,
    tier3_mv_group: int | None = None,
    tier3_inner_mv_vol: int | None = None,
) -> None:
    archive_volumes = state.archive_volumes
    pct = _backup_progress_pct(state)
    volume_cap = _chunked_volume_total_display(state, tar_volume)
    state.stats_volume_cap_chars_max = max(state.stats_volume_cap_chars_max, len(str(volume_cap)))
    vc_w = state.stats_volume_cap_chars_max
    archive_max_name = len(basename) + vc_w + 6
    archive_max_num = vc_w + 1
    if tier3_inner_mv_vol is not None:
        if tier3_mv_group is not None:
            mv_decor = f"[L{tier3_mv_group} MV {tier3_inner_mv_vol}]"
        else:
            mv_decor = f"[MV {tier3_inner_mv_vol}]"
    else:
        mv_decor = ""
    mv_tail = STATS_INCREMENTAL_COL_GAP + mv_decor if mv_decor else ""
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    short_line = state.source_size_running == 0
    if short_line:
        stats_message(
            f"{tar_archive:<{archive_max_name}s} {f'/{volume_cap}':>{archive_max_num}s} "
            f"{_stats_pct_field(pct)}{mv_tail}"
        )
        return
    avg_time = elapsed_time // tar_volume if tar_volume > 0 else 0
    remain_time = avg_time * max(0, volume_cap - tar_volume)
    if (
        remain_time == 0
        and pct < 100
        and tar_volume > 0
        and avg_time > 0
        and state.source_size_total > 0
        and state.source_size_running < state.source_size_total
    ):
        bpc = max(1, state.source_size_running // tar_volume)
        bytes_rem = state.source_size_total - state.source_size_running
        est_chunks = (bytes_rem + bpc - 1) // bpc
        remain_time = avg_time * est_chunks
    incremental_time = timestamp - state.incremental_timestamp - state.incremental_timestamp_running
    dest_size = state.dest_size_running
    comp_ratio = 100 - ((dest_size * 100) // state.source_size_running) if state.source_size_running else 0
    # Dynamic column widths (running maxima); columns separated by STATS_INCREMENTAL_COL_GAP.
    rem_txt = duration_readable(remain_time) if remain_time > 0 else "0s"
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_full = "remain.." + rem_txt
    state.stats_line_remain_seg_w = max(state.stats_line_remain_seg_w, len(remain_full))

    el_txt = duration_readable(elapsed_time)
    elapsed_seg = "elapsed.." + el_txt
    state.stats_line_elapsed_seg_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg))

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_full = "last.." + inc_txt
    state.stats_line_last_seg_w = max(state.stats_line_last_seg_w, len(last_full))

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_full = "avg.." + avg_txt
    state.stats_line_avg_seg_w = max(state.stats_line_avg_seg_w, len(avg_full))

    cr_legacy = _fmt_stats_compr_digits(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_legacy))
    compr_seg = _fmt_stats_compr_segment(comp_ratio)

    if state.source_size_total > 0:
        src_cap = f"source..{_fmt_kb_scaled(state.source_size_total)}"
        dst_cap = f"dest..{_fmt_kb_scaled(state.source_size_total)}"
        state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_cap))
        state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_cap))

    src_fmt = _fmt_kb_scaled(state.source_size_running)
    dst_fmt = _fmt_kb_scaled(dest_size)
    src_seg = f"source..{src_fmt}"
    dst_seg = f"dest..{dst_fmt}"
    state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_seg))
    state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_seg))

    date_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
    prefix = (
        f"{tar_archive:<{archive_max_name}s} {f'/{volume_cap}':>{archive_max_num}s} "
        f"{_stats_pct_field(pct)}{STATS_INCREMENTAL_COL_GAP}"
    )
    _emit_incremental_stats_full_line(
        prefix=prefix,
        remain_full=remain_full,
        elapsed_seg=elapsed_seg,
        last_full=last_full,
        avg_full=avg_full,
        compr_seg=compr_seg,
        src_seg=src_seg,
        dst_seg=dst_seg,
        state=state,
        date_s=date_s,
        mv_tail=mv_tail,
    )


def incremental_stats_restore(
    basename: str,
    state: "persistence.RuntimeState",
    filename: str,
    tar_volume: int,
    *,
    tier3_mv_group: int | None = None,
    tier3_inner_mv_vol: int | None = None,
) -> None:
    """Restore incremental row; full lines use :func:`_emit_incremental_stats_full_line` like backup."""
    # Chunk total comes only from scanned archive dirs (updated when roots change), not byte estimates.
    vol_total = max(state.archive_volumes, tar_volume)
    state.stats_volume_cap_chars_max = max(state.stats_volume_cap_chars_max, len(str(vol_total)))
    vc_w = state.stats_volume_cap_chars_max
    archive_max_name = len(basename) + vc_w + 6
    archive_max_num = vc_w + 1
    if tier3_inner_mv_vol is not None:
        if tier3_mv_group is not None:
            mv_decor = f"[L{tier3_mv_group} MV {tier3_inner_mv_vol}]"
        else:
            mv_decor = f"[MV {tier3_inner_mv_vol}]"
    else:
        mv_decor = ""
    mv_tail = STATS_INCREMENTAL_COL_GAP + mv_decor if mv_decor else ""
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    pct = (tar_volume * 100) // vol_total if vol_total else 0

    avg_time = elapsed_time // tar_volume if tar_volume > 0 else 0
    remain_time = avg_time * max(0, vol_total - tar_volume)

    incremental_time = timestamp - state.incremental_timestamp - state.incremental_timestamp_running
    comp_ratio = (
        100 - ((state.source_size_running * 100) // state.dest_size_running) if state.dest_size_running else 0
    )

    rem_txt = duration_readable(remain_time) if remain_time > 0 else "0s"
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_full = "remain.." + rem_txt
    state.stats_line_remain_seg_w = max(state.stats_line_remain_seg_w, len(remain_full))

    el_txt = duration_readable(elapsed_time)
    elapsed_seg = "elapsed.." + el_txt
    state.stats_line_elapsed_seg_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg))

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_full = "last.." + inc_txt
    state.stats_line_last_seg_w = max(state.stats_line_last_seg_w, len(last_full))

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_full = "avg.." + avg_txt
    state.stats_line_avg_seg_w = max(state.stats_line_avg_seg_w, len(avg_full))

    cr_legacy = _fmt_stats_compr_digits(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_legacy))
    compr_seg = _fmt_stats_compr_segment(comp_ratio)

    if state.source_size_total > 0:
        src_cap = f"source..{_fmt_kb_scaled(state.source_size_total)}"
        dst_cap = f"dest..{_fmt_kb_scaled(state.source_size_total)}"
        state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_cap))
        state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_cap))

    src_fmt = _fmt_kb_scaled(state.source_size_running)
    dst_fmt = _fmt_kb_scaled(state.dest_size_running)
    src_seg = f"source..{src_fmt}"
    dst_seg = f"dest..{dst_fmt}"
    state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_seg))
    state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_seg))

    date_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
    prefix = (
        f"{filename:<{archive_max_name}s} {f'/{vol_total}':>{archive_max_num}s} "
        f"{_stats_pct_field(pct)}{STATS_INCREMENTAL_COL_GAP}"
    )
    _emit_incremental_stats_full_line(
        prefix=prefix,
        remain_full=remain_full,
        elapsed_seg=elapsed_seg,
        last_full=last_full,
        avg_full=avg_full,
        compr_seg=compr_seg,
        src_seg=src_seg,
        dst_seg=dst_seg,
        state=state,
        date_s=date_s,
        mv_tail=mv_tail,
    )


def completion_stats_backup(state: "persistence.RuntimeState", tar_volume: int) -> None:
    completion_timestamp = int(time.time())
    wall = state.wall_clock_start_timestamp
    completion_base = wall if wall > 0 else state.start_timestamp
    completion_time = completion_timestamp - completion_base - state.start_timestamp_running
    avg_time = completion_time // (tar_volume - 1) if tar_volume > 1 else completion_time
    # Sum of raw per-chunk ``.tar`` sizes (``du --apparent-size``) minus apparent source tree size:
    # tar headers, 512-byte padding, PAX/long-name records, and multivolume glue.
    tar_overhead = state.source_size_running - state.source_size_total
    bcs_dest = Path(state.bcs_dest)
    dest_size_running = state.dest_size_running
    comp_ratio = 100 - ((dest_size_running * 100) // state.source_size_total) if state.source_size_total else 0
    _SUMMARY_W = 34

    def _summary_line(label: str, value: str) -> None:
        stats_message(f"{label:<{_SUMMARY_W}}{value}")

    stats_message("\nBACKUP OPERATION COMPLETE")
    _summary_line("Destination:", str(bcs_dest))
    _summary_line("Total runtime:", duration_readable(completion_time))
    _summary_line("Average time per archive file:", duration_readable(avg_time))
    _summary_line("Number of archive files:", str(tar_volume - 1))
    _summary_line("Large files (MV):", str(state.tier3_large_file_count))
    _summary_line("Tar overhead:", _fmt_kb_signed_scaled(tar_overhead))
    _summary_line("Total size of backup:", _fmt_kb_scaled(state.source_size_total))
    if dest_size_running:
        _summary_line("Total size of destinations:", _fmt_kb_scaled(dest_size_running))
    else:
        _summary_line("Total size of destination:", _fmt_kb_scaled(dest_size_running))
    _summary_line("Overall compression ratio:", f"{comp_ratio}%")


def completion_stats_restore(state: "persistence.RuntimeState", archive_volumes: int, bcs_dest: Path) -> None:
    completion_timestamp = int(time.time())
    completion_time = completion_timestamp - state.start_timestamp - state.start_timestamp_running
    avg_time = completion_time // archive_volumes if archive_volumes else completion_time
    du = subprocess.run(
        ["du", "-sk", "--apparent-size", str(bcs_dest)],
        capture_output=True,
        text=True,
        check=True,
    )
    dest_size = int(du.stdout.split()[0])
    # Running sum of decoded segment sizes vs final restored tree (legacy field).
    tar_overhead = state.dest_size_running - dest_size
    archive_kb = state.source_size_running
    comp_ratio = 100 - ((archive_kb * 100) // dest_size) if dest_size else 0
    stats_message("\nRESTORE OPERATION COMPLETE")
    stats_message(f"Total runtime:                 {duration_readable(completion_time)}")
    stats_message(f"Average time per archive file: {duration_readable(avg_time)}")
    stats_message(f"Number of archive files:       {archive_volumes}")
    stats_message(f"Tar overhead:                  {_fmt_kb_signed_scaled(tar_overhead)}")
    stats_message(f"Total size of source:          {_fmt_kb_scaled(archive_kb)}")
    stats_message(f"Total size of restore:         {_fmt_kb_scaled(dest_size)}")
    stats_message(f"Overall compression ratio:     {comp_ratio}%")


def compute_end(
    bcs_source: Path,
    basename: str,
    tmp_parent: Path,
    compress: bool,
    password: str,
) -> int:
    from bacchus.pipeline import process_volume_restore

    with __import__("tempfile").TemporaryDirectory(dir=str(tmp_parent)) as td:
        td_path = Path(td)
        matches = sorted(glob.glob(str(bcs_source / f"{basename}.tar*")))
        if not matches:
            return 0
        last = matches[-1]
        last = last.replace(".gpg", "").replace(".gz", "")
        name = Path(last).name
        _, _, dest_actual = process_volume_restore(
            bcs_source,
            name,
            td_path,
            td_path,
            compress=compress,
            password=password,
        )
        return dest_actual


def print_estimate_chunked_restore(
    *,
    chunks_on_disk: int,
    chunks_this_run: int,
    start_chunk: int,
    source_size_total_kb: int,
    ramdisk_planned: bool,
    peak_intermediate_kb: int | None,
    tmpfs_size_bytes: int | None,
) -> None:
    """Pre-run summary for manifestless chunked restore (no legacy volume-size math)."""
    stats_message("")
    stats_message(f"Archive chunks on disk:          {chunks_on_disk}")
    stats_message(f"Archive chunks (this run):       {chunks_this_run}")
    if start_chunk > 1:
        stats_message(f"Starting at chunk number:        {start_chunk}")
    stats_message(f"Total size of archive directory: {_fmt_kb_scaled(source_size_total_kb)}")
    if ramdisk_planned and peak_intermediate_kb is not None and tmpfs_size_bytes is not None:
        tmpfs_kb = tmpfs_size_bytes // 1024
        stats_message(f"Peak intermediate (worst chunk): {_fmt_kb_scaled(peak_intermediate_kb)}")
        stats_message(f"Planned tmpfs size:              {_fmt_kb_scaled(tmpfs_kb)}")


def print_estimate(
    volumesize_kb: int,
    archive_volumes: int,
    source_size_total: int,
    bcs_volumesize_end: int,
) -> None:
    stats_message("")
    stats_message(f"Volume size for archive:     {_fmt_int(volumesize_kb)}k")
    stats_message(f"Estimated number of volumes: {archive_volumes}")
    stats_message(f"Estimated size of source:    {_fmt_int(source_size_total)}k")
    total_dest_size = (archive_volumes - 1) * volumesize_kb + bcs_volumesize_end
    stats_message(f"Estimated size of restore:   {_fmt_int(total_dest_size)}k")
    comp_ratio = 100 - ((source_size_total * 100) // total_dest_size) if total_dest_size else 0
    stats_message(f"Estimated compression ratio: {comp_ratio}%")
