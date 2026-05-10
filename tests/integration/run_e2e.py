"""CLI entry for the full Bacchus E2E (random tree → chunked backup → restore → verify)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tests.integration._e2e_impl import E2EConfig, run_e2e


def main(argv: list[str] | None = None) -> int:
    d = E2EConfig()
    p = argparse.ArgumentParser(
        description=(
            "Run Bacchus chunked E2E: random source tree, backup, Tier-3 check, restore, "
            "byte verify, regular-file counts, and rsync checksum dry-run when rsync is installed."
        ),
    )
    p.add_argument("--total-bytes", type=int, default=d.total_bytes, help="total random data (default: %(default)s)")
    p.add_argument("--workdir", type=Path, default=None, help="work directory (default: auto under $TMPDIR)")
    p.add_argument("--keep-on-success", action="store_true", help="do not delete workdir after success")
    p.add_argument("--seed", type=int, default=None, help="RNG seed (default: time-based)")
    p.add_argument("--compress", action="store_true", help="enable pigz (-z on)")
    p.add_argument("--password", default="", help="gpg password (empty = no encryption)")
    p.add_argument("--volumesize-kb", type=int, default=d.volumesize_kb, help="chunk size kB")
    p.add_argument("--absolute-max-kb", type=int, default=d.absolute_max_kb, help="Tier-3 threshold kB")
    p.add_argument("--mini-slice-kb", type=int, default=d.mini_slice_kb, help="inner tar -L kB")
    p.add_argument(
        "--large-file-ratio",
        type=float,
        default=d.large_file_ratio,
        help="fraction of files larger than absolute max (default: %(default)s)",
    )
    p.add_argument("-b", "--basename", default=d.basename, help="archive basename")
    ns = p.parse_args(argv)

    cfg = E2EConfig(
        total_bytes=ns.total_bytes,
        workdir=ns.workdir,
        volumesize_kb=ns.volumesize_kb,
        absolute_max_kb=ns.absolute_max_kb,
        mini_slice_kb=ns.mini_slice_kb,
        large_file_ratio=ns.large_file_ratio,
        basename=ns.basename,
        seed=ns.seed,
        keep_on_success=ns.keep_on_success,
        compress=ns.compress,
        password=ns.password,
    )
    return run_e2e(cfg)


if __name__ == "__main__":
    sys.exit(main())
