"""Restore tmpfs sizing: peak concurrent size when decrypt and decompress share one directory."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from bacchus import extern
from bacchus.pipeline import du_sk_apparent


def chunk_member_name(path: Path, basename: str) -> str:
    m = re.match(rf"^({re.escape(basename)}\.\d{{6}}\.tar)", path.name)
    if not m:
        raise ValueError(f"Not a chunked archive file: {path.name}")
    return m.group(1)


def largest_chunk_artifact_across_roots(
    roots: list[Path],
    basename: str,
    *,
    compress: bool,
    password: str,
) -> tuple[Path, str]:
    """
    Largest on-disk chunk artifact (by ``st_size``) among all directories in ``roots``.

    Used for quick probes (e.g. ramdisk smoke decode). **Tmpfs sizing** must use
    :func:`worst_restore_intermediate_peak_kb_across_roots`, because a *smaller* ciphertext can
    decrypt to a *larger* tar than a bigger file on disk (compression ratio varies).
    """
    rx = re.compile(rf"^{re.escape(basename)}\.(\d{{6}})\.tar(?:\.gz)?(?:\.gpg)?$")
    best_art: Path | None = None
    best_member: str | None = None
    best_sz = -1
    for root in roots:
        root_r = root.resolve()
        try:
            for p in root_r.iterdir():
                if not p.is_file():
                    continue
                m = rx.match(p.name)
                if not m:
                    continue
                member = f"{basename}.{m.group(1)}.tar"
                artifact = _artifact_path(root_r, member, compress, password)
                if not artifact.is_file():
                    continue
                sz = artifact.stat().st_size
                if sz > best_sz or (sz == best_sz and str(artifact) < str(best_art or "")):
                    best_art, best_member, best_sz = artifact, member, sz
        except OSError:
            continue
    if best_art is None or best_member is None:
        raise FileNotFoundError(f"No {basename}.NNNNNN.tar* chunks under {roots!r}")
    return best_art, best_member


def largest_chunk_artifact(
    chunk_paths: list[Path],
    basename: str,
    src_dir: Path,
    *,
    compress: bool,
    password: str,
) -> tuple[Path, str]:
    """
    Chunk artifact with greatest on-disk ``st_size`` among ``chunk_paths``.

    Tie-break: lexicographically smallest path string for determinism.
    """
    best_art: Path | None = None
    best_member: str | None = None
    best_sz = -1
    for p in chunk_paths:
        member = chunk_member_name(p, basename)
        artifact = _artifact_path(src_dir, member, compress, password)
        if not artifact.is_file():
            raise FileNotFoundError(f"Missing chunk artifact for sizing: {artifact}")
        sz = artifact.stat().st_size
        if best_art is None:
            best_art, best_member, best_sz = artifact, member, sz
            continue
        if sz > best_sz or (sz == best_sz and str(artifact) < str(best_art)):
            best_art, best_member, best_sz = artifact, member, sz
    assert best_art is not None and best_member is not None
    return best_art, best_member


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


def worst_restore_intermediate_peak_kb_across_roots(
    roots: list[Path],
    basename: str,
    *,
    compress: bool,
    password: str,
    scratch_parent: Path,
) -> int:
    """
    Conservative tmpfs peak among **every** chunk artifact under ``roots``.

    Per chunk, :func:`restore_intermediate_peak_kb` matches **one** decode pass (``.gz`` +
    growing ``.tar`` during pigz). During **inner** ``tar -M`` restore, vol1's plain ``.tar`` can
    remain on the same tmpfs while the **next** slice decrypts/decompresses, so peak can reach
    ``pk + max_uncompressed_slice`` across chunks. We return ``worst_pk + worst_slack`` where
    ``worst_slack`` is the largest gzip-uncompressed slice (or largest decrypted plain when not
    compressed).
    """
    if not compress and not password:
        raise ValueError("worst_restore_intermediate_peak_kb_across_roots needs compress or password")

    rx = re.compile(rf"^{re.escape(basename)}\.(\d{{6}})\.tar(?:\.gz)?(?:\.gpg)?$")
    scratch_parent.mkdir(parents=True, exist_ok=True)
    worst_pk = 0
    worst_slack = 0
    n = 0
    for root in roots:
        root_r = root.resolve()
        try:
            for p in root_r.iterdir():
                if not p.is_file():
                    continue
                m = rx.match(p.name)
                if not m:
                    continue
                member = f"{basename}.{m.group(1)}.tar"
                artifact = _artifact_path(root_r, member, compress, password)
                if not artifact.is_file():
                    continue
                sub = Path(tempfile.mkdtemp(prefix="bacchus-wpeak-", dir=str(scratch_parent)))
                try:
                    if compress and password:
                        gz_path = sub / f"{member}.gz"
                        extern.gpg_decrypt(password, artifact, gz_path)
                        gz_kb = du_sk_apparent(gz_path)
                        uncomp_kb = _bytes_to_kb_ceil(gzip_uncompressed_bytes(gz_path))
                        gz_path.unlink(missing_ok=True)
                        worst_pk = max(worst_pk, gz_kb + uncomp_kb)
                        worst_slack = max(worst_slack, uncomp_kb)
                    elif compress and not password:
                        gz_kb = du_sk_apparent(artifact)
                        uncomp_kb = _bytes_to_kb_ceil(gzip_uncompressed_bytes(artifact))
                        worst_pk = max(worst_pk, gz_kb + uncomp_kb)
                        worst_slack = max(worst_slack, uncomp_kb)
                    else:
                        plain = sub / member
                        extern.gpg_decrypt(password, artifact, plain)
                        pk = du_sk_apparent(plain)
                        plain.unlink(missing_ok=True)
                        worst_pk = max(worst_pk, pk)
                        worst_slack = max(worst_slack, pk)
                    n += 1
                finally:
                    shutil.rmtree(sub, ignore_errors=True)
        except OSError:
            continue
    if n == 0:
        raise FileNotFoundError(f"No {basename}.NNNNNN.tar* chunks under {roots!r}")
    return worst_pk + worst_slack


def restore_ramdisk_size_bytes(peak_kb: int) -> int:
    """tmpfs ``size=`` bytes: peak intermediates plus small slack (minimum ~1 MiB peak)."""
    peak_kb = max(peak_kb, 1024)
    base = peak_kb * 1024
    return base + base // 20
