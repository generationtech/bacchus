"""GNU tar --new-volume-script for Tier-3 inner ``tar -cM`` (single huge member)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from bacchus import persistence, stats as statsmod
from bacchus.pipeline import du_sk_apparent, ship_raw_tar


def _next_piece_name(tar_base: str, tar_volume: int) -> str:
    m = re.match(r"^(.*)-[0-9]+$", tar_base)
    name = m.group(1) if m else ""
    base = name if name else tar_base
    return f"{base}-{tar_volume}"


def main() -> None:
    state_path = Path(os.environ["BCS_TIER3_STATE"])
    st = json.loads(state_path.read_text())
    chunk_seq = int(st["chunk_seq"])
    basename = st["basename"]
    dest = Path(st["dest"])
    compress = st["compress"]
    password = str(st.get("password", ""))
    compressdir = Path(st["compressdir"])
    datafile = Path(os.environ["BCS_DATAFILE"])

    tar_archive = os.environ.get("TAR_ARCHIVE", "")
    tar_volume = int(os.environ.get("TAR_VOLUME", "1"))
    tar_fd = os.environ.get("TAR_FD", "")
    tar_base = Path(tar_archive).name
    tararchivedir = Path(tar_archive).parent
    raw_path = tararchivedir / tar_base

    rt = persistence.load(datafile)
    rt.source_size_running += du_sk_apparent(raw_path)

    member = f"{basename}.{chunk_seq:06d}.tar"
    ship_raw_tar(raw_path, dest, member, compress=compress, password=password, compressdir=compressdir)

    st["chunk_seq"] = chunk_seq + 1
    state_path.write_text(json.dumps(st), encoding="utf-8")

    if st.get("statistics"):
        if st.get("runstatistics"):
            statsmod.incremental_stats_backup(basename, rt, member, chunk_seq)
        else:
            print(member)

    rt.incremental_timestamp = int(time.time())
    rt.incremental_timestamp_running = 0
    persistence.save(datafile, rt)

    if tar_fd == "none":
        sys.exit(0)

    fd = int(tar_fd)
    tarnew = tararchivedir / _next_piece_name(tar_base, tar_volume)
    os.write(fd, (str(tarnew) + "\n").encode())


if __name__ == "__main__":
    main()
