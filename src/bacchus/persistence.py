"""JSON runtime persistence (replaces jo + load_persistence.sh)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RuntimeState:
    """Fields aligned with legacy jq JSON for stats compatibility."""

    bcs_dest: str = ""
    bcs_source: str = ""
    archive_volumes: int = 0
    start_timestamp: int = 0
    start_timestamp_running: int = 0
    incremental_timestamp: int = 0
    incremental_timestamp_running: int = 0
    remain_text_size_running: int = 0
    incremental_text_size_running: int = 0
    avg_text_size_running: int = 0
    comp_ratio_text_size_running: int = 0
    source_size_total: int = 0
    source_size_running: int = 0
    dest_size_running: int = 0
    size_text_running: int = 0
    stats_line_source_seg_w: int = 0
    stats_line_dest_seg_w: int = 0
    chunk_index: int = 0
    mv_group_open: bool = False
    # Chunked backup: wall clock at run start; incremental stats use ``start_timestamp`` after preorder walk.
    wall_clock_start_timestamp: int = 0
    # Chunked backup: EMA-smoothed ``/NNN`` denominator (persisted between chunks).
    chunk_total_display_smooth: int = 0
    # Chunked tier-3: source files archived via inner ``tar -cM`` (large files).
    tier3_large_file_count: int = 0

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=0)

    @classmethod
    def from_json(cls, s: str) -> "RuntimeState":
        from dataclasses import fields

        data = json.loads(s)
        st = cls()
        for f in fields(cls):
            if f.name in data:
                setattr(st, f.name, data[f.name])
        return st


def load(path: Path) -> RuntimeState:
    return RuntimeState.from_json(path.read_text(encoding="utf-8"))


def save(path: Path, state: RuntimeState) -> None:
    path.write_text(state.to_json() + "\n", encoding="utf-8")


def initial_backup_state(
    dest: Path,
    archive_volumes: int,
    timestamp: int,
    source_size_total: int,
    wall_clock_start_timestamp: int = 0,
) -> RuntimeState:
    return RuntimeState(
        bcs_dest=str(dest),
        archive_volumes=archive_volumes,
        start_timestamp=timestamp,
        incremental_timestamp=timestamp,
        source_size_total=source_size_total,
        wall_clock_start_timestamp=wall_clock_start_timestamp,
    )


def initial_restore_state(
    source_dir: Path,
    archive_volumes: int,
    timestamp: int,
    source_size_total: int,
    source_size_running: int,
    dest_size_running: int,
) -> RuntimeState:
    return RuntimeState(
        bcs_source=str(source_dir),
        archive_volumes=archive_volumes,
        start_timestamp=timestamp,
        incremental_timestamp=timestamp,
        source_size_total=source_size_total,
        source_size_running=source_size_running,
        dest_size_running=dest_size_running,
    )
