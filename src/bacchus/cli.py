"""Command-line entry (replaces bacchus.sh + argbash)."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from bacchus import backup_chunked, restore_chunked
from bacchus import stats as statsmod
from bacchus import operation_preamble
from bacchus.config import BcsConfig


def _bool_from_store(v: str) -> bool:
    return v in ("on", "true", "1", "yes")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="bacchus",
        description="Bacchus: tar multi-volume backup/restore with optional pigz and gpg per volume/chunk.",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-s", "--source", default=".", help="source directory (default: .)")
        sp.add_argument("-d", "--dest", default=".", help="destination directory (default: .)")
        sp.add_argument("-b", "--basename", default="backupfile", help="archive base filename (default: backupfile)")
        sp.add_argument(
            "-v",
            "--volumesize",
            type=int,
            default=100_000,
            help="volume/chunk size in kB (default: 100000)",
        )
        sp.add_argument(
            "-r",
            "--ramdisk",
            choices=["on", "off"],
            default="on",
            help="use tmpfs for intermediates when compress or encrypt is on (default: on)",
        )
        sp.add_argument("-t", "--tardir", default=".", help="intermediate raw tar directory (default: .)")
        sp.add_argument("-c", "--compressdir", default=".", help="intermediate compression directory (default: .)")
        sp.add_argument(
            "-z",
            "--compress",
            choices=["on", "off"],
            default="on",
            help="enable pigz compression (default: on)",
        )
        sp.add_argument("-e", "--decryptdir", default=".", help="intermediate decryption directory (default: .)")
        sp.add_argument(
            "-u",
            "--userpassword",
            choices=["on", "off"],
            default="on",
            help="prompt for password if not given via -f/-p (default: on)",
        )
        sp.add_argument("-f", "--filepassword", default=None, help="read password from file (insecure if leaked)")
        sp.add_argument("-p", "--commandpassword", default=None, help="password on command line (danger)")
        sp.add_argument(
            "-R",
            "--revealpassword",
            choices=["on", "off"],
            default="off",
            help="echo password when printing options (default: off)",
        )
        sp.add_argument(
            "-T",
            "--verbosetar",
            choices=["on", "off"],
            default="off",
            help="pass verbose flag to tar (default: off)",
        )
        sp.add_argument(
            "-C",
            "--confirm",
            choices=["on", "off"],
            default="on",
            help="require Enter before starting (default: on)",
        )
        sp.add_argument(
            "-E",
            "--estimate",
            choices=["on", "off"],
            default="on",
            help="print size/volume estimates (default: on)",
        )
        sp.add_argument(
            "-S",
            "--statistics",
            choices=["on", "off"],
            default="on",
            help="enable statistics machinery (default: on)",
        )
        sp.add_argument(
            "-W",
            "--runstatistics",
            choices=["on", "off"],
            default="on",
            help="print incremental statistics (default: on)",
        )
        sp.add_argument(
            "-X",
            "--endstatistics",
            choices=["on", "off"],
            default="on",
            help="print completion statistics (default: on)",
        )
        sp.add_argument(
            "--stats-log-file",
            choices=["on", "off"],
            default="on",
            help="mirror incremental and completion statistics to a file (default: on; use with -S on)",
        )
        sp.add_argument(
            "--stats-log-path",
            default=None,
            metavar="PATH",
            help="statistics log file path (default: unique file under /dev/shm, /run/user/$UID, or TMPDIR, prefix bacchus-stats-)",
        )
        sp.add_argument(
            "--absolute-max-size",
            type=int,
            default=None,
            help="chunked backup: max single-chunk size in kB before Tier-3 mini MV (default: 8 * volumesize)",
        )
        sp.add_argument(
            "--mini-slice-size",
            type=int,
            default=None,
            help="chunked backup: -L for inner tar -cM in kB (default: volumesize)",
        )
        sp.add_argument(
            "--start-chunk",
            type=int,
            default=1,
            help="chunked restore: 1-based first chunk index (default: 1)",
        )

    pb = sub.add_parser("backup", help="create a backup")
    add_common(pb)
    pb.add_argument(
        "--archive-path-scope",
        choices=["parent", "source"],
        default="parent",
        help="chunked backup: tar member paths relative to source's parent (default) or source root only",
    )
    pb.add_argument(
        "--archive-top-dir",
        default=None,
        metavar="NAME",
        help="chunked backup: store members as NAME/... relative to source (implies chdir source); "
        "shortens paths and sets a stable top-level directory name",
    )
    pr = sub.add_parser("restore", help="restore a backup")
    add_common(pr)

    return p.parse_args(argv)


def _password_from_args(ns: argparse.Namespace) -> str:
    if ns.filepassword:
        return Path(ns.filepassword).read_text(encoding="utf-8").rstrip("\n")
    if ns.commandpassword:
        return ns.commandpassword
    if ns.userpassword == "on":
        while True:
            print()
            p1 = getpass.getpass("Enter a password for encryption or press enter for no password: ")
            print()
            if not p1:
                return ""
            p2 = getpass.getpass("Re-enter a password for encryption or press enter for no password: ")
            print()
            if not p2 or p1 != p2:
                print("Passwords do not match!")
            else:
                return p1
    return ""


def _ensure_default_stats_log_path(cfg: BcsConfig) -> None:
    if cfg.stats_file_log and cfg.statistics and cfg.stats_file_log_path is None:
        cfg.stats_file_log_path = statsmod.create_default_stats_log_path()


def _confirm_start(cfg: BcsConfig, ns: argparse.Namespace) -> None:
    if ns.confirm == "on":
        input("Press enter to begin...")
        print()
    # Ramdisk is only meaningful while compress or encryption stages need scratch space.
    if not (cfg.compress or cfg.password):
        cfg.ramdisk = False


def _ns_to_cfg(ns: argparse.Namespace) -> BcsConfig:
    pw = _password_from_args(ns)
    return BcsConfig(
        subcommand=ns.subcommand,
        source=Path(ns.source),
        dest=Path(ns.dest),
        basename=ns.basename,
        volumesize_kb=ns.volumesize,
        ramdisk=_bool_from_store(ns.ramdisk),
        tardir=Path(ns.tardir),
        compressdir=Path(ns.compressdir),
        compress=_bool_from_store(ns.compress),
        decryptdir=Path(ns.decryptdir),
        userpassword=_bool_from_store(ns.userpassword),
        filepassword=Path(ns.filepassword) if ns.filepassword else None,
        commandpassword=ns.commandpassword,
        revealpassword=_bool_from_store(ns.revealpassword),
        verbosetar=_bool_from_store(ns.verbosetar),
        confirm=_bool_from_store(ns.confirm),
        estimate=_bool_from_store(ns.estimate),
        statistics=_bool_from_store(ns.statistics),
        runstatistics=_bool_from_store(ns.runstatistics),
        endstatistics=_bool_from_store(ns.endstatistics),
        stats_file_log=_bool_from_store(ns.stats_log_file),
        stats_file_log_path=Path(ns.stats_log_path).resolve() if ns.stats_log_path else None,
        password=pw,
        absolute_max_size_kb=ns.absolute_max_size,
        mini_slice_size_kb=ns.mini_slice_size,
        start_chunk=ns.start_chunk,
        archive_path_scope=getattr(ns, "archive_path_scope", "parent"),
        archive_top_dir=getattr(ns, "archive_top_dir", None),
    )


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    cfg = _ns_to_cfg(ns)

    if ns.subcommand == "backup":
        _ensure_default_stats_log_path(cfg)
        preamble_body = "\n".join(operation_preamble.backup_start_banner_and_lines(cfg, ns))
        print(preamble_body)
        _confirm_start(cfg, ns)
        backup_chunked.run_backup(cfg, stats_log_preamble=preamble_body + "\n")
        return 0

    if ns.subcommand == "restore":
        _ensure_default_stats_log_path(cfg)
        preamble_body = "\n".join(operation_preamble.restore_start_banner_and_lines(cfg, ns))
        print(preamble_body)
        _confirm_start(cfg, ns)

        restore_chunked.run_restore(cfg, stats_log_preamble=preamble_body + "\n")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
