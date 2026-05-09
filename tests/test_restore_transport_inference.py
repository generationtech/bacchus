"""Regression: infer compress/encrypt from all chunks, not only the last filename."""

from __future__ import annotations

from pathlib import Path

from bacchus.pipeline import detect_compress_encrypt_from_artifacts, infer_compress_encrypt_from_chunk_paths


def test_infer_encrypt_true_if_any_chunk_gpg_even_when_last_plain_gz(tmp_path: Path) -> None:
    d = tmp_path
    (d / "test.000001.tar.gz.gpg").write_bytes(b"x")
    (d / "test.000002.tar.gz").write_bytes(b"y")
    chunks = sorted(d.glob("test.*"))
    compress, encrypt = infer_compress_encrypt_from_chunk_paths(chunks)
    assert compress is True
    assert encrypt is True


def test_infer_false_for_empty_chunks() -> None:
    assert infer_compress_encrypt_from_chunk_paths([]) == (False, False)


def test_detect_compress_encrypt_from_artifacts_scans_all_globs(tmp_path: Path) -> None:
    d = tmp_path
    (d / "legacy.tar").write_bytes(b"a")
    (d / "legacy.tar-2.gz").write_bytes(b"b")
    (d / "legacy.tar-3.gz.gpg").write_bytes(b"c")
    compress, encrypt = detect_compress_encrypt_from_artifacts(d, "legacy")
    assert compress is True
    assert encrypt is True


def test_infer_tar_gpg_without_gz(tmp_path: Path) -> None:
    (tmp_path / "x.000001.tar.gpg").write_bytes(b"1")
    chunks = [tmp_path / "x.000001.tar.gpg"]
    compress, encrypt = infer_compress_encrypt_from_chunk_paths(chunks)
    assert compress is False
    assert encrypt is True
