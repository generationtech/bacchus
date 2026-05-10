"""
E2E: backup → restore → verify using CLI flags that mirror normal defaults.

Compression stays on (requires pigz). Confirm and password prompts are disabled for CI.
See ``E2ECliDefaultsMirrorConfig`` in ``tests/integration/_e2e_impl.py``.
"""

from __future__ import annotations

import shutil

import pytest

from tests.integration._e2e_impl import E2ECliDefaultsMirrorConfig, run_e2e_cli_defaults_mirror


@pytest.fixture
def require_pigz_and_tar() -> None:
    if not shutil.which("tar"):
        pytest.skip("GNU tar not found")
    if not shutil.which("pigz"):
        pytest.skip("pigz not found (required for default -z on)")


def test_cli_defaults_mirror_backup_restore_verify(require_pigz_and_tar) -> None:
    cfg = E2ECliDefaultsMirrorConfig(
        total_bytes=16 * 1024 * 1024,
        n_files=14,
        seed=42,
    )
    assert run_e2e_cli_defaults_mirror(cfg) == 0
