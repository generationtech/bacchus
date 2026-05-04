from __future__ import annotations

from pathlib import Path

from bacchus import persistence


def test_roundtrip_json(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    s = persistence.initial_backup_state(Path("/dest"), 3, 1, 100, archive_mode="chunked")
    persistence.save(p, s)
    s2 = persistence.load(p)
    assert s2.archive_volumes == 3
    assert s2.archive_mode == "chunked"
