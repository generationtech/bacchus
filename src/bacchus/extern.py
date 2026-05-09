"""Subprocess wrappers for tar, pigz, gpg."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import List, Sequence


def run_check(cmd: Sequence[str], env: dict | None = None, **kwargs) -> subprocess.CompletedProcess:
    if env is None:
        return subprocess.run(cmd, check=True, **kwargs)
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(cmd, check=True, env=merged, **kwargs)


def _paths_to_null_delimited_bytes(paths_relative_to_cwd: List[str]) -> bytes:
    """NUL-separated member names for GNU ``tar --null -T`` (safe for newlines in paths)."""
    if not paths_relative_to_cwd:
        return b""
    return b"\0".join(os.fsencode(p) for p in paths_relative_to_cwd) + b"\0"


def _run_tar_with_files_from(cmd_prefix: List[str], paths_relative_to_cwd: List[str], list_dir: Path) -> None:
    """
    Run tar with member paths read from a temp file (avoids ``ARG_MAX`` / argv limits).

    ``cmd_prefix`` must end with ``--null`` and ``-T``; the list file path is appended.
    """
    if not paths_relative_to_cwd:
        return
    list_dir.mkdir(parents=True, exist_ok=True)
    payload = _paths_to_null_delimited_bytes(paths_relative_to_cwd)
    list_path = list_dir / f".bacchus-tar-list-{os.getpid()}-{os.urandom(4).hex()}.lst"
    try:
        list_path.write_bytes(payload)
        run_check(cmd_prefix + [str(list_path)])
    finally:
        list_path.unlink(missing_ok=True)


def tar_multivolume_create(
    source_dir: Path,
    tar_dir: Path,
    basename: str,
    volumesize_kb: int,
    volno_file: Path,
    new_volume_script: Path,
    verbose: bool,
    env: dict | None = None,
) -> None:
    tar_dir.mkdir(parents=True, exist_ok=True)
    first = tar_dir / f"{basename}.tar"
    args = ["tar"]
    if verbose:
        args += ["-cpMv"]
    else:
        args += ["-cpM"]
    args += [
        "--format=posix",
        "--sort=name",
        "--new-volume-script",
        str(new_volume_script),
        "-L",
        str(volumesize_kb),
        "--volno-file",
        str(volno_file),
        "-f",
        str(first),
        str(source_dir),
    ]
    run_check(args, env=env)


def tar_multivolume_extract(
    first_tar_path: Path,
    dest_dir: Path,
    volno_file: Path,
    new_volume_script: Path,
    verbose: bool,
    env: dict | None = None,
) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    args = ["tar"]
    if verbose:
        args += ["-xpMv"]
    else:
        args += ["-xpM"]
    args += [
        "--format",
        "posix",
        "--new-volume-script",
        str(new_volume_script),
        "--volno-file",
        str(volno_file),
        "-f",
        str(first_tar_path),
        "--directory",
        str(dest_dir),
    ]
    run_check(args, env=env)


def pigz_compress(src: Path, dst_gz: Path) -> None:
    dst_gz.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as inf, open(dst_gz, "wb") as outf:
        r = subprocess.run(["pigz", "-9c"], stdin=inf, stdout=outf, stderr=subprocess.PIPE)
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", errors="replace").strip()
        msg = f"pigz failed with exit status {r.returncode}"
        if err:
            msg += f": {err}"
        if "No space left on device" in err or r.returncode == 28:
            msg += (
                " (no space on the filesystem receiving the ``.gz`` or on tmpfs holding the raw "
                "``.tar`` when ``-r on``. Free ``-d`` and RAM/swap for tmpfs; try ``-r off`` or a "
                "smaller ``-v``.)"
            )
        raise RuntimeError(msg)


def pigz_decompress(src_gz: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src_gz, "rb") as inf, open(dst, "wb") as outf:
        run_check(["pigz", "-9cd"], stdin=inf, stdout=outf)


def gpg_encrypt(password: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            "gpg",
            "-qc",
            "--cipher-algo",
            "AES256",
            "--compress-algo",
            "none",
            "--batch",
            "--passphrase-fd",
            "0",
            "-o",
            str(dst),
            str(src),
        ],
        stdin=subprocess.PIPE,
    )
    proc.communicate(password.encode("utf-8"))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, "gpg")


def gpg_decrypt(password: str, src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            "gpg",
            "-qd",
            "--batch",
            "--cipher-algo",
            "AES256",
            "--compress-algo",
            "none",
            "--passphrase-fd",
            "0",
            "--no-mdc-warning",
            "-o",
            str(dst),
            str(src),
        ],
        stdin=subprocess.PIPE,
    )
    proc.communicate(password.encode("utf-8"))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, "gpg")


def tar_create_file_archive(
    paths_relative_to_cwd: List[str],
    archive_path: Path,
    cwd: Path,
    append: bool,
    verbose: bool,
) -> None:
    """Create or append ustar members; paths are relative to cwd."""
    if not paths_relative_to_cwd:
        return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    use_append = append and archive_path.exists() and archive_path.stat().st_size > 0
    verb: List[str] = ["-v"] if verbose else []
    if use_append:
        prefix: List[str] = (
            ["tar", "--format=posix", "-r"] + verb + ["-f", str(archive_path), "-C", str(cwd), "--null", "-T"]
        )
    else:
        prefix = ["tar", "--format=posix", "-c"] + verb + ["-f", str(archive_path), "-C", str(cwd), "--null", "-T"]
    _run_tar_with_files_from(prefix, paths_relative_to_cwd, archive_path.parent)


def tar_create_archive(
    paths_relative_to_cwd: List[str],
    archive_path: Path,
    cwd: Path,
    verbose: bool,
) -> None:
    """Create one archive in a single tar invocation from paths relative to cwd."""
    if not paths_relative_to_cwd:
        return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    prefix: List[str] = (
        ["tar", "--format=posix", "-c"] + (["-v"] if verbose else []) + ["-f", str(archive_path), "-C", str(cwd), "--null", "-T"]
    )
    _run_tar_with_files_from(prefix, paths_relative_to_cwd, archive_path.parent)


def tar_create_multivolume_single_member(
    cwd: Path,
    path_relative_to_cwd: str,
    out_first: Path,
    slice_kb: int,
    tardir: Path,
    new_volume_script: Path,
    volno_file: Path,
    verbose: bool,
    env: dict | None = None,
) -> None:
    """Inner ``tar -cM`` for one archive member, same ``-C``/relative path rules as ``tar_create_file_archive``."""
    tardir.mkdir(parents=True, exist_ok=True)
    args = ["tar"]
    if verbose:
        args += ["-cpMv"]
    else:
        args += ["-cpM"]
    args += [
        # Omit ``--format=posix`` so GNU multi-volume uses typeflag ``M`` continuations; POSIX
        # inner volumes classify as consecutive ``MV_START`` and break manifestless restore.
        "--new-volume-script",
        str(new_volume_script),
        "-L",
        str(slice_kb),
        "--volno-file",
        str(volno_file),
        "-f",
        str(out_first),
        "-C",
        str(cwd),
        path_relative_to_cwd,
    ]
    run_check(args, env=env)


def tar_extract_single(archive: Path, dest: Path, verbose: bool) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    args = ["tar"]
    if verbose:
        args += ["-xpv", "-f", str(archive), "-C", str(dest)]
    else:
        args += ["-xp", "-f", str(archive), "-C", str(dest)]
    run_check(args)


def _write_mv_nvs_script(script_path: Path, slice_paths: List[Path]) -> None:
    """GNU tar new-volume-script: echo path of next volume to TAR_FD when TAR_VOLUME >= 2."""
    paths_literal = json.dumps([str(p.resolve()) for p in slice_paths])
    body = f"""#!/usr/bin/env python3
import json, os, sys
paths = json.loads({repr(paths_literal)})
vol = int(os.environ.get("TAR_VOLUME", "0"))
fd = int(os.environ["TAR_FD"])
if 2 <= vol <= len(paths):
    p = paths[vol - 1].encode() + b"\\n"
    os.write(fd, p)
    sys.exit(0)
sys.exit(0)
"""
    script_path.write_text(body, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def tar_extract_multivolume_buffered(slices: List[Path], dest: Path, verbose: bool) -> None:
    """
    Extract one GNU multi-volume group from decoded plain-tar slice files.

    Must match :func:`tar_create_multivolume_single_member`: inner ``tar -cM`` omits ``--format=posix``
    so GNU ``M`` continuations apply; ``tar -xM`` here omits it too, otherwise volume offsets can fail
    with ``This volume is out of sequence``.
    """
    if not slices:
        raise ValueError("no slices")
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        volno = td_path / "volno"
        volno.write_text("1\n", encoding="utf-8")
        nvs = td_path / "nvs.py"
        _write_mv_nvs_script(nvs, slices)
        args = ["tar"]
        if verbose:
            args += ["-xpMv"]
        else:
            args += ["-xpM"]
        args += [
            "--new-volume-script",
            str(nvs),
            "--volno-file",
            str(volno),
            "-f",
            str(slices[0]),
            "-C",
            str(dest),
        ]
        run_check(args)
