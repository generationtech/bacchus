"""Per-chunk compress+encrypt and decrypt+decompress (Process_Volume port)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Tuple

from bacchus import extern


def du_sk_apparent(path: Path) -> int:
    r = subprocess.run(
        ["du", "-sk", "--apparent-size", str(path)], capture_output=True, text=True, check=True
    )
    return int(r.stdout.split()[0])


def ship_raw_tar(
    raw_tar: Path,
    dest_dir: Path,
    archive_member_name: str,
    *,
    compress: bool,
    password: str,
    compressdir: Path,
) -> Path:
    """
    Match bacchus-backup-new-volume.sh: pigz then gpg into dest_dir.
    archive_member_name is e.g. ``backupfile.tar`` or ``backupfile.000001.tar`` (no .gz/.gpg).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    compressdir.mkdir(parents=True, exist_ok=True)
    current = raw_tar

    if compress:
        gz_work = compressdir / f"{archive_member_name}.gz"
        extern.pigz_compress(current, gz_work)
        current.unlink(missing_ok=True)
        current = gz_work

    if password:
        if compress:
            final = dest_dir / f"{archive_member_name}.gz.gpg"
        else:
            final = dest_dir / f"{archive_member_name}.gpg"
        extern.gpg_encrypt(password, current, final)
        current.unlink(missing_ok=True)
        return final

    if compress:
        final = dest_dir / f"{archive_member_name}.gz"
        if final.exists():
            final.unlink()
        current.replace(final)
        return final

    final = dest_dir / archive_member_name
    if current.resolve() == final.resolve():
        return final
    if final.exists():
        final.unlink()
    current.replace(final)
    return final


def process_volume_restore(
    bcs_source: Path,
    filename: str,
    decryptdir: Path,
    compressdir: Path,
    *,
    compress: bool,
    password: str,
) -> Tuple[Path, int, int]:
    """
    Port of Process_Volume. ``filename`` is e.g. ``backupfile.tar`` or ``backupfile.tar-2`` (no .gz).
    Returns (plain_tar_path, source_actual_size_kb, dest_actual_size_kb).
    """
    source_actual_size = 0
    source = bcs_source / filename

    if compress:
        source = Path(str(source) + ".gz")

    if password:
        if compress:
            gpg_in = Path(str(source) + ".gpg")
        else:
            gpg_in = Path(str(bcs_source / filename) + ".gpg")
        if not gpg_in.is_file():
            gpg_in = bcs_source / (filename + ".gpg")
        if compress and not gpg_in.is_file():
            gpg_in = bcs_source / (filename + ".gz.gpg")
        decryptdir.mkdir(parents=True, exist_ok=True)
        if compress:
            decrypted = decryptdir / f"{filename}.gz"
        else:
            decrypted = decryptdir / filename
        source_actual_size = du_sk_apparent(gpg_in)
        extern.gpg_decrypt(password, gpg_in, decrypted)
        source = decrypted

    if compress:
        out_tar = compressdir / filename
        compressdir.mkdir(parents=True, exist_ok=True)
        if source_actual_size == 0:
            source_actual_size = du_sk_apparent(source)
        extern.pigz_decompress(source, out_tar)
        if password:
            source.unlink(missing_ok=True)
        source = out_tar

    if source_actual_size == 0:
        source_actual_size = du_sk_apparent(source)

    dest_actual_size = du_sk_apparent(source)
    return source, source_actual_size, dest_actual_size


def detect_compress_encrypt_from_artifacts(bcs_source: Path, basename: str) -> Tuple[bool, bool]:
    import glob

    matches = sorted(glob.glob(str(bcs_source / f"{basename}.tar*")))
    if not matches:
        return False, False
    tail = matches[-1]
    return ".gz" in tail, ".gpg" in tail
