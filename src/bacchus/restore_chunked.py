"""Manifestless chunked restore: classify each decoded tar segment, dispatch ``tar -x`` or ``tar -xM``."""

from __future__ import annotations

import atexit
import re
import subprocess
import tempfile
import time
from pathlib import Path

from bacchus import extern, persistence, ramdisk, restore_sizing
from bacchus.classify import TarSegmentKind, classify_tar_segment
from bacchus.config import BcsConfig
from bacchus.pipeline import process_volume_restore
from bacchus import stats as statsmod


def _chunk_member_name(path: Path, basename: str) -> str:
    return restore_sizing.chunk_member_name(path, basename)


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


def _artifact_path(src_dir: Path, member: str, compress: bool, password: str) -> Path:
    p = src_dir / member
    if compress:
        p = Path(str(p) + ".gz")
    if password:
        p = Path(str(p) + ".gpg")
    return p


def _prompt_new_source(expected: Path, current: Path) -> Path:
    print(f"\nArchive chunk: {expected.name}\nNOT FOUND in:   {current}\n")
    print("Place the file or enter a new source directory path (empty = retry):\n")
    np = input().strip()
    return Path(np) if np else current


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

    tail = str(paths[-1])
    compress = ".gz" in tail
    password = cfg.password if ".gpg" in tail else ""

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

    mv_buf: list[Path] = []
    inner_mv_group = 0

    for vol_idx, p in enumerate(paths, start=1):
        member = _chunk_member_name(p, cfg.basename)
        src_dir = bcs_source
        artifact = _artifact_path(src_dir, member, compress, password)
        while not artifact.is_file():
            src_dir = _prompt_new_source(artifact, src_dir)
            artifact = _artifact_path(src_dir, member, compress, password)

        decoded, src_sz, dst_sz = process_volume_restore(
            src_dir,
            member,
            decryptdir,
            compressdir,
            compress=compress,
            password=password,
        )
        kind = classify_tar_segment(decoded)
        # Inner Tier-3 ``tar -cM`` last slice often looks like standalone (ustar trailer) but still
        # needs earlier slices for ``tar -xM``; once mv_buf is open, finish the group here.
        if mv_buf and kind == TarSegmentKind.STANDALONE:
            kind = TarSegmentKind.MV_END

        tier3_g: int | None = None
        tier3_v: int | None = None

        if kind == TarSegmentKind.STANDALONE:
            if mv_buf:
                raise SystemExit(
                    "Invalid layout: standalone chunk while a multi-volume group is open. "
                    "Use an earlier --start-chunk or restore from chunk 1."
                )
            extern.tar_extract_single(decoded, cfg.dest.resolve(), cfg.verbosetar)
            decoded.unlink(missing_ok=True)
        elif kind == TarSegmentKind.MV_START:
            if mv_buf:
                raise SystemExit("Invalid layout: MV_START while a group is already open.")
            inner_mv_group += 1
            mv_buf.append(decoded)
            tier3_g = inner_mv_group
            tier3_v = len(mv_buf)
        elif kind in (TarSegmentKind.MV_MIDDLE, TarSegmentKind.MV_END):
            if not mv_buf:
                raise SystemExit(
                    "Invalid layout: multi-volume continuation without start. "
                    "Choose a smaller --start-chunk that begins at MV_START."
                )
            mv_buf.append(decoded)
            tier3_g = inner_mv_group
            tier3_v = len(mv_buf)
            if kind == TarSegmentKind.MV_END:
                extern.tar_extract_multivolume_buffered(mv_buf, cfg.dest.resolve(), cfg.verbosetar)
                for x in mv_buf:
                    x.unlink(missing_ok=True)
                mv_buf.clear()
        else:
            raise SystemExit(f"Unknown segment kind: {kind}")

        st = persistence.load(tmp_runtime)
        st.source_size_running += src_sz
        st.dest_size_running += dst_sz

        if cfg.statistics:
            if cfg.runstatistics:
                statsmod.incremental_stats_restore(
                    cfg.basename,
                    st,
                    member,
                    vol_idx,
                    tier3_mv_group=tier3_g,
                    tier3_inner_mv_vol=tier3_v,
                )
            else:
                print(member)

        st.incremental_timestamp = int(time.time())
        st.incremental_timestamp_running = 0
        persistence.save(tmp_runtime, st)

    if mv_buf:
        raise SystemExit("Truncated multi-volume group at end of backup.")

    if cfg.statistics and cfg.endstatistics:
        st = persistence.load(tmp_runtime)
        statsmod.completion_stats_restore(st, len(paths), cfg.dest.resolve())
