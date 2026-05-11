"""Runtime configuration (replaces BCS_* environment variables)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

ArchivePathScope = Literal["parent", "source"]


@dataclass
class BcsConfig:
    """Bacchus configuration for one backup or restore run."""

    subcommand: Literal["backup", "restore"]
    source: Path
    dest: Path
    basename: str = "backupfile"
    volumesize_kb: int = 100_000
    ramdisk: bool = True
    tardir: Path = field(default_factory=lambda: Path("."))
    compressdir: Path = field(default_factory=lambda: Path("."))
    compress: bool = True
    decryptdir: Path = field(default_factory=lambda: Path("."))
    userpassword: bool = True
    filepassword: Optional[Path] = None
    commandpassword: Optional[str] = None
    revealpassword: bool = False
    verbosetar: bool = False
    confirm: bool = True
    estimate: bool = True
    statistics: bool = True
    runstatistics: bool = True
    endstatistics: bool = True
    stats_file_log: bool = True
    stats_file_log_path: Optional[Path] = None
    password: str = ""
    absolute_max_size_kb: Optional[int] = None  # default 8 * volumesize at resolve time
    mini_slice_size_kb: Optional[int] = None  # default volumesize
    start_chunk: int = 1
    lowdiskspace_multiplier: int = 2
    # Chunked backup: tar member paths (restore reads whatever names were stored).
    archive_path_scope: ArchivePathScope = "parent"
    archive_top_dir: Optional[str] = None

    def resolved_absolute_max_kb(self) -> int:
        if self.absolute_max_size_kb is not None:
            return self.absolute_max_size_kb
        return self.volumesize_kb * 8

    def resolved_mini_slice_kb(self) -> int:
        if self.mini_slice_size_kb is not None:
            return self.mini_slice_size_kb
        return self.volumesize_kb

    def desired_bytes(self) -> int:
        return self.volumesize_kb * 1024

    def absolute_bytes(self) -> int:
        return self.resolved_absolute_max_kb() * 1024

    def mini_slice_bytes(self) -> int:
        return self.resolved_mini_slice_kb() * 1024
