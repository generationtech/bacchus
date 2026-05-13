"""Console + on-disk stats log preamble (operation banner and option summary)."""

from __future__ import annotations

from argparse import Namespace

from bacchus import stats as statsmod
from bacchus.config import BcsConfig


def iter_option_lines(cfg: BcsConfig, ns: Namespace):
    yield f"Source directory:                    {cfg.source}"
    yield f"Destination directory:               {cfg.dest}"
    yield f"Base name for archive:               {cfg.basename}"
    yield f"Estimate size and duration:          {'on' if cfg.estimate else 'off'}"
    yield f"Show detailed statistics:            {'on' if cfg.statistics else 'off'}"
    if cfg.statistics:
        yield f"Statistics log file:                 {'on' if cfg.stats_file_log else 'off'}"
        if cfg.stats_file_log:
            lp = cfg.stats_file_log_path
            shown = str(lp.resolve()) if lp is not None else "<auto under shared memory or temp>"
            yield f"Statistics log path:                 {shown}"
    if cfg.compress or cfg.password:
        yield f"Use ramdisk for intermediate dirs:   {'on' if cfg.ramdisk else 'off'}"
    else:
        yield "Use ramdisk for intermediate dirs:   disabled"

    if cfg.compress and not cfg.ramdisk:
        yield f"Intermediate compression directory:  {cfg.compressdir}"
    if not cfg.compress:
        yield "Compression:                         disabled"

    if not cfg.password:
        yield "Encryption:                          disabled"
    else:
        if ns.filepassword:
            yield f"Password, file-based:                {ns.filepassword}"
        elif ns.commandpassword:
            yield "Password:                            command-line"
        elif ns.userpassword == "on":
            yield "Password:                            console from user"
        if ns.revealpassword == "on":
            yield f"Password is:                         {cfg.password}"


def backup_start_banner_and_lines(cfg: BcsConfig, ns: Namespace) -> list[str]:
    lines = [
        "",
        " ====================================",
        "|| Running Bacchus backup operation ||",
        " ====================================",
    ]
    lines.extend(iter_option_lines(cfg, ns))
    if not cfg.ramdisk and (cfg.compress or cfg.password):
        lines.append(f"Intermediate tar directory:          {cfg.tardir}")
    col = 37
    lines.append(f"{'Volume size for archive (KiB):':<{col}}{statsmod._fmt_kb_scaled(cfg.volumesize_kb)}")
    lines.append(f"{'Absolute max chunk (KiB):':<{col}}{statsmod._fmt_kb_scaled(cfg.resolved_absolute_max_kb())}")
    lines.append(f"{'Mini MV slice (KiB):':<{col}}{statsmod._fmt_kb_scaled(cfg.resolved_mini_slice_kb())}")
    scope = cfg.archive_path_scope
    top = (cfg.archive_top_dir or "").strip()
    lines.append(f"{'Archive path scope:':<{col}}{scope}")
    if top:
        lines.append(f"{'Archive top directory name:':<{col}}{top}")
    lines.append("")
    return lines


def restore_start_banner_and_lines(cfg: BcsConfig, ns: Namespace) -> list[str]:
    lines = [
        "",
        " =====================================",
        "|| Running Bacchus restore operation ||",
        " =====================================",
    ]
    lines.extend(iter_option_lines(cfg, ns))
    if cfg.password and not cfg.ramdisk:
        lines.append(f"Intermediate decryption directory:   {cfg.decryptdir}")
    lines.append("")
    return lines
