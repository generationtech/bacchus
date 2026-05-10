"""
End-to-end production test: random tree, chunked backup (Tier-3), restore, byte verify.

Designed to run from pytest or ``python -m tests.integration.run_e2e``.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Repo root: tests/integration/_e2e_impl.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"

# Default file count (~20% large, rest small) — matches plan’s ~5 + ~20 layout at 500 MiB.
E2E_DEFAULT_N_FILES = 25


def _repo_pythonpath() -> dict[str, str]:
    env = os.environ.copy()
    p = str(_SRC)
    env["PYTHONPATH"] = p + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _bacchus_imports():
    try:
        from bacchus.classify import TarSegmentKind, classify_tar_segment
        from bacchus.pipeline import process_volume_restore
    except ImportError:
        sys.path.insert(0, str(_SRC))
        from bacchus.classify import TarSegmentKind, classify_tar_segment
        from bacchus.pipeline import process_volume_restore

    return TarSegmentKind, classify_tar_segment, process_volume_restore


def _rand_name(rng: random.Random, min_len: int = 4, max_len: int = 10) -> str:
    n = rng.randint(min_len, max_len)
    alphabet = string.ascii_letters + string.digits
    return "".join(rng.choice(alphabet) for _ in range(n))


def _allocate_file_sizes(
    rng: random.Random,
    total_bytes: int,
    n_files: int,
    large_file_ratio: float,
    absolute_max_bytes: int,
) -> list[int]:
    """
    Return ``n_files`` sizes summing to ``total_bytes``.
    At least ``round(n_files * ratio)`` files are strictly larger than ``absolute_max_bytes``.
    """
    large_n = max(1, min(int(round(n_files * large_file_ratio)), n_files - 1))
    small_n = n_files - large_n
    min_large = int(absolute_max_bytes * 1.1) + 1
    max_large = int(absolute_max_bytes * 2)
    min_small = 4096

    if large_n * min_large + small_n * min_small > total_bytes:
        raise ValueError(
            f"total_bytes={total_bytes} too small for n_files={n_files}, "
            f"absolute_max_bytes={absolute_max_bytes} (need {large_n} files > {min_large} B)"
        )

    sizes: list[int] = []
    rem = total_bytes
    for i in range(large_n):
        others_large = large_n - i - 1
        reserve_small = small_n * min_small
        lo = min_large
        hi = min(
            max_large,
            rem - others_large * min_large - reserve_small,
        )
        if hi < lo:
            raise ValueError("Could not allocate large file sizes within budget")
        sz = rng.randint(lo, hi)
        sizes.append(sz)
        rem -= sz

    if rem < small_n * min_small:
        raise ValueError("Insufficient remainder for small files after large allocation")
    cap_small = max(min_small, absolute_max_bytes - 1)
    rem_small = rem
    for j in range(small_n - 1):
        slots_after = small_n - j - 1
        lo = max(min_small, rem_small - slots_after * cap_small)
        hi = min(cap_small, rem_small - slots_after * min_small)
        if lo > hi:
            raise ValueError(
                f"Could not allocate small file #{j}: rem={rem_small}, "
                f"slots_after={slots_after}, lo={lo}, hi={hi}"
            )
        sz = rng.randint(lo, hi)
        sizes.append(sz)
        rem_small -= sz
    last_small = rem_small
    if not (min_small <= last_small <= cap_small):
        raise ValueError(
            f"Final small-file size {last_small} out of range [{min_small}, {cap_small}]; "
            "tune total_bytes / n_files / absolute_max."
        )
    sizes.append(last_small)

    assert sum(sizes) == total_bytes
    lg = sum(1 for s in sizes if s > absolute_max_bytes)
    assert lg >= large_n
    return sizes


def _random_tree(root: Path, rng: random.Random, sizes: list[int]) -> None:
    """Create files under ``root``; random nested subdirs; ~50%% binary vs text."""
    root.mkdir(parents=True, exist_ok=True)
    for sz in sizes:
        depth = rng.randint(1, 4)
        cur = root
        for _ in range(depth - 1):
            nd = cur / _rand_name(rng)
            nd.mkdir(parents=True, exist_ok=True)
            cur = nd
        name = _rand_name(rng) + (".bin" if rng.random() < 0.5 else ".txt")
        path = cur / name
        binary = rng.random() < 0.5
        _write_file(path, sz, rng, binary)


def _write_file(path: Path, size: int, rng: random.Random, binary: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk = 1024 * 1024
    left = size
    with open(path, "wb") as f:
        while left > 0:
            n = min(chunk, left)
            if binary:
                f.write(os.urandom(n))
            else:
                buf = bytearray()
                while len(buf) < n:
                    buf.extend((rng.choice("abcdef ") * rng.randint(2, 20) + "\n").encode())
                f.write(buf[:n])
            left -= n


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


EntryKind = Literal["file", "dir", "symlink"]

# rel_path -> (kind, size, mode, mtime_int, sha256_hex | symlink_target | "" for dirs)
TreeEntry = tuple[EntryKind, int, int, int, str]


def _scan_tree(root: Path) -> dict[str, TreeEntry]:
    """Map relative POSIX path -> (kind, size, mode, mtime, payload)."""
    root = root.resolve()
    out: dict[str, TreeEntry] = {}
    for p in sorted(root.rglob("*"), key=lambda x: str(x)):
        rel = p.relative_to(root).as_posix()
        st = p.lstat()
        mode = st.st_mode & 0o7777
        if p.is_symlink():
            out[rel] = ("symlink", 0, mode, 0, os.readlink(p))
        elif p.is_dir():
            out[rel] = ("dir", 0, mode, 0, "")
        elif p.is_file():
            stf = p.stat()
            mtime = int(stf.st_mtime)
            out[rel] = ("file", stf.st_size, mode, mtime, _hash_file(p))
        else:
            raise AssertionError(f"unsupported tree entry {p} (not file/dir/symlink)")
    return out


def _count_regular_files(root: Path) -> int:
    """Like ``find -type f``: regular files only (exclude symlink paths)."""
    return sum(1 for p in root.rglob("*") if not p.is_symlink() and p.is_file())


def _verify_rsync_mirror_checksum(src_root: Path, dst_root: Path) -> None:
    """
    Dry-run rsync with checksums; empty itemized output means no transfers needed.

    Skips non-regular entries rsync would skip (FIFO/socket/device); this harness does
    not create them by default.
    """
    rsync_bin = shutil.which("rsync")
    if rsync_bin is None:
        print(
            "E2E: rsync not found; skipping checksum mirror verification.",
            file=sys.stderr,
        )
        return
    src = src_root.resolve()
    dst = dst_root.resolve()
    r = subprocess.run(
        [
            rsync_bin,
            "-rlcin",
            "--checksum",
            "--omit-dir-times",
            "--delete",
            f"{src}/",
            f"{dst}/",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"rsync checksum dry-run failed ({r.returncode})\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if out or err:
        raise AssertionError(
            "rsync checksum dry-run reported differences or unexpected output.\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


def verify_match(src_root: Path, dst_root: Path, max_report: int = 20) -> None:
    a = _scan_tree(src_root)
    b = _scan_tree(dst_root)
    keys_a = set(a)
    keys_b = set(b)
    missing = sorted(keys_a - keys_b)
    extra = sorted(keys_b - keys_a)
    diffs: list[str] = []
    for k in sorted(keys_a & keys_b):
        if a[k] != b[k]:
            diffs.append(f"{k}: src={a[k]} dst={b[k]}")
    if missing or extra or diffs:
        msg: list[str] = [
            f"Source: {src_root.resolve()}",
            f"Restored: {dst_root.resolve()}",
        ]
        if missing:
            msg.append(f"missing in restore ({len(missing)}): {missing[:max_report]}")
        if extra:
            msg.append(f"extra in restore ({len(extra)}): {extra[:max_report]}")
        if diffs:
            msg.append(f"content/meta diffs ({len(diffs)}):")
            msg.extend(diffs[:max_report])
        raise AssertionError("\n".join(msg))


def _list_chunk_artifacts(dest: Path, basename: str) -> list[Path]:
    rx = re.compile(rf"^{re.escape(basename)}\.\d{{6}}\.tar(?:\.gz)?(?:\.gpg)?$")
    return sorted(p for p in dest.iterdir() if p.is_file() and rx.match(p.name))


def assert_tier3_mv_continuation_present(
    dest: Path,
    basename: str,
    workdir: Path,
    compress: bool,
    password: str,
) -> None:
    """At least one decoded chunk must be a GNU inner multi-volume continuation (typeflag ``M``)."""
    TarSegmentKind, classify_tar_segment, process_volume_restore = _bacchus_imports()

    rx_member = re.compile(rf"^({re.escape(basename)}\.\d{{6}}\.tar)")
    tmp = workdir / "_e2e_decode"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    tmp_resolved = tmp.resolve()

    found_mv = False
    for art in _list_chunk_artifacts(dest, basename):
        m = rx_member.match(art.name)
        if not m:
            continue
        member = m.group(1)
        plain, _, _ = process_volume_restore(
            dest,
            member,
            tmp,
            tmp,
            compress=compress,
            password=password,
        )
        kind = classify_tar_segment(plain)
        # ``plain`` may be the real artifact under ``dest``; only remove intermediates under ``tmp``.
        try:
            plain.resolve().relative_to(tmp_resolved)
        except ValueError:
            pass
        else:
            plain.unlink(missing_ok=True)
        if kind in (TarSegmentKind.MV_MIDDLE, TarSegmentKind.MV_END):
            found_mv = True
            break
    shutil.rmtree(tmp, ignore_errors=True)
    if not found_mv:
        raise AssertionError(
            "Tier-3 check failed: no decoded chunk had GNU multivolume continuation header (typeflag 'M'). "
            "Increase total_bytes / lower absolute-max-size / lower mini-slice-size."
        )


def _run_cmd(cmd: list[str], env: dict[str, str]) -> None:
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"Command failed ({r.returncode}): {' '.join(cmd)}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


def _pw_cli_args(password: str) -> list[str]:
    if password:
        return ["-p", password, "-u", "off"]
    return ["-u", "off"]


@dataclass
class E2EConfig:
    total_bytes: int = 500 * 1024 * 1024
    workdir: Path | None = None
    volumesize_kb: int = 10_000
    absolute_max_kb: int = 40_000
    mini_slice_kb: int = 10_000
    large_file_ratio: float = 0.20
    basename: str = "e2e"
    seed: int | None = None
    keep_on_success: bool = False
    compress: bool = False
    password: str = ""

    def resolved_workdir(self) -> Path:
        if self.workdir is not None:
            return self.workdir.resolve()
        return Path(tempfile.gettempdir()) / f"bacchus-e2e-{os.getpid()}-{time.time_ns()}"


def run_e2e(cfg: E2EConfig) -> int:
    workdir = cfg.resolved_workdir()
    src_root = workdir / "source"
    dest_root = workdir / "dest"
    restored_root = workdir / "restored"
    tar_dir = workdir / "tar"
    comp_dir = workdir / "comp"
    dec_dir = workdir / "dec"
    env = _repo_pythonpath()
    exe = sys.executable

    rng = random.Random(cfg.seed if cfg.seed is not None else time.time_ns() % (2**32))

    try:
        workdir.mkdir(parents=True, exist_ok=True)
        abs_b = cfg.absolute_max_kb * 1024
        sizes = _allocate_file_sizes(
            rng, cfg.total_bytes, E2E_DEFAULT_N_FILES, cfg.large_file_ratio, abs_b
        )
        _random_tree(src_root, rng, sizes)

        z = "on" if cfg.compress else "off"
        pw_args = _pw_cli_args(cfg.password)

        backup_cmd = [
            exe,
            "-m",
            "bacchus",
            "backup",
            "-s",
            str(src_root),
            "-d",
            str(dest_root),
            "-b",
            cfg.basename,
            "-v",
            str(cfg.volumesize_kb),
            "--absolute-max-size",
            str(cfg.absolute_max_kb),
            "--mini-slice-size",
            str(cfg.mini_slice_kb),
            "--archive-mode",
            "chunked",
            "-z",
            z,
            "-r",
            "off",
            "-t",
            str(tar_dir),
            "-c",
            str(comp_dir),
            "-C",
            "off",
            "-E",
            "off",
            "-S",
            "off",
            "-W",
            "off",
            "-X",
            "off",
            *pw_args,
        ]
        _run_cmd(backup_cmd, env)

        assert_tier3_mv_continuation_present(
            dest_root,
            cfg.basename,
            workdir,
            compress=cfg.compress,
            password=cfg.password,
        )

        restore_cmd = [
            exe,
            "-m",
            "bacchus",
            "restore",
            "-s",
            str(dest_root),
            "-d",
            str(restored_root),
            "-b",
            cfg.basename,
            "--archive-mode",
            "chunked",
            "-z",
            z,
            "-r",
            "off",
            "-e",
            str(dec_dir),
            "-c",
            str(comp_dir),
            "-C",
            "off",
            "-E",
            "off",
            "-S",
            "off",
            "-W",
            "off",
            "-X",
            "off",
            *pw_args,
        ]
        _run_cmd(restore_cmd, env)

        verify_src = restored_root / src_root.name
        verify_match(src_root, verify_src)

        n_reg_src = _count_regular_files(src_root)
        n_reg_dst = _count_regular_files(verify_src)
        if n_reg_src != n_reg_dst:
            raise AssertionError(
                f"regular file count mismatch (find -type f semantics): "
                f"source={n_reg_src} restored={n_reg_dst}"
            )

        _verify_rsync_mirror_checksum(src_root, verify_src)

        n_files = sum(1 for p in src_root.rglob("*") if p.is_file())
        n_dirs = sum(1 for p in src_root.rglob("*") if p.is_dir())
        print(
            f"E2E OK: {cfg.total_bytes} bytes, {n_files} files, {n_dirs} dirs; "
            f"basename={cfg.basename}; workdir was {workdir}"
        )
    except Exception as e:
        print(f"E2E FAILED: {e}", file=sys.stderr)
        print(f"Source tree:    {src_root}", file=sys.stderr)
        print(f"Restored tree:  {restored_root / src_root.name}", file=sys.stderr)
        print(f"Backup chunks:  {dest_root}", file=sys.stderr)
        print(f"Workdir:        {workdir}", file=sys.stderr)
        return 1
    else:
        if not cfg.keep_on_success:
            shutil.rmtree(workdir, ignore_errors=True)
        return 0
