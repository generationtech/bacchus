"""Legacy single-stream GNU tar multi-volume backup (``tar -cM``)."""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bacchus import extern, persistence, ramdisk
from bacchus.config import BcsConfig


def _setup_env(cfg: BcsConfig, datafile: Path, tmp_prefix: Path) -> dict:
    env = os.environ.copy()
    env["BCS_DATAFILE"] = str(datafile)
    env["BCS_BASENAME"] = cfg.basename
    env["BCS_COMPRESS"] = "on" if cfg.compress else "off"
    env["BCS_COMPRESDIR"] = str(cfg.compressdir.resolve())
    env["BCS_DEST"] = str(cfg.dest.resolve())
    env["BCS_ENDSTATISTICS"] = "on" if cfg.endstatistics else "off"
    env["BCS_LOWDISKSPACE"] = str(cfg.lowdiskspace_multiplier)
    env["BCS_PASSWORD"] = cfg.password
    env["BCS_STATISTICS"] = "on" if cfg.statistics else "off"
    env["BCS_RUNSTATISTICS"] = "on" if cfg.runstatistics else "off"
    env["BCS_VOLUMESIZE"] = str(cfg.volumesize_kb)
    env["BCS_TMPFILE"] = str(tmp_prefix)
    return env


def run_backup(cfg: BcsConfig) -> None:
    tmp_prefix = Path(tempfile.mktemp(prefix="baccus-", dir="/tmp"))
    tmp_volno = Path(str(tmp_prefix) + ".volno")
    tmp_runtime = Path(str(tmp_prefix) + ".runtime")

    rd: ramdisk.Ramdisk | None = None
    tardir = cfg.tardir.resolve()
    compressdir = cfg.compressdir.resolve()

    if not cfg.compress and not cfg.password:
        tardir = cfg.dest.resolve()
    elif cfg.ramdisk and (cfg.compress or cfg.password):
        size_b = ramdisk.ramdisk_size_bytes(cfg.volumesize_kb, cfg.compress, bool(cfg.password))
        rd_path = Path(str(tmp_prefix) + ".ramdisk")
        rd = ramdisk.Ramdisk(rd_path, size_b)
        rd.mount()
        tardir = rd_path
        compressdir = cfg.dest.resolve() if cfg.compress else rd_path

    hook = Path(str(tmp_prefix) + "-nvs.sh")
    hook.write_text(f'#!/bin/sh\nexec {sys.executable} -m bacchus.volume_hook backup\n', encoding="utf-8")
    os.chmod(hook, 0o755)

    def cleanup() -> None:
        ramdisk.cleanup_print()
        if rd:
            ramdisk.sync_filesystem()
            rd.umount()
        ramdisk.remove_tmp_prefix(tmp_prefix)

    atexit.register(cleanup)

    source_size_total = int(
        subprocess.check_output(
            ["du", "-sk", "--apparent-size", str(cfg.source.resolve())], text=True
        ).split()[0]
    )
    total_volumes = source_size_total // cfg.volumesize_kb
    if cfg.volumesize_kb * total_volumes < source_size_total:
        total_volumes += 1

    if cfg.estimate:
        print(f"Estimating total size of:  {cfg.source}\n")
        print(f"Total size:                {source_size_total:,}k".replace(",", ""))
        print(
            f"Number of archive volumes: {total_volumes} ({cfg.volumesize_kb:,}k each)".replace(",", "")
        )
    print()

    ts = int(time.time())
    state = persistence.initial_backup_state(
        cfg.dest.resolve(), total_volumes, ts, source_size_total, archive_mode="legacy"
    )
    persistence.save(tmp_runtime, state)

    env = _setup_env(cfg, tmp_runtime, tmp_prefix)
    # pigz output path; on ramdisk+compress this is ``dest`` so tmpfs is not tar+gz at once
    env["BCS_COMPRESDIR"] = str(compressdir)
    tmp_volno.write_text("1\n", encoding="utf-8")

    extern.tar_multivolume_create(
        cfg.source.resolve(),
        tardir,
        cfg.basename,
        cfg.volumesize_kb,
        tmp_volno,
        hook,
        cfg.verbosetar,
        env=env,
    )

    vol = int(tmp_volno.read_text().strip())
    if not cfg.compress and not cfg.password:
        st = persistence.load(tmp_runtime)
        tardir = Path(st.bcs_dest)

    tar_base = f"{cfg.basename}.tar" if vol == 1 else f"{cfg.basename}.tar-{vol}"
    tar_path = tardir / tar_base
    env_final = env.copy()
    env_final["TAR_ARCHIVE"] = str(tar_path)
    env_final["TAR_VOLUME"] = str(vol + 1)
    env_final["TAR_SUBCOMMAND"] = "-c"
    env_final["TAR_FD"] = "none"
    subprocess.run([sys.executable, "-m", "bacchus.volume_hook", "backup"], env=env_final, check=True)
