"""Heavy full-disk E2E (500 MiB default); skipped when ``BACCHUS_SKIP_E2E=1``."""

from __future__ import annotations

import os

import pytest

from tests.integration._e2e_impl import E2EConfig, run_e2e


def test_e2e_default_500mb() -> None:
    if os.environ.get("BACCHUS_SKIP_E2E") == "1":
        pytest.skip("BACCHUS_SKIP_E2E=1")
    assert run_e2e(E2EConfig()) == 0
