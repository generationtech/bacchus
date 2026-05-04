"""Legacy GNU tar multi-volume restore (``tar -xM``)."""

from __future__ import annotations

import atexit
import glob
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bacchus import extern, persistence, ramdisk
from bacchus.config import BcsConfig
from bacchus.pipeline import process_volume_restore
from bacchus import stats as statsmod


def _restore_env(cfg: BcsConfig, datafile: Path, tmp_prefix: Path, bcs_source: Path) -> dict:
    env = os.environ.copy()
    env["BCS_DATAFILE"] = str(datafile)
    env["BCS_BASENAME"] = cfg.basename
    env["BCS_COMPRESS"] = "on" if cfg.compress else "off"
    env["BCS_COMPRESDIR"] = str(cfg.compressdir.resolve())
    env["BCS_DECRYPTDIR"] = str(cfg.decryptdir.resolve())
    env["BCS_DEST"] = str(cfg.dest.resolve())
    env["BCS_ENDSTATISTICS"] = "on" if cfg.endstatistics else "off"
    env["BCS_ESTIMATE"] = "on" if cfg.estimate else "off"
    env["BCS_PASSWORD"] = cfg.password
    env["BCS_STATISTICS"] = "on" if cfg.statistics else "off"
    env["BCS_RUNSTATISTICS"] = "on" if cfg.runstatistics else "off"
    env["BCS_TMPFILE"] = str(tmp_prefix)
    env["BCS_SOURCE"] = str(bcs_source)
    return env


def run_restore(cfg: BcsConfig) -> None:
    tmp_prefix = Path(tempfile.mktemp(prefix="baccus-", dir="/tmp"))
    tmp_volno = Path(str(tmp_prefix) + ".volno")
    tmp_runtime = Path(str(tmp_prefix) + ".runtime")

    bcs_source = cfg.source.resolve()

    matches = sorted(glob.glob(str(bcs_source / f"{cfg.basename}.tar*")))
    if not matches:
        raise SystemExit(f"No archives matching {cfg.basename}.tar* in {bcs_source}")
    tail = matches[-1]
    compress = ".gz" in tail
    password = cfg.password if ".gpg" in tail else ""

    rd: ramdisk.Ramdisk | None = None
    tardir = cfg.tardir.resolve()
    decryptdir = cfg.decryptdir.resolve()
    compressdir = cfg.compressdir.resolve()

    ramdisk_size_tmpdir = Path(str(tmp_prefix) + ".ramdisk_size")
    ramdisk_size_tmpdir.mkdir()
    first_name = f"{cfg.basename}.tar"
    plain, _, dest_actual = process_volume_restore(
        bcs_source,
        first_name,
        ramdisk_size_tmpdir,
        ramdisk_size_tmpdir,
        compress=compress,
        password=password,
    )
    volumesize_kb = dest_actual
    subprocess.run(["rm", "-rf", str(ramdisk_size_tmpdir)], check=False)

    if not compress and not password:
        tardir = cfg.dest.resolve()
    elif cfg.ramdisk and (compress or password):
        size_b = ramdisk.ramdisk_size_bytes(volumesize_kb, compress, bool(password))
        rd_path = Path(str(tmp_prefix) + ".ramdisk")
        rd = ramdisk.Ramdisk(rd_path, size_b)
        rd.mount()
        decryptdir = rd_path
        compressdir = rd_path
        tardir = rd_path

    hook = Path(str(tmp_prefix) + "-nvs.sh")
    hook.write_text(f'#!/bin/sh\nexec {sys.executable} -m bacchus.volume_hook restore\n', encoding="utf-8")
    os.chmod(hook, 0o755)

    def cleanup() -> None:
        ramdisk.cleanup_print()
        if rd:
            ramdisk.sync_filesystem()
            rd.umount()
        ramdisk.remove_tmp_prefix(tmp_prefix)

    atexit.register(cleanup)

    archive_volumes = len(glob.glob(str(bcs_source / f"{cfg.basename}.tar*")))
    source_size_total = int(
        subprocess.check_output(["du", "-sk", "--apparent-size", str(bcs_source)], text=True).split()[0]
    )

    if cfg.estimate:
        bcs_end = statsmod.compute_end(bcs_source, cfg.basename, Path(tempfile.gettempdir()), compress, password)
        statsmod.print_estimate(volumesize_kb, archive_volumes, source_size_total, bcs_end)
    print()

    plain2, src_run, dst_run = process_volume_restore(
        bcs_source,
        first_name,
        decryptdir,
        compressdir,
        compress=compress,
        password=password,
    )
    # tar -f expects path to first plain segment (bash uses $source after Process_Volume)
    source_for_tar = plain2

    archive_max_name = len(cfg.basename) + len(str(archive_volumes)) + 5
    archive_max_num = len(str(archive_volumes)) + 1
    pct = (100 // archive_volumes) if archive_volumes else 0
    print(
        f"{(cfg.basename + '.tar'):<{archive_max_name}s} "
        f"{('/' + str(archive_volumes)):>{archive_max_num}s} {pct:4d}%"
    )

    ts = int(time.time())
    state = persistence.initial_restore_state(
        bcs_source,
        archive_volumes,
        ts,
        source_size_total,
        src_run,
        dst_run,
        archive_mode="legacy",
    )
    persistence.save(tmp_runtime, state)

    env = _restore_env(cfg, tmp_runtime, tmp_prefix, bcs_source)
    env["BCS_COMPRESS"] = "on" if compress else "off"
    env["BCS_PASSWORD"] = password
    env["BCS_COMPRESDIR"] = str(compressdir)
    env["BCS_DECRYPTDIR"] = str(decryptdir)
    tmp_volno.write_text("1\n", encoding="utf-8")

    extern.tar_multivolume_extract(
        source_for_tar,
        cfg.dest.resolve(),
        tmp_volno,
        hook,
        cfg.verbosetar,
        env=env,
    )

    st = persistence.load(tmp_runtime)
    if cfg.statistics and cfg.endstatistics:
        statsmod.completion_stats_restore(st, archive_volumes, cfg.dest.resolve())

    vol = int(tmp_volno.read_text().strip())
    if vol == 1:
        source_for_tar.unlink(missing_ok=True)
    else:
        (source_for_tar.parent / f"{cfg.basename}.tar-{vol}").unlink(missing_ok=True)
