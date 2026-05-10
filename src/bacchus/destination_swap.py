"""Prompt to free space or swap backup destination when the target is low (legacy new-volume hook)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from bacchus import persistence


def ensure_backup_destination_space(
    datafile: Path,
    *,
    volumesize_kb: int,
    lowdisk_multiplier: int,
) -> Path:
    """
    Match ``bacchus-backup-new-volume.sh``: loop on ``df`` until available space is at least
    ``volumesize_kb * lowdisk_multiplier``. Optionally prompt for a new destination path; update
    ``RuntimeState.bcs_dest``, ``dest_size_running``, and pause timestamps when swapping.

    ``datafile`` must already contain a persisted ``bcs_dest`` (backup initialization writes it).
    """
    state = persistence.load(datafile)
    bcs_dest = Path(state.bcs_dest)
    lowspace = volumesize_kb * lowdisk_multiplier
    # Legacy tracks a non-empty ``newpath`` across prompts; use a bool so an empty line on a later
    # prompt does not drop accounting for an earlier path change.
    need_dest_accounting = False
    oldpath = str(bcs_dest)
    stop_timestamp = 0

    while True:
        df = subprocess.run(
            ["df", "-kP", str(bcs_dest)], capture_output=True, text=True, check=True
        )
        lines = [ln for ln in df.stdout.splitlines() if ln.strip()]
        availablespace = int(lines[-1].split()[3])
        if availablespace < lowspace:
            stop_timestamp = int(time.time())
            print(
                f"\nLOW AVAILABLE SPACE on {bcs_dest} ({availablespace}k < {lowspace}k)\n"
                "Either free-up space, or swap out the storage device,\n"
                "or enter a new destination path here.\n"
                "Press enter when ready\n"
            )
            entered = input().strip()
            print()
            if entered:
                need_dest_accounting = True
                bcs_dest = Path(entered)
                state.bcs_dest = str(bcs_dest)
                persistence.save(datafile, state)
        else:
            if need_dest_accounting:
                du = subprocess.run(
                    ["du", "-c", "--apparent-size", oldpath],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                last = du.stdout.strip().splitlines()[-1].split()[0]
                state.dest_size_running += int(last)
                resume_ts = int(time.time())
                state.start_timestamp_running += resume_ts - stop_timestamp
                state.incremental_timestamp_running += resume_ts - stop_timestamp
                persistence.save(datafile, state)
            break

    return bcs_dest
