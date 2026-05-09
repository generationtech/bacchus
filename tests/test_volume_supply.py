"""Tests for :mod:`bacchus.volume_supply`."""

from __future__ import annotations

import pytest

from bacchus.volume_supply import artifact_path, chunk_seq_from_member


def test_chunk_seq_from_member() -> None:
    assert chunk_seq_from_member("test.000017.tar", "test") == 17
    assert chunk_seq_from_member("backupfile.000001.tar", "backupfile") == 1


def test_chunk_seq_from_member_rejects() -> None:
    with pytest.raises(ValueError):
        chunk_seq_from_member("other.000001.tar", "test")


def test_artifact_path_orders_suffixes(tmp_path) -> None:
    src = tmp_path
    member = "x.000001.tar"
    assert artifact_path(src, member, False, "").suffix == ".tar"
    assert artifact_path(src, member, True, "").name == "x.000001.tar.gz"
    assert artifact_path(src, member, True, "pw").name == "x.000001.tar.gz.gpg"
