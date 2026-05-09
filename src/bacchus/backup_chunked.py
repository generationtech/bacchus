"""Chunked backup: Tier 1/2 standalone tars + Tier 3 inner ``tar -cM`` for huge members."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bacchus import extern, persistence, ramdisk
from bacchus import stats as statsmod
from bacchus.config import BcsConfig
from bacchus.pipeline import du_sk_apparent, ship_raw_tar
from bacchus.walk import iter_files_from_ordered_paths, iter_source_paths_tar_order


def backup_tar_chdir(cfg: BcsConfig, source_root: Path) -> Path:
    """GNU tar ``-C`` directory for chunked backup (constant for all members under ``source_root``)."""
    top = (cfg.archive_top_dir or "").strip()
    if top or cfg.archive_path_scope == "source":
        return source_root
    return source_root.parent


def member_rel_for_backup(cfg: BcsConfig, source_root: Path, path: Path) -> str:
    """
    Member path relative to :func:`backup_tar_chdir`.

    Default: historical layout — path relative to ``source_root.parent`` (includes source basename).

    ``archive_path_scope`` source: relative to ``source_root`` only.

    ``archive_top_dir``: ``{name}/{relative_to_source}`` with chdir ``source_root``.
    """
    parent = source_root.parent
    rel_to_src = path.relative_to(source_root).as_posix()
    rel_to_parent = path.relative_to(parent).as_posix()
    top = (cfg.archive_top_dir or "").strip()
    if top:
        return f"{top}/{rel_to_src}"
    if cfg.archive_path_scope == "source":
        return rel_to_src
    return rel_to_parent


def _predict_after_add(current_raw_bytes: int, file_size: int) -> int:
    return current_raw_bytes + 512 + ((file_size + 511) // 512) * 512


def _mini_tar_volume(name: str) -> int | None:
    """Map ``mini.tar`` / ``mini.tar-N`` basename to a monotonic volume index (1-based)."""
    if name == "mini.tar":
        return 1
    prefix = "mini.tar-"
    if name.startswith(prefix) and name[len(prefix) :].isdigit():
        return int(name[len(prefix) :])
    return None


def _last_mini_tar_slice(tardir: Path) -> Path | None:
    """
    After ``tar -cM`` returns, ``--volno-file`` can read **ahead** of the last real slice name.
    The new-volume hook has already shipped every completed slice; only the final ``mini.tar*``
    remains. Discover it by scanning the directory instead of deriving the name from ``volno``.
    """
    best: tuple[int, Path] | None = None
    for p in tardir.glob("mini.tar*"):
        if not p.is_file():
            continue
        v = _mini_tar_volume(p.name)
        if v is None:
            continue
        if best is None or v > best[0]:
            best = (v, p)
    return None if best is None else best[1]


def _emit_chunked_ship_progress(
    cfg: BcsConfig,
    datafile: Path,
    member: str,
    chunk_vol: int,
    *,
    tier3_mv_group: int | None = None,
    tier3_inner_mv_vol: int | None = None,
) -> None:
    """Per-chunk line when ``-S on``; full incremental when ``-S on -W on`` (legacy-style)."""
    if not cfg.statistics:
        return
    state = persistence.load(datafile)
    if cfg.runstatistics:
        statsmod.incremental_stats_backup(
            cfg.basename,
            state,
            member,
            chunk_vol,
            tier3_mv_group=tier3_mv_group,
            tier3_inner_mv_vol=tier3_inner_mv_vol,
        )
        persistence.save(datafile, state)
    else:
        print(member)


def _tier3(
    member_rel: str,
    tar_cwd: Path,
    cfg: BcsConfig,
    tardir: Path,
    compressdir: Path,
    dest: Path,
    datafile: Path,
    tmp_prefix: Path,
    chunk_index: int,
) -> int:
    tier3_state = Path(str(tmp_prefix) + ".tier3.json")
    rt = persistence.load(datafile)
    rt.tier3_large_file_count += 1
    mv_group = rt.tier3_large_file_count
    persistence.save(datafile, rt)
    tier3_state.write_text(
        json.dumps(
            {
                "chunk_seq": chunk_index,
                "basename": cfg.basename,
                "dest": str(dest),
                "compress": cfg.compress,
                "password": cfg.password,
                "compressdir": str(compressdir),
                "statistics": cfg.statistics,
                "runstatistics": cfg.runstatistics,
                "mv_group": mv_group,
            }
        ),
        encoding="utf-8",
    )
    hook = Path(str(tmp_prefix) + "-tier3-nvs.sh")
    hook.write_text(f'#!/bin/sh\nexec {sys.executable} -m bacchus.tier3_volume_hook\n', encoding="utf-8")
    os.chmod(hook, 0o755)
    volno = Path(str(tmp_prefix) + ".tier3.volno")
    volno.write_text("1\n", encoding="utf-8")
    mini_first = tardir / "mini.tar"

    env = {"BCS_DATAFILE": str(datafile), "BCS_TIER3_STATE": str(tier3_state)}
    extern.tar_create_multivolume_single_member(
        tar_cwd.resolve(),
        member_rel,
        mini_first,
        cfg.resolved_mini_slice_kb(),
        tardir,
        hook,
        volno,
        cfg.verbosetar,
        env=env,
    )

    last_raw = _last_mini_tar_slice(tardir)
    if last_raw is not None and last_raw.is_file():
        st = json.loads(tier3_state.read_text(encoding="utf-8"))
        seq = int(st["chunk_seq"])
        member = f"{cfg.basename}.{seq:06d}.tar"
        inner_mv = _mini_tar_volume(last_raw.name) or 1
        # Size before ship: ``ship_raw_tar`` moves ``last_raw`` out of ``tardir`` (often ``replace``).
        extra_kb = du_sk_apparent(last_raw)
        final_path = ship_raw_tar(last_raw, dest, member, compress=cfg.compress, password=cfg.password, compressdir=compressdir)
        rt = persistence.load(datafile)
        rt.source_size_running += extra_kb
        rt.dest_size_running += du_sk_apparent(final_path)
        st["chunk_seq"] = seq + 1
        tier3_state.write_text(json.dumps(st), encoding="utf-8")
        persistence.save(datafile, rt)
        lf_group = int(st.get("mv_group", 1))
        _emit_chunked_ship_progress(
            cfg,
            datafile,
            member,
            seq,
            tier3_mv_group=lf_group,
            tier3_inner_mv_vol=inner_mv,
        )
        rt = persistence.load(datafile)
        rt.incremental_timestamp = int(time.time())
        rt.incremental_timestamp_running = 0
        persistence.save(datafile, rt)
        last_raw.unlink(missing_ok=True)
        chunk_index = int(st["chunk_seq"])
    else:
        vol_hint = volno.read_text(encoding="utf-8").strip()
        raise RuntimeError(
            f"Tier-3: inner tar finished but no remaining mini.tar* slice under {tardir} "
            f"(expected final slice before ship; --volno-file last read {vol_hint!r})."
        )

    for p in tardir.glob("mini.tar*"):
        p.unlink(missing_ok=True)
    return chunk_index


def run_backup(cfg: BcsConfig) -> None:
    tmp_prefix = Path(tempfile.mktemp(prefix="baccus-", dir="/tmp"))
    tmp_runtime = Path(str(tmp_prefix) + ".runtime")
    # Wall clock for completion "Total runtime" (includes ramdisk, du, preorder walk, and all chunks).
    wall_clock_start = int(time.time())

    rd: ramdisk.Ramdisk | None = None
    tardir = cfg.tardir.resolve()
    compressdir = cfg.compressdir.resolve()
    dest = cfg.dest.resolve()

    if not cfg.compress and not cfg.password:
        tardir = dest
    elif cfg.ramdisk and (cfg.compress or cfg.password):
        size_b = ramdisk.ramdisk_size_bytes(cfg.volumesize_kb, cfg.compress, bool(cfg.password))
        rd_path = Path(str(tmp_prefix) + ".ramdisk")
        rd = ramdisk.Ramdisk(rd_path, size_b)
        rd.mount()
        tardir = rd_path
        # pigz writes ``.gz`` under ``compressdir``; use ``dest`` so tmpfs only holds raw ``.tar`` /
        # tier-3 slices (tar + gzip both on tmpfs exceeds ``size=`` for large ``-v``).
        compressdir = dest if cfg.compress else rd_path

    def cleanup() -> None:
        ramdisk.cleanup_print()
        if rd:
            ramdisk.sync_filesystem()
            rd.umount()
        ramdisk.remove_tmp_prefix(tmp_prefix)

    atexit.register(cleanup)

    source_root = cfg.source.resolve()
    source_size_total = int(
        subprocess.check_output(["du", "-sk", "--apparent-size", str(source_root)], text=True).split()[0]
    )
    desired = cfg.desired_bytes()
    absolute = cfg.absolute_bytes()

    est_chunks = max(1, (source_size_total * 1024 + desired - 1) // desired)
    if cfg.estimate:
        print(f"Estimating total size of:  {source_root}\n")
        print(f"Total size:                {statsmod._fmt_kb_scaled(source_size_total)}")
        print(
            f"Estimated chunk count (rough): {est_chunks} (nominal target {cfg.volumesize_kb:,}k)".replace(",", "")
        )
        print()
    ordered_paths = iter_source_paths_tar_order(source_root)
    stats_start = int(time.time())
    persistence.save(
        tmp_runtime,
        persistence.initial_backup_state(
            dest,
            est_chunks,
            stats_start,
            source_size_total,
            archive_mode="chunked",
            wall_clock_start_timestamp=wall_clock_start,
        ),
    )

    tar_work_cwd = backup_tar_chdir(cfg, source_root)

    chunk_index = 1
    pending_paths: list[str] = []
    pending_raw = 0

    def flush() -> None:
        nonlocal chunk_index, pending_paths, pending_raw
        if not pending_paths:
            return
        current_tar = tardir / f"_cur.{os.getpid()}.tar"
        if current_tar.exists():
            current_tar.unlink()
        extern.tar_create_archive(pending_paths, current_tar, tar_work_cwd, verbose=cfg.verbosetar)
        state = persistence.load(tmp_runtime)
        state.source_size_running += du_sk_apparent(current_tar)
        member = f"{cfg.basename}.{chunk_index:06d}.tar"
        final_path = ship_raw_tar(
            current_tar, dest, member, compress=cfg.compress, password=cfg.password, compressdir=compressdir
        )
        state.dest_size_running += du_sk_apparent(final_path)
        persistence.save(tmp_runtime, state)
        _emit_chunked_ship_progress(cfg, tmp_runtime, member, chunk_index)
        state = persistence.load(tmp_runtime)
        state.incremental_timestamp = int(time.time())
        state.incremental_timestamp_running = 0
        persistence.save(tmp_runtime, state)
        current_tar.unlink(missing_ok=True)
        chunk_index += 1
        pending_paths = []
        pending_raw = 0

    for path, file_size in iter_files_from_ordered_paths(ordered_paths):
        rel_path = member_rel_for_backup(cfg, source_root, path)
        if file_size > absolute:
            flush()
            chunk_index = _tier3(rel_path, tar_work_cwd, cfg, tardir, compressdir, dest, tmp_runtime, tmp_prefix, chunk_index)
            continue

        projected = _predict_after_add(pending_raw, file_size)
        if projected > desired and pending_paths:
            flush()
            projected = _predict_after_add(0, file_size)

        if projected > desired:
            # Defensive: normal files should fit desired unless metadata estimates drift unexpectedly.
            # Keep forward progress by placing it alone in a chunk.
            pending_paths = [rel_path]
            pending_raw = projected
            flush()
            continue

        pending_paths.append(rel_path)
        pending_raw = projected

    flush()
    if chunk_index > 1 and cfg.statistics and cfg.endstatistics:
        st = persistence.load(tmp_runtime)
        statsmod.completion_stats_backup(st, chunk_index)
