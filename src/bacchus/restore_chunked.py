"""Manifestless chunked restore: classify each decoded tar segment, dispatch ``tar -x`` or ``tar -xM``."""

from __future__ import annotations

import atexit
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bacchus import extern, persistence, ramdisk, restore_sizing
from bacchus.classify import TarSegmentKind, classify_tar_segment
from bacchus.config import BcsConfig
from bacchus.pipeline import infer_compress_encrypt_from_chunk_paths, process_volume_restore
from bacchus import stats as statsmod
from bacchus import volume_supply


def _list_chunks(source: Path, basename: str) -> list[Path]:
    rx = re.compile(rf"^{re.escape(basename)}\.(\d{{6}})\.tar(?:\.gz)?(?:\.gpg)?$")
    items: list[tuple[int, Path]] = []
    for p in source.iterdir():
        if not p.is_file():
            continue
        m = rx.match(p.name)
        if m:
            items.append((int(m.group(1)), p))
    items.sort(key=lambda t: t[0])
    return [p for _, p in items]


def _run_inner_mv_extract(
    *,
    cfg: BcsConfig,
    vol1_plain: Path,
    first_seq: int,
    state_path: Path,
    hook_script: Path,
    volno_path: Path,
    tmp_runtime: Path,
    bcs_source: Path,
    inner_mv_group: int,
    stats_tar_volume_after_vol1: int,
    compress: bool,
    password: str,
    decryptdir: Path,
    compressdir: Path,
) -> tuple[int, Path]:
    """
    Run legacy-style inner ``tar -xM``: volume 1 is *vol1_plain*; hook decodes later chunks on demand.

    Returns ``(hook_decode_count, updated_bcs_source)``.
    """
    state = {
        "datafile": str(tmp_runtime.resolve()),
        "basename": cfg.basename,
        "compress": compress,
        "password": password,
        "decryptdir": str(decryptdir.resolve()),
        "compressdir": str(compressdir.resolve()),
        "bcs_source": str(bcs_source.resolve()),
        "first_chunk_seq": first_seq,
        "statistics": cfg.statistics,
        "runstatistics": cfg.runstatistics,
        "tier3_mv_group": inner_mv_group,
        "verbosetar": cfg.verbosetar,
        "vol1_plain_path": str(vol1_plain.resolve()),
        "stats_tar_volume_after_vol1": stats_tar_volume_after_vol1,
        "hook_decode_count": 0,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    volno_path.write_text("1\n", encoding="utf-8")
    hook_script.write_text(
        "#!/bin/sh\n" f'exec "{sys.executable}" -m bacchus.restore_inner_mv_hook\n',
        encoding="utf-8",
    )
    hook_script.chmod(hook_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    env = os.environ.copy()
    env["BCS_INNER_RESTORE_STATE"] = str(state_path.resolve())
    hook_decode_count = 0
    try:
        extern.tar_extract_multivolume_script(
            vol1_plain,
            cfg.dest.resolve(),
            cfg.verbosetar,
            hook_script,
            volno_path,
            env=env,
        )
    finally:
        try:
            st_final = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            st_final = {}
        v1_left = st_final.pop("vol1_plain_path", None)
        if v1_left:
            Path(v1_left).unlink(missing_ok=True)
        pend = st_final.pop("pending_unlink_plain", None)
        if pend:
            Path(pend).unlink(missing_ok=True)
        hook_decode_count = int(st_final.get("hook_decode_count", 0))
        state_path.write_text(json.dumps(st_final), encoding="utf-8")

    try:
        st_out = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st_out = {}
    new_src = Path(st_out.get("bcs_source", str(bcs_source)))
    return hook_decode_count, new_src.resolve()


def run_restore(cfg: BcsConfig) -> None:
    tmp_prefix = Path(tempfile.mktemp(prefix="baccus-", dir="/tmp"))
    tmp_runtime = Path(str(tmp_prefix) + ".runtime")

    bcs_source = cfg.source.resolve()
    all_chunks = _list_chunks(bcs_source, cfg.basename)
    if not all_chunks:
        raise SystemExit(f"No chunked archives {cfg.basename}.NNNNNN.tar* in {bcs_source}")

    start = max(1, cfg.start_chunk)
    paths: list[Path] = []
    for p in all_chunks:
        m = re.search(rf"{re.escape(cfg.basename)}\.(\d{{6}})\.tar", p.name)
        if m and int(m.group(1)) >= start:
            paths.append(p)
    if not paths:
        raise SystemExit(f"No chunks at or after --start-chunk {start}")

    compress, encrypt_on_disk = infer_compress_encrypt_from_chunk_paths(all_chunks)
    password = cfg.password if encrypt_on_disk else ""
    if encrypt_on_disk and not cfg.password:
        raise SystemExit(
            "Archive chunks are encrypted (.gpg); provide a password (-p, -f, or console prompt)."
        )

    rd: ramdisk.Ramdisk | None = None
    decryptdir = cfg.decryptdir.resolve()
    compressdir = cfg.compressdir.resolve()

    archive_volumes = len(all_chunks)
    source_size_total = int(
        subprocess.check_output(["du", "-sk", "--apparent-size", str(bcs_source)], text=True).split()[0]
    )

    peak_intermediate_kb: int | None = None
    tmpfs_size_bytes: int | None = None

    if compress or password:
        largest_art, probe_member = restore_sizing.largest_chunk_artifact(
            paths, cfg.basename, bcs_source, compress=compress, password=password
        )

        if cfg.ramdisk:
            largest_bytes = largest_art.stat().st_size
            probe_bytes = max(largest_bytes * 3, 1024 * 1024)
            probe_mp = Path(str(tmp_prefix) + ".probe_ramdisk")
            probe_rd = ramdisk.Ramdisk(probe_mp, probe_bytes)
            probe_rd.mount()
            try:
                decoded_probe, _, _ = process_volume_restore(
                    bcs_source,
                    probe_member,
                    probe_mp,
                    probe_mp,
                    compress=compress,
                    password=password,
                )
                decoded_probe.unlink(missing_ok=True)
            finally:
                probe_rd.umount()

        else:
            decoded_probe, _, _ = process_volume_restore(
                bcs_source,
                probe_member,
                decryptdir,
                compressdir,
                compress=compress,
                password=password,
            )
            decoded_probe.unlink(missing_ok=True)

        scratch_peak = Path(tempfile.mkdtemp(prefix="bacchus-peak-", dir="/tmp"))
        try:
            peak_intermediate_kb = restore_sizing.restore_intermediate_peak_kb(
                largest_art,
                probe_member,
                scratch_peak,
                compress=compress,
                password=password,
            )
        finally:
            subprocess.run(["rm", "-rf", str(scratch_peak)], check=False)

        if cfg.ramdisk:
            tmpfs_size_bytes = restore_sizing.restore_ramdisk_size_bytes(peak_intermediate_kb)
            rd_path = Path(str(tmp_prefix) + ".ramdisk")
            rd = ramdisk.Ramdisk(rd_path, tmpfs_size_bytes)
            rd.mount()
            decryptdir = rd_path
            compressdir = rd_path

    def cleanup() -> None:
        ramdisk.cleanup_print()
        if rd:
            ramdisk.sync_filesystem()
            rd.umount()
        ramdisk.remove_tmp_prefix(tmp_prefix)

    atexit.register(cleanup)

    if cfg.estimate:
        statsmod.print_estimate_chunked_restore(
            chunks_on_disk=archive_volumes,
            chunks_this_run=len(paths),
            start_chunk=start,
            source_size_total_kb=source_size_total,
            ramdisk_planned=bool(cfg.ramdisk and (compress or password)),
            peak_intermediate_kb=peak_intermediate_kb,
            tmpfs_size_bytes=tmpfs_size_bytes,
        )
    print()

    ts = int(time.time())
    persistence.save(
        tmp_runtime,
        persistence.initial_restore_state(
            bcs_source,
            archive_volumes,
            ts,
            source_size_total,
            0,
            0,
            archive_mode="chunked",
        ),
    )

    inner_mv_group = 0
    processed_chunks = 0
    idx = 0
    bcs_source_mutable = bcs_source

    while idx < len(paths):
        p = paths[idx]
        member = restore_sizing.chunk_member_name(p, cfg.basename)
        src_dir, _artifact = volume_supply.ensure_chunk_artifact(
            member,
            initial_src=bcs_source_mutable,
            compress=compress,
            password=password,
        )
        bcs_source_mutable = src_dir

        decoded, src_sz, dst_sz = process_volume_restore(
            src_dir,
            member,
            decryptdir,
            compressdir,
            compress=compress,
            password=password,
        )
        processed_chunks += 1

        kind = classify_tar_segment(decoded)

        st = persistence.load(tmp_runtime)
        st.source_size_running += src_sz
        st.dest_size_running += dst_sz

        tier3_g: int | None = None
        tier3_v: int | None = None

        if kind == TarSegmentKind.STANDALONE:
            extern.tar_extract_single(decoded, cfg.dest.resolve(), cfg.verbosetar)
            decoded.unlink(missing_ok=True)
            tier3_g = None
            tier3_v = None

            if cfg.statistics:
                if cfg.runstatistics:
                    statsmod.incremental_stats_restore(
                        cfg.basename,
                        st,
                        member,
                        processed_chunks,
                        tier3_mv_group=tier3_g,
                        tier3_inner_mv_vol=tier3_v,
                    )
                else:
                    print(member)

            st.incremental_timestamp = int(time.time())
            st.incremental_timestamp_running = 0
            persistence.save(tmp_runtime, st)
            idx += 1
            continue

        if kind == TarSegmentKind.MV_START:
            inner_mv_group += 1
            tier3_g = inner_mv_group
            tier3_v = 1
            if cfg.statistics:
                if cfg.runstatistics:
                    statsmod.incremental_stats_restore(
                        cfg.basename,
                        st,
                        member,
                        processed_chunks,
                        tier3_mv_group=tier3_g,
                        tier3_inner_mv_vol=tier3_v,
                    )
                else:
                    print(member)
            st.incremental_timestamp = int(time.time())
            st.incremental_timestamp_running = 0
            persistence.save(tmp_runtime, st)

            first_seq = volume_supply.chunk_seq_from_member(member, cfg.basename)
            state_path = Path(str(tmp_prefix) + f".inner_mv.{idx}.json")
            hook_script = Path(str(tmp_prefix) + f".inner_mv_nvs.{idx}.sh")
            volno_path = Path(str(tmp_prefix) + f".inner.volno.{idx}")
            hook_decode_count, bcs_source_mutable = _run_inner_mv_extract(
                cfg=cfg,
                vol1_plain=decoded,
                first_seq=first_seq,
                state_path=state_path,
                hook_script=hook_script,
                volno_path=volno_path,
                tmp_runtime=tmp_runtime,
                bcs_source=bcs_source_mutable,
                inner_mv_group=inner_mv_group,
                stats_tar_volume_after_vol1=processed_chunks,
                compress=compress,
                password=password,
                decryptdir=decryptdir,
                compressdir=compressdir,
            )
            processed_chunks += hook_decode_count
            idx += 1 + hook_decode_count
            continue

        decoded.unlink(missing_ok=True)
        raise SystemExit(
            "Invalid layout: multi-volume continuation without start at this position. "
            "Use a smaller --start-chunk that begins at the first slice (MV_START) of the inner group."
        )

    if cfg.statistics and cfg.endstatistics:
        st = persistence.load(tmp_runtime)
        statsmod.completion_stats_restore(st, len(paths), cfg.dest.resolve())
