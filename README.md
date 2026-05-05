# BACCHUS

Creates multi-volume backups, optionally compressing (**pigz**) and encrypting (**gpg**) **each volume or chunk separately**. Chunked mode (default) writes **self-contained tar chunks** plus optional **Tier-3 GNU tar multi-volume “mini” runs** for single members larger than an absolute cap. Legacy mode preserves the original **single `tar -cM` stream** layout for compatibility with older backups.

## Requirements

- Python **3.9+**
- **GNU tar**, **pigz** (optional if compression disabled), **gpg** (optional if encryption disabled)
- For **legacy ramdisk** or **chunked ramdisk**: ability to `mount` **tmpfs** (typically root)

## Install (development)

```bash
pip install -e .
# or without install:
./bacchus --help
# equivalent:
PYTHONPATH=src python3 -m bacchus --help
```

The `bacchus` console script is registered when installing the package (`pip install -e .`).

## Usage

```bash
bacchus --help
bacchus backup --help
bacchus restore --help
```

### Archive modes

- **`chunked` (default for backup)**  
  Chunks are named `basename.NNNNNN.tar` (optional `.gz`, `.gpg`). Restore detects standalone vs multi-volume slices by inspecting tar bytes (no manifest).

- **`legacy`**  
  Same on-disk layout as Bacchus 1.x: `basename.tar`, `basename.tar-2`, …

On **restore**, if `--archive-mode` is omitted, Bacchus infers the mode from filenames. If both layouts are present, pass `--archive-mode` explicitly.

### Notable new flags

| Flag | Meaning |
|------|---------|
| `--archive-mode chunked\|legacy` | Backup/restore driver |
| `--absolute-max-size kB` | Chunked backup: max single chunk before Tier-3 mini `tar -cM` (default: `8 × --volumesize`) |
| `--mini-slice-size kB` | Chunked backup: `-L` for inner `tar -cM` (default: `--volumesize`) |
| `--start-chunk N` | Chunked restore: begin at chunk index `N` (1-based) |

### Chunked progress (bash-style per “volume”)

Chunked backup and restore print **one line per shipped chunk** (`basename.NNNNNN.tar`), similar to the legacy bash per-volume log:

- **`-S on` (default), `-W off`:** print the chunk filename only after each chunk.
- **`-S on`, `-W on` (default):** print the full incremental statistics line (remain / elapsed / compression / sizes / timestamp), matching the legacy `volume_hook` layout.
- **`-S off`:** suppress those per-chunk lines (and chunked completion summary that depends on `-X`; use **`-X off`** to silence the “OPERATION COMPLETE” block as well).

Tier‑3 inner `tar -cM` slices are logged the same way (hook + final ship), so output stays consistent whether or not Tier‑3 ran.

### Legacy shell implementation

The original bash + argbash sources live under [`legacy/`](legacy/) for reference or emergency use:

- `legacy/bacchus.sh`
- `legacy/scripts/`
- `legacy/source/`

## Tests

```bash
pip install -e '.[dev]'
PYTHONPATH=src python3 -m pytest tests/ -q
```

### Full E2E (chunked + Tier‑3 + restore verify)

`tests/test_e2e_full.py` always runs a **~500 MiB** random tree through real `python -m bacchus` backup/restore when you run `pytest`. For a smaller manual run, use `--total-bytes` on the CLI (see below).

Run the same flow from the CLI (writes under `$TMPDIR` by default):

```bash
PYTHONPATH=src python3 -m tests.integration.run_e2e --help
```

On failure, the implementation prints paths to the source tree, backup chunks, and restore output under the workdir and leaves them in place for inspection.

## License

GPL-3.0-or-later (see [LICENSE](LICENSE)).
