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
        run_check(["pigz", "-9c"], stdin=inf, stdout=outf)


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
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    use_append = append and archive_path.exists() and archive_path.stat().st_size > 0
    args: List[str] = ["tar", "--format=posix"]
    if use_append:
        args += ["-r"] + (["-v"] if verbose else []) + ["-f", str(archive_path), "-C", str(cwd)]
    else:
        args += ["-c"] + (["-v"] if verbose else []) + ["-f", str(archive_path), "-C", str(cwd)]
    args += paths_relative_to_cwd
    run_check(args)


def tar_create_multivolume_single_member(
    member_abs: Path,
    out_first: Path,
    slice_kb: int,
    tardir: Path,
    new_volume_script: Path,
    volno_file: Path,
    verbose: bool,
    env: dict | None = None,
) -> None:
    """Inner tar -cM over a single file (Tier 3)."""
    tardir.mkdir(parents=True, exist_ok=True)
    parent = member_abs.parent
    name = member_abs.name
    args = ["tar"]
    if verbose:
        args += ["-cpMv"]
    else:
        args += ["-cpM"]
    args += [
        "--format=posix",
        "--new-volume-script",
        str(new_volume_script),
        "-L",
        str(slice_kb),
        "--volno-file",
        str(volno_file),
        "-f",
        str(out_first),
        "-C",
        str(parent),
        name,
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
    """Extract one GNU multi-volume group from decoded plain-tar slice files."""
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
            "--format",
            "posix",
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
