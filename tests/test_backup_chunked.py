from __future__ import annotations

from pathlib import Path

from bacchus import backup_chunked
from bacchus.config import BcsConfig


def test_chunked_uses_single_tar_create_per_flushed_chunk(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    tard = tmp_path / "tard"
    comp = tmp_path / "comp"
    src.mkdir()
    dst.mkdir()
    tard.mkdir()
    comp.mkdir()

    files = []
    for i in range(5):
        p = src / f"f{i}.txt"
        p.write_text("x", encoding="utf-8")
        files.append(p)

    monkeypatch.setattr(
        backup_chunked.subprocess,
        "check_output",
        lambda *args, **kwargs: "5\n",
    )
    monkeypatch.setattr(
        backup_chunked,
        "iter_files_with_sizes",
        lambda _source: ((p, 600) for p in files),
    )
    monkeypatch.setattr(backup_chunked, "du_sk_apparent", lambda _p: 1)

    tar_calls: list[list[str]] = []

    def fake_tar_create_archive(paths_relative_to_cwd, archive_path, cwd, verbose):
        tar_calls.append(list(paths_relative_to_cwd))
        archive_path.write_bytes(b"tar")

    monkeypatch.setattr(backup_chunked.extern, "tar_create_archive", fake_tar_create_archive)

    shipped: list[str] = []

    def fake_ship_raw_tar(raw_tar, dest_dir, archive_member_name, **kwargs):
        final = dest_dir / f"{archive_member_name}.gz.gpg"
        final.write_bytes(b"out")
        shipped.append(archive_member_name)
        return final

    monkeypatch.setattr(backup_chunked, "ship_raw_tar", fake_ship_raw_tar)

    cfg = BcsConfig(
        subcommand="backup",
        source=src,
        dest=dst,
        basename="test",
        volumesize_kb=4,
        ramdisk=False,
        tardir=tard,
        compressdir=comp,
        compress=True,
        userpassword=False,
        confirm=False,
        estimate=False,
        statistics=False,
        runstatistics=False,
        endstatistics=False,
        password="",
        archive_mode="chunked",
    )

    backup_chunked.run_backup(cfg)

    assert tar_calls == [
        ["src/f0.txt", "src/f1.txt"],
        ["src/f2.txt", "src/f3.txt"],
        ["src/f4.txt"],
    ]
    assert shipped == ["test.000001.tar", "test.000002.tar", "test.000003.tar"]
