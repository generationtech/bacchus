# Testing

This document describes how the Bacchus test suite is organized, what it covers, and how to run it locally or in CI.

## Prerequisites

Install the package in editable mode with the development extra (pulls in **pytest**):

```bash
pip install -e '.[dev]'
```

Runtime tools exercised by the tests (install via your OS package manager where needed):

| Tool | Used by |
|------|---------|
| **Python** 3.9+ | All tests |
| **GNU tar** | Backup/restore, classification, E2E |
| **pytest** | Test runner (`dev` extra) |
| **rsync** | Optional: full E2E checksum mirror step (skipped with a stderr message if missing) |
| **pigz** | Tests that enable compression |
| **gpg** | Tests that enable encryption (not all E2E paths) |

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["src"]`, so you do not need to set `PYTHONPATH` when running `pytest` from the repository root.

## Run everything

From the repository root:

```bash
pytest
```

Quiet summary:

```bash
pytest -q
```

Run a single file or test:

```bash
pytest tests/test_stats.py
pytest tests/test_stats.py::test_fmt_kb_scaled
```

## Layout and what each area covers

| Path | Role |
|------|------|
| [`tests/test_stats.py`](../tests/test_stats.py) | Incremental stats lines, completion summaries, progress/compression formatting |
| [`tests/test_persistence.py`](../tests/test_persistence.py) | Runtime state / persistence helpers |
| [`tests/test_classify.py`](../tests/test_classify.py) | Tar segment classification (standalone vs GNU multi-volume) |
| [`tests/test_backup_chunked.py`](../tests/test_backup_chunked.py) | Chunked backup pipeline edge cases |
| [`tests/test_restore_sizing.py`](../tests/test_restore_sizing.py) | Restore sizing and estimates |
| [`tests/test_restore_transport_inference.py`](../tests/test_restore_transport_inference.py) | Inferring archive transport (e.g. compression) from on-disk names |
| [`tests/test_volume_supply.py`](../tests/test_volume_supply.py) | Volume/chunk supply logic |
| [`tests/test_walk.py`](../tests/test_walk.py) | Source tree walking |
| [`tests/test_ramdisk.py`](../tests/test_ramdisk.py) | Ramdisk / tmpfs related behavior (where applicable) |
| [`tests/test_extern_tar.py`](../tests/test_extern_tar.py) | Interaction with external `tar` |
| [`tests/test_e2e_chunked.py`](../tests/test_e2e_chunked.py) | **Integration:** small chunked roundtrips via `python -m bacchus` (including a symlink case) |
| [`tests/test_e2e_full.py`](../tests/test_e2e_full.py) | **Heavy E2E:** large random tree, Tier-3 multi-volume check, restore, tree hash verify, regular-file counts, optional `rsync` checksum dry-run |
| [`tests/test_e2e_defaults_mirror.py`](../tests/test_e2e_defaults_mirror.py) | **CLI-defaults E2E:** `pigz` on, volume size 100000 KiB, estimates/statistics on; `-C off` / `-u off` only for automation (see [`E2ECliDefaultsMirrorConfig`](../tests/integration/_e2e_impl.py)); skips if `pigz` missing |
| [`tests/integration/_e2e_impl.py`](../tests/integration/_e2e_impl.py) | Shared E2E implementation (`E2EConfig`, `run_e2e`, `verify_match`, rsync step) |
| [`tests/integration/run_e2e.py`](../tests/integration/run_e2e.py) | CLI to run the full E2E outside pytest (useful for debugging) |

## Full E2E (`test_e2e_full`)

`tests/test_e2e_full.py` runs on a normal `pytest` invocation. It:

1. Builds a **pseudorandom directory tree** (default **~500 MiB** total data; see `E2EConfig` in [`_e2e_impl.py`](../tests/integration/_e2e_impl.py)).
2. Runs **real** `python -m bacchus backup` in **chunked** mode with parameters that force **Tier-3** inner GNU multi-volume behavior for some members.
3. Asserts that at least one decoded chunk contains a **multi-volume continuation** header (Tier-3 coverage).
4. Runs **restore** to a fresh directory.
5. Compares source vs restored tree with **`verify_match`** (relative paths, SHA-256 for regular files, symlink metadata).
6. Asserts **regular file counts** match (semantics similar to `find -type f`).
7. If **`rsync` is on `PATH`**, runs a **dry-run** with checksums and itemized output; empty output means no diff. If `rsync` is absent, this step is **skipped** and a line is printed to **stderr** (the rest of the E2E still must pass).

On failure, the harness prints paths to the workdir, source tree, chunks, and restore output; use `--keep-on-success` on the CLI runner to retain artifacts after a successful run as well.

## Manual E2E CLI

Same flow as the heavy pytest case, with tunable size and options:

```bash
python3 -m tests.integration.run_e2e --help
```

Examples:

```bash
# Smaller, faster run
python3 -m tests.integration.run_e2e --total-bytes $((50 * 1024 * 1024)) --keep-on-success

# Reproducible tree
python3 -m tests.integration.run_e2e --seed 12345
```

## CI and optional tools

- The suite is designed to pass on a typical Linux image with **Python**, **tar**, and **pytest**. **rsync** improves confidence of the E2E mirror check but is not required for a green run.
- If you add CI, install **tar** at minimum; add **rsync** if you want the checksum dry-run to execute every time.

## Reporting failures

When opening an issue, include the **pytest** command, **Python version**, and relevant **stdout/stderr**. For E2E failures, attach or quote the printed workdir paths and the failing assertion message.
