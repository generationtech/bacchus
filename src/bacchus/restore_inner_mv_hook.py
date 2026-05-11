"""
GNU tar ``--new-volume-script`` for chunked restore inner tier-3 ``tar -xM``.

Decodes the next outer chunk when tar requests ``TAR_VOLUME`` ≥ 2 (legacy-style on-demand
materialization). Shared prompt/artifact logic with the main restore loop via
:mod:`bacchus.volume_supply`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from bacchus import persistence, stats as statsmod
from bacchus.pipeline import process_volume_restore
from bacchus.volume_supply import ensure_chunk_artifact, max_chunk_seq_across_roots, total_archive_kb_on_roots


def main() -> None:
    state_path = Path(os.environ["BCS_INNER_RESTORE_STATE"])
    if os.environ.get("TAR_FD") == "none":
        sys.exit(0)
    vol = int(os.environ.get("TAR_VOLUME", "0"))
    if vol < 2:
        sys.exit(0)

    st = json.loads(state_path.read_text(encoding="utf-8"))
    fd = int(os.environ["TAR_FD"])

    basename = st["basename"]
    first_seq = int(st["first_chunk_seq"])
    seq = first_seq + vol - 1
    member = f"{basename}.{seq:06d}.tar"

    if vol == 2:
        v1 = st.pop("vol1_plain_path", None)
        if v1:
            Path(v1).unlink(missing_ok=True)
    else:
        prev = st.pop("pending_unlink_plain", None)
        if prev:
            Path(prev).unlink(missing_ok=True)

    compress = bool(st["compress"])
    password = str(st.get("password", ""))
    search_roots = [Path(p) for p in st["search_roots"]]
    datafile = Path(st["datafile"])

    def record_prompt_idle(secs: int) -> None:
        if secs <= 0:
            return
        rt = persistence.load(datafile)
        rt.start_timestamp_running += secs
        rt.incremental_timestamp_running += secs
        persistence.save(datafile, rt)

    src_dir, _artifact = ensure_chunk_artifact(
        member,
        search_roots=search_roots,
        compress=compress,
        password=password,
        record_prompt_idle=record_prompt_idle,
    )
    st["search_roots"] = [str(p.resolve()) for p in search_roots]

    mx_chunks = max_chunk_seq_across_roots(search_roots, basename)
    archive_trees_kb = total_archive_kb_on_roots(search_roots)

    decryptdir = Path(st["decryptdir"])
    compressdir = Path(st["compressdir"])
    decoded, src_sz, dst_sz = process_volume_restore(
        src_dir,
        member,
        decryptdir,
        compressdir,
        compress=compress,
        password=password,
    )
    st["pending_unlink_plain"] = str(decoded.resolve())
    st["hook_decode_count"] = int(st.get("hook_decode_count", 0)) + 1

    os.write(fd, (str(decoded.resolve()) + "\n").encode())

    datafile = Path(st["datafile"])
    rt = persistence.load(datafile)
    rt.source_size_running += src_sz
    rt.dest_size_running += dst_sz

    stats_tar_after_v1 = int(st["stats_tar_volume_after_vol1"])
    tar_vol_index = stats_tar_after_v1 + (vol - 1)
    rt.archive_volumes = max(rt.archive_volumes, mx_chunks, tar_vol_index)
    rt.source_size_total = archive_trees_kb

    if st.get("statistics") and st.get("runstatistics"):
        statsmod.incremental_stats_restore(
            basename,
            rt,
            member,
            tar_vol_index,
            tier3_mv_group=int(st["tier3_mv_group"]),
            tier3_inner_mv_vol=vol,
        )
    elif st.get("statistics"):
        statsmod.stats_message(member)

    rt.incremental_timestamp = int(time.time())
    rt.incremental_timestamp_running = 0
    persistence.save(datafile, rt)

    state_path.write_text(json.dumps(st), encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
