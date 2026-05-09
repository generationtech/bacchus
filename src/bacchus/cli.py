"""Command-line entry (replaces bacchus.sh + argbash)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bacchus import backup_chunked, backup_legacy, restore_chunked, restore_legacy
from bacchus.config import BcsConfig
from bacchus import modes


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
            "--archive-mode",
            choices=["chunked", "legacy"],
            default=None,
            help="chunked (default) or legacy single tar -cM stream (restore: auto-detect if omitted)",
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
            p1 = input("Enter a password for encryption or press enter for no password: ")
            print()
            if not p1:
                return ""
            p2 = input("Re-enter a password for encryption or press enter for no password: ")
            print()
            if not p2 or p1 != p2:
                print("Passwords do not match!")
            else:
                return p1
    return ""


def _print_options(cfg: BcsConfig, ns: argparse.Namespace) -> None:
    print(f"Source directory:                    {cfg.source}")
    print(f"Destination directory:               {cfg.dest}")
    print(f"Base name for archive:               {cfg.basename}")
    print(f"Estimate size and duration:          {'on' if cfg.estimate else 'off'}")
    print(f"Show detailed statistics:            {'on' if cfg.statistics else 'off'}")
    if cfg.compress or cfg.password:
        print(f"Use ramdisk for intermediate dirs:   {'on' if cfg.ramdisk else 'off'}")
    else:
        print("Use ramdisk for intermediate dirs:   disabled")

    if cfg.compress and not cfg.ramdisk:
        print(f"Intermediate compression directory:  {cfg.compressdir}")
    if not cfg.compress:
        print("Compression:                         disabled")

    if not cfg.password:
        print("Encryption:                          disabled")
    else:
        if ns.filepassword:
            print(f"Password, file-based:                {ns.filepassword}")
        elif ns.commandpassword:
            print("Password:                            command-line")
        elif ns.userpassword == "on":
            print("Password:                            console from user")
        if ns.revealpassword == "on":
            print(f"Password is:                         {cfg.password}")


def _confirm_start(cfg: BcsConfig, ns: argparse.Namespace) -> None:
    if ns.confirm == "on":
        input("Press enter to begin...")
        print()
    if (not cfg.compress) or (not cfg.password):
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
        password=pw,
        archive_mode=ns.archive_mode,
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
        if cfg.archive_mode is None:
            cfg.archive_mode = "chunked"
        print("\n ====================================\n|| Running Bacchus backup operation ||\n ====================================")
        _print_options(cfg, ns)
        if not cfg.ramdisk and (cfg.compress or cfg.password):
            print(f"Intermediate tar directory:          {cfg.tardir}")
        _BACKUP_OPT_COL = 37
        print(
            f"{'Volume size for archive:':<{_BACKUP_OPT_COL}}"
            f"{cfg.volumesize_kb:,}k".replace(",", "")
        )
        if cfg.archive_mode == "chunked":
            print(
                f"{'Absolute max chunk (kB):':<{_BACKUP_OPT_COL}}"
                f"{cfg.resolved_absolute_max_kb():,}".replace(",", "")
            )
            print(
                f"{'Mini MV slice (kB):':<{_BACKUP_OPT_COL}}"
                f"{cfg.resolved_mini_slice_kb():,}".replace(",", "")
            )
            scope = cfg.archive_path_scope
            top = (cfg.archive_top_dir or "").strip()
            print(f"{'Archive path scope:':<{_BACKUP_OPT_COL}}{scope}")
            if top:
                print(f"{'Archive top directory name:':<{_BACKUP_OPT_COL}}{top}")
        print()
        _confirm_start(cfg, ns)
        if cfg.archive_mode == "legacy":
            backup_legacy.run_backup(cfg)
        else:
            backup_chunked.run_backup(cfg)
        return 0

    if ns.subcommand == "restore":
        if cfg.archive_mode is None:
            try:
                cfg.archive_mode = modes.infer_archive_mode(cfg.source.resolve(), cfg.basename)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 1

        print("\n =====================================\n|| Running Bacchus restore operation ||\n =====================================")
        _print_options(cfg, ns)
        if cfg.password and not cfg.ramdisk:
            print(f"Intermediate decryption directory:   {cfg.decryptdir}")
        print()
        _confirm_start(cfg, ns)

        if cfg.archive_mode == "legacy":
            restore_legacy.run_restore(cfg)
        else:
            restore_chunked.run_restore(cfg)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
