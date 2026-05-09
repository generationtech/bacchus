"""Restore tmpfs sizing: peak concurrent size when decrypt and decompress share one directory."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bacchus import extern
from bacchus.pipeline import du_sk_apparent


def chunk_member_name(path: Path, basename: str) -> str:
    m = re.match(rf"^({re.escape(basename)}\.\d{{6}}\.tar)", path.name)
    if not m:
        raise ValueError(f"Not a chunked archive file: {path.name}")
    return m.group(1)


def _artifact_path(src_dir: Path, member: str, compress: bool, password: str) -> Path:
    p = src_dir / member
    if compress:
        p = Path(str(p) + ".gz")
    if password:
        p = Path(str(p) + ".gpg")
    return p


def gzip_uncompressed_bytes(path: Path) -> int:
    """Uncompressed size from ``gzip -l`` (handles large members; avoids ISIZE wraparound)."""
    r = subprocess.run(["gzip", "-l", str(path)], capture_output=True, text=True, check=True)
    for line in reversed(r.stdout.strip().splitlines()):
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[1])
    raise ValueError(f"Could not parse gzip -l output for {path}:\n{r.stdout}")


def _bytes_to_kb_ceil(n: int) -> int:
    return (n + 1023) // 1024


def restore_intermediate_peak_kb(
    artifact: Path,
    member: str,
    scratch: Path,
    *,
    compress: bool,
    password: str,
) -> int:
    """
    Peak KiB on a single filesystem while mirroring ``process_volume_restore`` intermediates.

    When compress and encrypt: decrypted ``.gz`` and final ``.tar`` may both exist during pigz.
    """
    scratch.mkdir(parents=True, exist_ok=True)

    if compress and password:
        gz_path = scratch / f"{member}.gz"
        extern.gpg_decrypt(password, artifact, gz_path)
        gz_kb = du_sk_apparent(gz_path)
        uncomp_kb = _bytes_to_kb_ceil(gzip_uncompressed_bytes(gz_path))
        gz_path.unlink(missing_ok=True)
        return gz_kb + uncomp_kb

    if compress and not password:
        gz_kb = du_sk_apparent(artifact)
        uncomp_kb = _bytes_to_kb_ceil(gzip_uncompressed_bytes(artifact))
        return gz_kb + uncomp_kb

    if password and not compress:
        plain = scratch / member
        extern.gpg_decrypt(password, artifact, plain)
        peak_kb = du_sk_apparent(plain)
        plain.unlink(missing_ok=True)
        return peak_kb

    raise ValueError("restore_intermediate_peak_kb expects compress or password")


def max_restore_peak_kb(
    chunk_paths: list[Path],
    basename: str,
    src_dir: Path,
    *,
    compress: bool,
    password: str,
    scratch: Path,
) -> int:
    """Maximum intermediate peak over chunks (same ordering as restore)."""
    max_kb = 0
    for p in chunk_paths:
        member = chunk_member_name(p, basename)
        artifact = _artifact_path(src_dir, member, compress, password)
        if not artifact.is_file():
            raise FileNotFoundError(f"Missing chunk artifact for sizing: {artifact}")
        peak = restore_intermediate_peak_kb(artifact, member, scratch, compress=compress, password=password)
        if peak > max_kb:
            max_kb = peak
    return max_kb


def restore_ramdisk_size_bytes(peak_kb: int) -> int:
    """tmpfs ``size=`` bytes: peak intermediates plus 1% slack (minimum ~1 MiB peak)."""
    peak_kb = max(peak_kb, 1024)
    base = peak_kb * 1024
    return base + base // 100
