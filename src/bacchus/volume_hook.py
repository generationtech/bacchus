"""
Invoked by GNU tar --new-volume-script (multi-volume / Tier-3 flows) or manually for last volume.

Usage: python -m bacchus.volume_hook backup|restore
Reads TAR_* and BCS_* from environment.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from bacchus import persistence
from bacchus import stats as statsmod
from bacchus.destination_swap import ensure_backup_destination_space
from bacchus.pipeline import du_sk_apparent, ship_raw_tar


def _load() -> persistence.RuntimeState:
    return persistence.load(Path(os.environ["BCS_DATAFILE"]))


def _save(state: persistence.RuntimeState) -> None:
    persistence.save(Path(os.environ["BCS_DATAFILE"]), state)


def _backup_next_piece_name(tar_base: str, tar_volume: int) -> str:
    """Match bash: vol=${name:-"$TAR_ARCHIVE"}-"$TAR_VOLUME" with name=$(expr "$TAR_ARCHIVE" : '\\(.*\\)-.*')."""
    m = re.match(r"^(.*)-[0-9]+$", tar_base)
    name = m.group(1) if m else ""
    base = name if name else tar_base
    return f"{base}-{tar_volume}"


def _restore_member_filename(tar_base: str, tar_volume: int) -> str:
    """Next archive member filename (e.g. backupfile.tar-2)."""
    m = re.match(r"^(.*)-[0-9]+$", tar_base)
    name = m.group(1) if m else ""
    base = name if name else tar_base
    return f"{base}-{tar_volume}"


def backup_new_volume() -> None:
    """Port of bacchus-backup-new-volume.sh"""
    tar_archive = os.environ.get("TAR_ARCHIVE", "")
    tar_volume = int(os.environ.get("TAR_VOLUME", "1"))
    tar_subcommand = os.environ.get("TAR_SUBCOMMAND", "-c")
    tar_fd = os.environ.get("TAR_FD", "")

    if tar_subcommand not in ("-c",):
        sys.exit(1)

    tararchivedir = str(Path(tar_archive).parent)
    tar_base = Path(tar_archive).name
    vol_piece = _backup_next_piece_name(tar_base, tar_volume)

    datafile = Path(os.environ["BCS_DATAFILE"])
    lowdisk = int(os.environ.get("BCS_LOWDISKSPACE", "2"))
    volumesize_kb = int(os.environ.get("BCS_VOLUMESIZE", "100000"))
    bcs_dest = ensure_backup_destination_space(
        datafile,
        volumesize_kb=volumesize_kb,
        lowdisk_multiplier=lowdisk,
    )

    state = _load()
    source_path = Path(tararchivedir) / tar_base
    archive_source_size = du_sk_apparent(source_path)
    state.source_size_running += archive_source_size

    statistics = os.environ.get("BCS_STATISTICS") == "on"
    runstatistics = os.environ.get("BCS_RUNSTATISTICS") == "on"
    if statistics and runstatistics:
        statsmod.incremental_stats_backup(
            os.environ.get("BCS_BASENAME", "backupfile"),
            state,
            tar_base,
            tar_volume,
        )
    else:
        print(tar_base)

    compress = os.environ.get("BCS_COMPRESS") == "on"
    password = os.environ.get("BCS_PASSWORD", "")
    compressdir = Path(os.environ.get("BCS_COMPRESDIR", "."))

    ship_raw_tar(
        source_path,
        bcs_dest,
        tar_base,
        compress=compress,
        password=password,
        compressdir=compressdir,
    )

    tarnew = Path(tararchivedir) / vol_piece
    if tar_fd == "none":
        endstats = os.environ.get("BCS_ENDSTATISTICS") == "on"
        if statistics and endstats:
            statsmod.completion_stats_backup(state, tar_volume)
        sys.exit(0)

    fd = int(tar_fd)
    os.write(fd, (str(tarnew) + "\n").encode())

    state.incremental_timestamp = int(time.time())
    state.incremental_timestamp_running = 0
    state.bcs_dest = str(bcs_dest)
    _save(state)


def restore_new_volume() -> None:
    """Port of bacchus-restore-new-volume.sh"""
    state = _load()
    tar_archive = os.environ["TAR_ARCHIVE"]
    tar_volume = int(os.environ["TAR_VOLUME"])
    tar_fd = os.environ.get("TAR_FD", "")
    tar_subcommand = os.environ.get("TAR_SUBCOMMAND", "-x")

    tararchivedir = str(Path(tar_archive).parent)
    base = Path(tar_archive).name
    filename = _restore_member_filename(base, tar_volume)
    oldname = base

    bcs_source = Path(state.bcs_source)
    compress = os.environ.get("BCS_COMPRESS") == "on"
    password = os.environ.get("BCS_PASSWORD", "")

    newpath = None
    stop_timestamp = 0
    while True:
        check = bcs_source / filename
        if compress:
            check = Path(str(check) + ".gz")
        if password:
            gpg_candidate = Path(str(check) + ".gpg")
            if not gpg_candidate.is_file() and compress:
                gpg_candidate = bcs_source / (filename + ".gz.gpg")
            if not gpg_candidate.is_file():
                gpg_candidate = bcs_source / (filename + ".gpg")
            check = gpg_candidate

        if compress:
            (Path(os.environ["BCS_COMPRESDIR"]) / oldname).unlink(missing_ok=True)
        if password:
            (Path(os.environ["BCS_DECRYPTDIR"]) / oldname).unlink(missing_ok=True)

        if not check.is_file():
            stop_timestamp = int(time.time())
            print(f"\nArchive volume: {check.name}\nNOT FOUND in:   {bcs_source}\n")
            print(
                "Either place this file in the source directory,\n"
                "or enter a new source path here.\n"
                "Press enter when ready\n"
            )
            np = input().strip()
            print()
            if np:
                newpath = np
                bcs_source = Path(np)
                state.bcs_source = str(bcs_source)
        else:
            if newpath:
                newpath = None
                du = subprocess.run(
                    ["du", "-sk", "--apparent-size", str(bcs_source)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                new_source_size = int(du.stdout.split()[0])
                state.source_size_total += new_source_size
                nv = len(glob.glob(str(bcs_source / f'{os.environ["BCS_BASENAME"]}.tar*')))
                state.archive_volumes += nv
                resume_ts = int(time.time())
                state.start_timestamp_running += resume_ts - stop_timestamp
                state.incremental_timestamp_running += resume_ts - stop_timestamp
            break

    if tar_subcommand != "-x":
        sys.exit(1)

    # GNU tar -x expects decrypted/decompressed plain .tar segment path for -f chain;
    # first volume path is passed to outer tar; subsequent via hook.
    plain = bcs_source / filename
    if not os.access(plain, os.R_OK) and not compress and not password:
        # will be created by Process_Volume from raw .tar only
        pass

    statistics = os.environ.get("BCS_STATISTICS") == "on"
    runstatistics = os.environ.get("BCS_RUNSTATISTICS") == "on"
    if statistics and runstatistics:
        statsmod.incremental_stats_restore(
            os.environ.get("BCS_BASENAME", "backupfile"),
            state,
            filename,
            tar_volume,
        )
    else:
        print(filename)

    state.incremental_timestamp = int(time.time())
    from bacchus.pipeline import process_volume_restore

    _, src_sz, dst_sz = process_volume_restore(
        bcs_source,
        filename,
        Path(os.environ["BCS_DECRYPTDIR"]),
        Path(os.environ["BCS_COMPRESDIR"]),
        compress=compress,
        password=password,
    )

    if tar_fd == "none":
        sys.exit(0)

    fd = int(tar_fd)
    basename = os.environ.get("BCS_BASENAME", "backupfile")
    os.write(fd, (f"{tararchivedir}/{basename}.tar-{tar_volume}\n").encode())

    state.source_size_running += src_sz
    state.dest_size_running += dst_sz
    state.incremental_timestamp_running = 0
    _save(state)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "backup":
        backup_new_volume()
    elif mode == "restore":
        restore_new_volume()
    else:
        print("usage: python -m bacchus.volume_hook backup|restore", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
