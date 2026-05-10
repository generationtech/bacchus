"""Statistics and estimates (ports duration_readable, incremental_stats, completion_stats)."""

from __future__ import annotations

import glob
import subprocess
import time
from pathlib import Path

from bacchus import persistence


def duration_readable(total_seconds: int) -> str:
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
    """Progress percent for stats lines: always two digits before % until 100."""
    pct = max(0, min(100, pct))
    if pct == 100:
        return "100%"
    return f"{pct:02d}%"


def _stats_pct_field(pct: int) -> str:
    """Fixed-width token so ``09%`` and ``100%`` align with following columns."""
    return f"{_fmt_stats_pct(pct):<4}"


def _fmt_stats_compr_digits(comp_ratio: int) -> str:
    """Compression ratio digits (no %%); zero-pad 0–99, ``100`` when full."""
    cr = max(0, min(100, comp_ratio))
    if cr == 100:
        return "100"
    return f"{cr:02d}"


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
            mv_suffix = f" [L{tier3_mv_group} MV {tier3_inner_mv_vol}]"
        else:
            mv_suffix = f" [MV {tier3_inner_mv_vol}]"
    else:
        mv_suffix = ""
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    short_line = state.source_size_running == 0
    if short_line:
        print(
            f"{tar_archive:<{archive_max_name}s} {f'/{volume_cap}':>{archive_max_num}s} {_stats_pct_field(pct)}{mv_suffix}"
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
    # Dynamic column widths (legacy bash incremental_stats): running maxima keep columns aligned.
    rem_txt = duration_readable(remain_time) if remain_time > 0 else "0s"
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_w = state.remain_text_size_running + 10

    el_txt = duration_readable(elapsed_time)
    elapsed_seg = "elapsed.." + el_txt
    # +1 trailing slot so ``last..`` never abuts ``elapsed..`` when width equals text length.
    state.stats_line_elapsed_seg_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg) + 1)

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_w = state.incremental_text_size_running + 8

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_w = state.avg_text_size_running + 7

    cr_txt = _fmt_stats_compr_digits(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_txt))
    compr_w = state.comp_ratio_text_size_running + 10

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

    date_s = time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(timestamp))
    elapsed_col_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg) + 1)
    line = (
        f"{tar_archive:<{archive_max_name}s} {f'/{volume_cap}':>{archive_max_num}s} {_stats_pct_field(pct)}  "
        f"{'remain..' + rem_txt:<{remain_w}s}"
        f"{elapsed_seg:<{elapsed_col_w}s}"
        f"{'last..' + inc_txt:<{last_w}s}"
        f"{'avg..' + avg_txt:<{avg_w}s}"
        f"{'compr..' + cr_txt + '%':<{compr_w}s}"
        f"{src_seg:<{state.stats_line_source_seg_w}s} "
        f"{dst_seg:<{state.stats_line_dest_seg_w}s} "
        f"{date_s}{mv_suffix}"
    )
    print(line)


def incremental_stats_restore(
    basename: str,
    state: "persistence.RuntimeState",
    filename: str,
    tar_volume: int,
    *,
    tier3_mv_group: int | None = None,
    tier3_inner_mv_vol: int | None = None,
) -> None:
    archive_volumes = state.archive_volumes
    vol_den_w = max(len(str(archive_volumes)), len(str(tar_volume)))
    archive_max_name = len(basename) + vol_den_w + 6
    archive_max_num = vol_den_w + 1
    if tier3_inner_mv_vol is not None:
        if tier3_mv_group is not None:
            mv_suffix = f" [L{tier3_mv_group} MV {tier3_inner_mv_vol}]"
        else:
            mv_suffix = f" [MV {tier3_inner_mv_vol}]"
    else:
        mv_suffix = ""
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    pct = (tar_volume * 100) // archive_volumes if archive_volumes else 0

    avg_time = elapsed_time // tar_volume if tar_volume > 0 else 0
    remain_time = avg_time * max(0, archive_volumes - tar_volume)
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
    comp_ratio = (
        100 - ((state.source_size_running * 100) // state.dest_size_running) if state.dest_size_running else 0
    )

    rem_txt = duration_readable(remain_time) if remain_time > 0 else "0s"
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_w = state.remain_text_size_running + 10

    el_txt = duration_readable(elapsed_time)
    elapsed_seg = "elapsed.." + el_txt
    state.stats_line_elapsed_seg_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg) + 1)

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_w = state.incremental_text_size_running + 8

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_w = state.avg_text_size_running + 7

    cr_txt = _fmt_stats_compr_digits(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_txt))
    compr_w = state.comp_ratio_text_size_running + 10

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

    elapsed_col_w = max(state.stats_line_elapsed_seg_w, len(elapsed_seg) + 1)
    line = (
        f"{filename:<{archive_max_name}s} {f'/{archive_volumes}':>{archive_max_num}s} {_stats_pct_field(pct)}  "
        f"{'remain..' + rem_txt:<{remain_w}s}"
        f"{elapsed_seg:<{elapsed_col_w}s}"
        f"{'last..' + inc_txt:<{last_w}s}"
        f"{'avg..' + avg_txt:<{avg_w}s}"
        f"{'compr..' + cr_txt + '%':<{compr_w}s}"
        f"{src_seg:<{state.stats_line_source_seg_w}s} "
        f"{dst_seg:<{state.stats_line_dest_seg_w}s} "
        f"{time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(timestamp))}{mv_suffix}"
    )
    print(line)


def completion_stats_backup(state: "persistence.RuntimeState", tar_volume: int) -> None:
    completion_timestamp = int(time.time())
    wall = state.wall_clock_start_timestamp
    completion_base = wall if wall > 0 else state.start_timestamp
    completion_time = completion_timestamp - completion_base - state.start_timestamp_running
    avg_time = completion_time // (tar_volume - 1) if tar_volume > 1 else completion_time
    tar_overhead = state.source_size_running - state.source_size_total
    bcs_dest = Path(state.bcs_dest)
    dest_size_running = state.dest_size_running
    comp_ratio = 100 - ((dest_size_running * 100) // state.source_size_total) if state.source_size_total else 0
    _SUMMARY_W = 34

    def _summary_line(label: str, value: str) -> None:
        print(f"{label:<{_SUMMARY_W}}{value}")

    print("\nBACKUP OPERATION COMPLETE")
    _summary_line("Destination:", str(bcs_dest))
    _summary_line("Total runtime:", duration_readable(completion_time))
    _summary_line("Average time per archive file:", duration_readable(avg_time))
    _summary_line("Number of archive files:", str(tar_volume - 1))
    _summary_line("Large files (MV):", str(state.tier3_large_file_count))
    _summary_line("Tar overhead:", _fmt_kb_scaled(tar_overhead))
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
    tar_overhead = state.dest_size_running - dest_size
    comp_ratio = 100 - ((state.source_size_total * 100) // dest_size) if dest_size else 0
    print("\nRESTORE OPERATION COMPLETE")
    print(f"Total runtime:                 {duration_readable(completion_time)}")
    print(f"Average time per archive file: {duration_readable(avg_time)}")
    print(f"Number of archive files:       {archive_volumes}")
    print(f"Tar overhead:                  {_fmt_kb_scaled(tar_overhead)}")
    print(f"Total size of source:          {_fmt_kb_scaled(state.source_size_total)}")
    print(f"Total size of restore:         {_fmt_kb_scaled(dest_size)}")
    print(f"Overall compression ratio:     {comp_ratio}%")


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
    print(f"\nArchive chunks on disk:          {chunks_on_disk}")
    print(f"Archive chunks (this run):       {chunks_this_run}")
    if start_chunk > 1:
        print(f"Starting at chunk number:        {start_chunk}")
    print(f"Total size of archive directory: {_fmt_kb_scaled(source_size_total_kb)}")
    if ramdisk_planned and peak_intermediate_kb is not None and tmpfs_size_bytes is not None:
        tmpfs_kb = tmpfs_size_bytes // 1024
        print(f"Peak intermediate (worst chunk): {_fmt_kb_scaled(peak_intermediate_kb)}")
        print(f"Planned tmpfs size:              {_fmt_kb_scaled(tmpfs_kb)}")


def print_estimate(
    volumesize_kb: int,
    archive_volumes: int,
    source_size_total: int,
    bcs_volumesize_end: int,
) -> None:
    print(f"\nVolume size for archive:     {_fmt_int(volumesize_kb)}k")
    print(f"Estimated number of volumes: {archive_volumes}")
    print(f"Estimated size of source:    {_fmt_int(source_size_total)}k")
    total_dest_size = (archive_volumes - 1) * volumesize_kb + bcs_volumesize_end
    print(f"Estimated size of restore:   {_fmt_int(total_dest_size)}k")
    comp_ratio = 100 - ((source_size_total * 100) // total_dest_size) if total_dest_size else 0
    print(f"Estimated compression ratio: {comp_ratio}%")
