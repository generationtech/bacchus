"""tmpfs ramdisk mount/unmount (replaces cleanup.sh ramdisk portion)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


class Ramdisk:
    def __init__(self, mountpoint: Path, size_bytes: int):
        self.mountpoint = mountpoint
        self.size_bytes = size_bytes
        self._mounted = False

    def mount(self) -> None:
        self.mountpoint.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["mount", "-t", "tmpfs", "-o", f"size={self.size_bytes}", "tmpfs", str(self.mountpoint)],
            check=True,
        )
        self._mounted = True

    def remount_resize(self, size_bytes: int) -> None:
        """Grow tmpfs in place (Linux ``mount -o remount,size=…``). No-op if already large enough."""
        if not self._mounted:
            raise RuntimeError("Ramdisk.remount_resize requires an active mount")
        if size_bytes <= self.size_bytes:
            return
        subprocess.run(
            ["mount", "-o", f"remount,size={size_bytes}", str(self.mountpoint)],
            check=True,
        )
        self.size_bytes = size_bytes

    def umount(self) -> None:
        if not self._mounted:
            return
        mp = str(self.mountpoint)
        # findmnt check like bash
        r = subprocess.run(["findmnt", mp, "-n", "-o", "TARGET"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == mp:
            while True:
                u = subprocess.run(["umount", mp])
                if u.returncode == 0:
                    break
                time.sleep(2)
                print("Unmount ramdisk failed, retrying")
        self._mounted = False


def ramdisk_size_bytes(
    volumesize_kb: int,
    compress: bool,
    encrypt: bool,
    *,
    max_chunk_kb: int | None = None,
) -> int:
    """
    tmpfs size for tar + compression + encryption scratch when ``-r on``.

    ``max_chunk_kb`` is the largest raw chunk (KiB) we may hold on tmpfs at once: at least
    ``volumesize_kb``, and typically ``max(absolute_max, mini_slice)`` from chunked backup so a
    single tier-2 or tier-3 slice fits.

    Peak footprint (same filesystem) while shipping one chunk:

    - compress: raw ``.tar`` and ``.pigz`` output ``.gz`` can both exist briefly.
    - encrypt (no compress): raw ``.tar`` and ``.gpg``.
    - both: ``.gz`` then ``.gpg``; bound by roughly three slab-sized artifacts in the worst case.

    Slack: 1% of the dominant chunk size (same as legacy single-slab rule, applied to ``chunk_kb``).
    """
    chunk_kb = max(volumesize_kb, max_chunk_kb or 0)
    if not compress and not encrypt:
        return chunk_kb * 1024 + ((chunk_kb * 1024) // 100)
    if compress and encrypt:
        ramdisk_kb = chunk_kb * 3
    else:
        ramdisk_kb = chunk_kb * 2
    return (ramdisk_kb * 1024) + ((chunk_kb * 1024) // 100)


def cleanup_print() -> None:
    print("\nOperation shutting down - cleanup process started\n")


def remove_tmp_prefix(tmp_prefix: Path) -> None:
    """Remove all paths tmp_prefix* if tmp_prefix looks safe."""
    s = str(tmp_prefix)
    if "tmp" not in s and "temp" not in s.lower():
        return
    parent = tmp_prefix.parent
    stem = tmp_prefix.name
    if not parent.is_dir():
        return
    for p in parent.iterdir():
        if p.name.startswith(stem):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)


def sync_filesystem() -> None:
    subprocess.run(["sync"], check=False)
