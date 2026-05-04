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


def ramdisk_size_bytes(volumesize_kb: int, compress: bool, encrypt: bool) -> int:
    """Match bash: ramdisk_size = sum(volume) * 1024 + 1% of volume in bytes."""
    ramdisk_kb = 0
    if compress:
        ramdisk_kb += volumesize_kb
    if encrypt:
        ramdisk_kb += volumesize_kb
    return (ramdisk_kb * 1024) + ((volumesize_kb * 1024) // 100)


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
