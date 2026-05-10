# Bacchus

**Multi-volume tar backup and restore** for large trees, with optional **per-chunk compression** (pigz) and **per-chunk encryption** (gpg). Bacchus is aimed at workflows where each chunk is a manageable file for removable media, remote sync, or archival storage.

- **Project:** Python package (`bacchus`), GPLv3+ (see [LICENSE](LICENSE)).
- **Status:** Maintained by the original author; suitable for production-style backups when you validate restore paths that matter to you.
- **Documentation:** this file for overview and usage; [docs/TESTING.md](docs/TESTING.md) for the test suite.

## Features

- **Chunked archives**  
  Self-contained chunks named `basename.NNNNNN.tar`, optionally suffixed with `.gz` and/or `.gpg`. Restore inspects tar bytes to distinguish standalone members from GNU multi-volume slices—**no separate manifest file**.

- **Tier-3 large-file handling**  
  Files that would exceed a configured **absolute max chunk size** are packed with an inner **GNU `tar -cM`** (“mini” multi-volume) run so a single logical file can span inner volumes while outer chunks stay bounded.

- **Operational controls**  
  Chunk size, intermediate directories, ramdisk (tmpfs) for heavy compress/encrypt paths, estimates, confirmations, and **statistics** hooks (per-chunk progress lines).

- **Path layout options (backup)**  
  `--archive-path-scope` (member paths relative to source’s parent vs source root) and `--archive-top-dir` for a stable top-level directory name inside the archive.

## Requirements

| Component | Notes |
|-----------|--------|
| **Python** | 3.9 or newer |
| **GNU tar** | Required for backup/restore |
| **pigz** | Optional if compression is disabled (`-z off`) |
| **gpg** | Optional if encryption is disabled (`-u off` and no password) |
| **tmpfs / mount** | Used when ramdisk is enabled for compress/encrypt intermediates (typically needs appropriate privileges) |

For **developers** running the full test suite, see [docs/TESTING.md](docs/TESTING.md) (including optional **rsync** for an extra E2E checksum check).

## Install

**From a clone (recommended for development):**

```bash
pip install -e .
```

This installs the `bacchus` console script (see `pyproject.toml`).

**Run without installing:**

```bash
PYTHONPATH=src python3 -m bacchus --help
```

Or use the wrapper script if present in your tree root:

```bash
./bacchus --help
```

**Development dependencies** (pytest):

```bash
pip install -e '.[dev]'
```

## Quick start

```bash
bacchus backup --help
bacchus restore --help
```

Typical backup (adjust paths and sizes for your environment):

```bash
bacchus backup \
  -s /path/to/data \
  -d /path/to/archive/output \
  -b mybackup \
  -v 100000 \
  -t /path/to/tardir \
  -c /path/to/compdir \
  -z on \
  -u off
```

Restore into an empty or dedicated destination (restore expects chunked chunk files for `mybackup` under the source directory):

```bash
bacchus restore \
  -s /path/to/archive/output \
  -d /path/to/restored \
  -b mybackup \
  -e /path/to/decrypttmp \
  -z on \
  -u off
```

Use `-C off` for non-interactive runs (skips “Press enter to begin”). Tar verbose mode and password sources are documented under `bacchus backup --help`.

## Archive layout and flags

Backup and restore use **chunked** archives only:

| Output | Pattern |
|--------|---------|
| Chunks | `basename.NNNNNN.tar` [`.gz`] [`.gpg`] |

| Flag | Meaning |
|------|---------|
| `-v` / `--volumesize` | Target chunk size (KiB) |
| `--absolute-max-size` | Max single outer chunk (KiB) before Tier-3 inner multi-volume (default: 8 × volumesize) |
| `--mini-slice-size` | Inner `tar -cM` `-L` value (KiB); default: volumesize |
| `--start-chunk` | Restore only from this 1-based chunk index onward |

### Progress and statistics

With **statistics** enabled (see `-S`, `-W`, `-X` in `--help`):

- Backup/restore can print **one line per shipped chunk**, including incremental fields (remain, elapsed, compression estimate, scaled sizes, timestamp) aligned for logging.
- Tier-3 inner multi-volume slices follow the same hook behavior so logs stay consistent.

## Security and passwords

- Prefer **no password on the command line** in shared histories; use interactive prompts or a protected file if you must automate (`-f`), understanding the risk of leaks.
- Encryption applies **per chunk** when enabled; treat keys and passwords like any other secret material.

## Historical bash implementation (Bacchus 1.x layout)

The original bash and argbash implementation—including the older **single-stream** multi-volume layout (`basename.tar`, `basename.tar-2`, …)—remains under [`legacy/`](legacy/) for reference or if you need that format. The **Python CLI does not implement that layout**; use the scripts in `legacy/` for those archives.

## Testing

See **[docs/TESTING.md](docs/TESTING.md)** for:

- How to run **pytest** and target subsets
- What each test module covers
- The **heavy E2E** (~500 MiB) and the **`run_e2e`** CLI
- Optional **rsync** checksum verification

Short version:

```bash
pip install -e '.[dev]'
pytest
```

## Contributing

Issues and pull requests are welcome. Please run the test suite before submitting changes and describe backup/restore scenarios you exercised. For test layout and commands, use [docs/TESTING.md](docs/TESTING.md).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
