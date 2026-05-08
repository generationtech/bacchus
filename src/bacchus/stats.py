"""Statistics and estimates (ports duration_readable, incremental_stats, completion_stats)."""

from __future__ import annotations

import glob
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def incremental_stats_backup(
    basename: str,
    state: "persistence.RuntimeState",
    tar_archive: str,
    tar_volume: int,
) -> None:
    archive_volumes = state.archive_volumes
    archive_max_name = len(basename) + len(str(archive_volumes)) + 6
    archive_max_num = len(str(archive_volumes)) + 1
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    pct = ((tar_volume - 1) * 100) // archive_volumes if archive_volumes else 0
    # Legacy tar -cM skips full stats for the first two volumes; chunked mode prints full lines from chunk 1.
    short_line = state.source_size_running == 0 or (
        tar_volume <= 2 and state.archive_mode != "chunked"
    )
    if short_line:
        print(
            f"{tar_archive:<{archive_max_name}s} {f'/{archive_volumes}':>{archive_max_num}s} {pct:4d}%"
        )
        return
    if state.archive_mode == "chunked" and tar_volume <= 2:
        avg_time = elapsed_time // tar_volume if tar_volume > 0 else 0
        remain_time = avg_time * max(0, archive_volumes - tar_volume) if archive_volumes else 0
    else:
        avg_time = elapsed_time // (tar_volume - 2) if tar_volume > 2 else 0
        remain_time = avg_time * (archive_volumes - tar_volume + 2) if archive_volumes else 0
    incremental_time = timestamp - state.incremental_timestamp - state.incremental_timestamp_running
    bcs_dest = Path(state.bcs_dest)
    dest_size = state.dest_size_running
    if any(bcs_dest.glob(f"{basename}*")):
        du = subprocess.run(
            ["du", "-c", "--apparent-size", str(bcs_dest)],
            capture_output=True,
            text=True,
            check=True,
        )
        dest_size += int(du.stdout.strip().splitlines()[-1].split()[0])
    comp_ratio = 100 - ((dest_size * 100) // state.source_size_running) if state.source_size_running else 0
    # Dynamic column widths (legacy bash incremental_stats): running maxima keep columns aligned.
    rem_txt = duration_readable(remain_time)
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_w = state.remain_text_size_running + 10

    el_txt = duration_readable(elapsed_time)
    elapsed_w = remain_w + 1

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_w = state.incremental_text_size_running + 8

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_w = state.avg_text_size_running + 7

    cr_txt = str(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_txt))
    compr_w = state.comp_ratio_text_size_running + 10

    src_fmt = _fmt_int(state.source_size_running)
    dst_fmt = _fmt_int(dest_size)
    src_seg = f"source..{src_fmt}k"
    dst_seg = f"dest..{dst_fmt}k"
    state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_seg))
    state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_seg))

    line = (
        f"{tar_archive:<{archive_max_name}s} {f'/{archive_volumes}':>{archive_max_num}s} {pct:4d}%  "
        f"{'remain..' + rem_txt:<{remain_w}s}"
        f"{'elapsed..' + el_txt:<{elapsed_w}s}"
        f"{'last..' + inc_txt:<{last_w}s}"
        f"{'avg..' + avg_txt:<{avg_w}s}"
        f"{'compr..' + cr_txt + '%':<{compr_w}s}"
        f"{src_seg:<{state.stats_line_source_seg_w}s} "
        f"{dst_seg:<{state.stats_line_dest_seg_w}s} "
        f"{time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(timestamp))}"
    )
    print(line)


def incremental_stats_restore(
    basename: str,
    state: "persistence.RuntimeState",
    filename: str,
    tar_volume: int,
) -> None:
    archive_volumes = state.archive_volumes
    archive_max_name = len(basename) + len(str(archive_volumes)) + 6
    archive_max_num = len(str(archive_volumes)) + 1
    timestamp = int(time.time())
    elapsed_time = timestamp - state.start_timestamp - state.start_timestamp_running
    incremental_time = timestamp - state.incremental_timestamp - state.incremental_timestamp_running
    avg_time = elapsed_time // (tar_volume - 1) if tar_volume > 1 else 0
    remain_time = avg_time * (archive_volumes - tar_volume + 1) if archive_volumes else 0
    comp_ratio = (
        100 - ((state.source_size_running * 100) // state.dest_size_running) if state.dest_size_running else 0
    )
    pct = (tar_volume * 100) // archive_volumes if archive_volumes else 0

    rem_txt = duration_readable(remain_time)
    state.remain_text_size_running = max(state.remain_text_size_running, len(rem_txt))
    remain_w = state.remain_text_size_running + 10

    el_txt = duration_readable(elapsed_time)
    elapsed_w = remain_w + 1

    inc_txt = duration_readable(incremental_time)
    state.incremental_text_size_running = max(state.incremental_text_size_running, len(inc_txt))
    last_w = state.incremental_text_size_running + 8

    avg_txt = duration_readable(avg_time)
    state.avg_text_size_running = max(state.avg_text_size_running, len(avg_txt))
    avg_w = state.avg_text_size_running + 7

    cr_txt = str(comp_ratio)
    state.comp_ratio_text_size_running = max(state.comp_ratio_text_size_running, len(cr_txt))
    compr_w = state.comp_ratio_text_size_running + 10

    src_fmt = _fmt_int(state.source_size_running)
    dst_fmt = _fmt_int(state.dest_size_running)
    src_seg = f"source..{src_fmt}k"
    dst_seg = f"dest..{dst_fmt}k"
    state.stats_line_source_seg_w = max(state.stats_line_source_seg_w, len(src_seg))
    state.stats_line_dest_seg_w = max(state.stats_line_dest_seg_w, len(dst_seg))

    line = (
        f"{filename:<{archive_max_name}s} {f'/{archive_volumes}':>{archive_max_num}s} {pct:4d}%  "
        f"{'remain..' + rem_txt:<{remain_w}s}"
        f"{'elapsed..' + el_txt:<{elapsed_w}s}"
        f"{'last..' + inc_txt:<{last_w}s}"
        f"{'avg..' + avg_txt:<{avg_w}s}"
        f"{'compr..' + cr_txt + '%':<{compr_w}s}"
        f"{src_seg:<{state.stats_line_source_seg_w}s} "
        f"{dst_seg:<{state.stats_line_dest_seg_w}s} "
        f"{time.strftime('%m-%d-%Y %H:%M:%S', time.localtime(timestamp))}"
    )
    print(line)


def completion_stats_backup(state: "persistence.RuntimeState", tar_volume: int) -> None:
    completion_timestamp = int(time.time())
    completion_time = completion_timestamp - state.start_timestamp - state.start_timestamp_running
    avg_time = completion_time // (tar_volume - 1) if tar_volume > 1 else completion_time
    source_size_total_text = _fmt_int(state.source_size_total)
    tar_overhead = state.source_size_running - state.source_size_total
    bcs_dest = Path(state.bcs_dest)
    du = subprocess.run(
        ["du", "-c", "--apparent-size", str(bcs_dest)],
        capture_output=True,
        text=True,
        check=True,
    )
    dest_size_running = state.dest_size_running + int(du.stdout.strip().splitlines()[-1].split()[0])
    dest_size_running_text = _fmt_int(dest_size_running)
    comp_ratio = 100 - ((dest_size_running * 100) // state.source_size_total) if state.source_size_total else 0
    print("\nBACKUP OPERATION COMPLETE")
    print(f"Total runtime:                 {duration_readable(completion_time)}")
    print(f"Average time per archive file: {duration_readable(avg_time)}")
    print(f"Number of archive files:       {tar_volume - 1}")
    print(f"Tar overhead:                  {_fmt_int(tar_overhead)}k")
    print(f"Total size of backup:          {source_size_total_text}k")
    if dest_size_running:
        print(f"Total size of destinations:    {dest_size_running_text}k")
    else:
        print(f"Total size of destination:     {dest_size_running_text}k")
    print(f"Overall compression ratio:     {comp_ratio}%")


def completion_stats_restore(state: "persistence.RuntimeState", archive_volumes: int, bcs_dest: Path) -> None:
    completion_timestamp = int(time.time())
    completion_time = completion_timestamp - state.start_timestamp - state.start_timestamp_running
    avg_time = completion_time // archive_volumes if archive_volumes else completion_time
    source_size_total_text = _fmt_int(state.source_size_total)
    du = subprocess.run(
        ["du", "-sk", "--apparent-size", str(bcs_dest)],
        capture_output=True,
        text=True,
        check=True,
    )
    dest_size = int(du.stdout.split()[0])
    dest_size_text = _fmt_int(dest_size)
    tar_overhead = state.dest_size_running - dest_size
    comp_ratio = 100 - ((state.source_size_total * 100) // dest_size) if dest_size else 0
    print("\nRESTORE OPERATION COMPLETE")
    print(f"Total runtime:                 {duration_readable(completion_time)}")
    print(f"Average time per archive file: {duration_readable(avg_time)}")
    print(f"Number of archive files:       {archive_volumes}")
    print(f"Tar overhead:                  {_fmt_int(tar_overhead)}k")
    print(f"Total size of source:          {source_size_total_text}k")
    print(f"Total size of restore:         {dest_size_text}k")
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
