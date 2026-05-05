"""Heavy full-disk E2E (~500 MiB): runs on every ``pytest`` invocation."""

from __future__ import annotations

from tests.integration._e2e_impl import E2EConfig, run_e2e


def test_e2e_default_500mb() -> None:
    assert run_e2e(E2EConfig()) == 0
