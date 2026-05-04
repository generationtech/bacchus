# Code purpose and implementation summary
_Exported on 5/3/2026 at 12:50:59 EDT from Cursor (3.2.16)_

---

**User**

Review this code in its entirety and summarize what its purpose is and how it does that.

---

**Cursor**

Exploring the repository structure and key files to summarize the project's purpose and implementation.



Here is a concise review of what **BACCHUS** is and how it is put together.

## Purpose

**BACCHUS** is a shell-based **backup and restore** tool for ad-hoc directory backups. It builds **multi-volume GNU tar archives**, then **compresses** (optional) and **encrypts** (optional) **each volume separately**. The README frames the design goal as: **smaller, portable chunks**, **privacy**, and **less catastrophic failure** than a single long compressed+encrypted stream—if one volume file is damaged, you are not necessarily stuck with “everything after the first bad byte is gone” the way you often are with one monolithic `.gz.gpg` stream.

Typical stack: **tar** (multi-volume), **pigz** (compression), **gpg** (AES-256, no extra compression inside gpg), plus **jo** / **jq** for a small JSON runtime state file and **tmpfs** for optional RAM-backed scratch space.

## How it does that

### Entry point and CLI

- **`bacchus.sh`** is the user-facing command. It loads **`scripts/include/common/bacchus-parsing.sh`**, which is **Argbash-generated** argument parsing (the sources live in **`source/bacchus.m4`** and **`source/bacchus-parsing.m4`**; see `README.md` for the exact `argbash` invocations).
- It defines **`backup`** and **`restore`** subcommands, maps flags into **`BCS_*`** environment variables, and collects a password from **file**, **`-p`**, or **interactive** prompt (or leaves encryption off if empty).
- **`PrintOptions`**, **`ConfirmStart`**, and optional ramdisk disabling when compression and encryption are both off mirror the behavior described in the header comments.

### Backup pipeline (`scripts/bacchus-backup.sh`)

1. Sets **`trap Cleanup EXIT`** (from **`scripts/include/common/cleanup.sh`**) to unmount a tmpfs ramdisk if used and remove temp paths.
2. Optionally mounts a **tmpfs** sized from **`BCS_VOLUMESIZE`** when compression or encryption needs fast scratch space (`BCS_RAMDISK`).
3. Estimates **how many volumes** will be needed from **`du`** and **`BCS_VOLUMESIZE`** (optional **`BCS_ESTIMATE`** output).
4. Initializes **`BCS_DATAFILE`** JSON via **`jo`** (destination, volume count, timestamps, running sizes for statistics).
5. Runs **`tar`** in **multi-volume create** mode (`-cpM`, POSIX format, `-L` volume size, **`--new-volume-script`** → **`scripts/include/backup/bacchus-backup-new-volume.sh`**). Each time tar finishes a volume, that helper runs.
6. After tar exits, it invokes the same new-volume helper once with **`TAR_FD=none`** so the **last** volume is compressed/encrypted and finalized like the others.

**Per-volume handler (`bacchus-backup-new-volume.sh`):**

- Loads stats from **`BCS_DATAFILE`** (**`Load_Persistence`** / **`jq`**).
- Can **pause** if destination filesystem free space is low and let the operator **change `bcs_dest`** (resume-friendly behavior).
- **`pigz -9c`** if **`BCS_COMPRESS`** is on; then **`gpg`** with **`--cipher-algo AES256`** and **`--compress-algo none`** if **`BCS_PASSWORD`** is set—i.e. **compress then encrypt**, no double compression inside gpg.
- Writes updated JSON back to **`BCS_DATAFILE`**; optional incremental/completion statistics modules print progress and ETA-style info.

### Restore pipeline (`scripts/bacchus-restore.sh`)

1. Discovers whether archives are **`.gz`** / **`.gpg`** from filenames and aligns **`BCS_COMPRESS`** / **`BCS_PASSWORD`** with reality.
2. Measures an effective volume size from the first archive via **`Process_Volume`** (`scripts/include/restore/process_volume.sh`).
3. Same **ramdisk** pattern as backup when intermediates are needed.
4. Optional **estimate** path uses **`compute_end.sh`** / **`print_estimate.sh`**.
5. Runs **`tar`** **multi-volume extract** (`-xpM`) with **`--new-volume-script`** → **`bacchus-restore-new-volume.sh`**, extracting into **`BCS_DEST`**.

**Per-volume restore helper:**

- If a volume file is missing, it can **prompt for a new source directory** and refresh estimates (similar to backup’s destination pause).
- **`Process_Volume`** reverses the pipeline: **gpg decrypt** (if needed) → **pigz decompress** (if needed) → leaves a plain **`tar`** segment for **`tar -x`** to consume.
- Updates **`BCS_DATAFILE`** after each volume.

### Cross-cutting pieces

- **`load_persistence.sh`**: reads the JSON state into shell variables.
- **`cleanup.sh`**: sync, unmount ramdisk, delete **`BCS_TMPFILE`**\* temps.
- **`duration_readable.sh`** and the **`incremental_stats` / `completion_stats`** includes: human-readable timing and progress reporting controlled by **`BCS_STATISTICS`**, **`BCS_RUNSTATISTICS`**, **`BCS_ENDSTATISTICS`**.

### Licensing

- **`LICENSE`** is **GPLv3**.

---

**In one sentence:** BACCHUS is a **tar multi-volume** backup/restorer that applies **pigz** and **gpg per volume**, keeps **JSON-backed runtime state** for stats and flexible stops (disk full / missing volume), and optionally uses **tmpfs** to avoid hammering disk for intermediates—documented as favoring **manageable files** and **fault isolation** between volumes compared to a single compressed encrypted archive stream.

---

**User**

I originally wrote this with the intention that I could easily recovey from a failed medium mid-way through the bnackup and then continue. I also envisioned being able to start the restore from any individual# backup file and proceed forward through subsequent file. Can you assess that possible existing or new code needed?

---

**Cursor**

Tracing backup/resume and restore entry points in the code to assess what's implemented versus what would require new behavior.



Here is an assessment tied directly to how the scripts behave today and what GNU tar allows.

## 1. Backup: recover from a failed medium and **continue**

### What already exists (live continuation)

In **`bacchus-backup-new-volume.sh`**, before each volume is compressed/encrypted and written, the script checks free space on `bcs_dest`. If space is low, it prompts and lets you set a **new destination path**; it updates **`bcs_dest`** in the JSON persistence file and adjusts timing stats when you resume. That is **in-process** continuation: **the same `tar` process** keeps running and later volumes go to the new location.

So the scenario “this disk/removable medium is full or bad — point at another path and keep going” is **partially** covered, as long as **`tar` never exits** and the failure is handled as “low space / operator intervenes” rather than a hard crash.

### What is **not** covered (restart after failure)

There is **no** design for “backup died or machine rebooted — rerun `bacchus` and attach to the **same** multi-volume archive”:

- **`--volno-file`** is under a **temporary** prefix (`BCS_TMPFILE.volno`); **`Cleanup`** removes `BCS_TMPFILE*`, so there is no durable checkpoint of “which volume number `tar` thought it was on.”
- Initial backup JSON sets **`bcs_dest`** from **`BCS_DEST`**, but **`bacchus-backup.sh` does not `Load_Persistence` at startup** to reuse a previous run’s changed destination or position.
- A new **`bacchus backup`** run starts a **new** `tar -c -M` over **`$BCS_SOURCE`** from the beginning; it does not resume the previous logical archive.
- With **`BCS_RAMDISK`**, unfinished raw tar segments live on **tmpfs** until the new-volume script finishes; a crash before that can lose work that never made it to durable `.gz`/`.gpg` files on **`bcs_dest`**.

So your original “easily recover … mid-way through the backup and then **continue**” is **only** met for **interactive path changes while one backup run is still alive**, not for **crash / kill / reboot / unplug** without redoing from scratch (for that run).

### New code / design (if you want true resume)

You would need something in the spirit of:

- **Durable state**: persist last completed volume index, paths, and possibly **`--volno-file`** outside the temp prefix that gets deleted on exit.
- **Explicit resume mode**: only if **GNU tar** can resume your chosen flow (multi-volume **create** resume is not a well-supported “one flag” story; you may need a different packaging model, e.g. **one independent archive per volume** or **append-only volume files** with a manifest).
- **Safer default for durability**: avoid ramdisk for the segment `tar` is still writing until it is flushed to final media, or sync explicit checkpoints.

That is a **non-trivial** product decision + tar semantics research, not a small patch.

---

## 2. Restore: start from **any** volume **N** and go forward

### What already exists (forward through **later** volumes in order)

Restore **always** starts with the **first** logical file:

```114:141:/run/user/1000/gvfs/sftp:host=metalshop,user=root/mnt/disk0/users/ken/programming/databackup.scripts/bacchus/scripts/bacchus-restore.sh
source="$bcs_source"/"$BCS_BASENAME".tar
Process_Volume "$BCS_BASENAME".tar "$BCS_DECRYPTDIR" "$BCS_COMPRESDIR"
...
tar "$tarargs" --format posix --new-volume-script "$scriptdir/include/restore/bacchus-restore-new-volume.sh" --volno-file "$BCS_TMPFILE".volno -f "$source" --directory "$BCS_DEST"
```

When **`tar`** needs the **next** volume, **`bacchus-restore-new-volume.sh`** can pause if the expected file is missing and let you change **`bcs_source`** (another directory / swapped medium), then continue. So **sequential** multi-volume restore with **media/path changes between volumes** is aligned with your intent.

### What is **not** implemented

- There is **no** option like “initial archive is `backupfile.tar-7`” — **`tar -f`** is always **`…/backupfile.tar`** (after `Process_Volume` turns it into a plain tar segment for `tar` to read).
- **`--volno-file`** is again **temporary**; there is no “resume restore after reboot from volume 5.”

### Conceptual limitation (even with new flags)

A **multi-volume `tar` archive is one byte stream** split at fixed boundaries. **`tar -x -M`** is meant to be fed **from volume 1 forward**. Starting cold at **`backupfile.tar-5`**:

- **`tar` generally cannot** treat that as a standalone full archive (volume 1 holds the start of the stream and archive metadata).
- You **cannot** recover a **complete** tree of all files from “volume N onward” only: anything whose bytes began on an earlier volume is incomplete or unavailable.

Per-volume **gzip + gpg** helps **isolate corruption** to one volume file, but it does **not** turn volumes into independent full backups; it only helps you **decrypt/decompress** later segments if you still have a **`tar` session** that is already in the right place in the logical stream.

So “start restore from **any** individual `#` file and proceed **forward**” is:

- **Reasonable** if you mean: “I start from **volume 1**, but volumes 2–K live on other disks and I **point at them when prompted**” — **already close** to what you have.
- **Not generally achievable** if you mean: “**skip** volumes 1–(N−1) and still do a normal full restore of everything” — that conflicts with **how multi-volume `tar` works**.

---

## Summary table

| Goal | Today | Gap |
|------|--------|-----|
| Swap destination / free space **during** backup | Yes — low-space prompt updates `bcs_dest` while `tar` runs | Only while the **same** backup process runs |
| Continue **same** backup after crash/reboot | No | Durable checkpoint + resume semantics (and likely ramdisk/tar interaction changes) |
| Restore with volumes on different media in sequence | Yes — missing-volume prompt can retarget `bcs_source` | No durable “resume restore” state |
| Begin restore at **`basename.tar-K`** without earlier volumes | No — hard-coded start at **`basename.tar`** | Would not fix GNU tar’s need for the **beginning** of the multi-volume stream for a full restore |

If you want to push the design toward your original vision, the next fork in the road is: **stay with multi-volume `tar`** and implement **durable volno + documented resume** (still limited by tar), versus **change the on-disk format** (e.g. one self-contained archive per chunk + manifest) so “resume” and “start from chunk K” become well-defined at the application layer. I can outline concrete flags and file layouts for either path if you say which tradeoff you prefer.

---

**User**

I need to be able to start, no restart, from volume X and then proceed to the end. Is that even possible to add to the current design?

---

**Cursor**

## Short answer

**Not in any useful sense**, if you mean: run restore (or “replay” the archive) **beginning at volume X’s bytes** and still treat it like one Bacchus backup through to the end — **with the current format (single multi-volume GNU `tar` stream split across files)**.

That isn’t a missing feature in your scripts; it’s how **multi-volume `tar`** works.

## Why the current design can’t support it

What you have on disk is **one continuous POSIX tar byte stream**, cut into pieces at **fixed size boundaries** (`-L`). Each piece is then optionally `.gz` / `.gpg`.

- Volume **X** (after decrypt/decompress) is **not** a standalone tar archive; it’s **middle of the stream**.
- **`tar -x -M`** is built to read that stream **from the first volume forward**. GNU tar’s own docs treat multi-volume extract as needing the volumes **in order from the start** — without the leading bytes, the reader cannot reliably interpret headers and members.

So “**start** from volume X” (skip volumes 1…X−1 entirely) is **not** something you can bolt on with `--volno-file`, a new flag, or a smarter `bacchus-restore-new-volume.sh`: you’d be handing `tar` a **truncated stream**.

## What *would* make “start at chunk X” possible

You’d need a **different on-disk contract**, for example:

- **Independent archives per chunk**: each volume is a **complete** `tar` (or cpio, etc.) plus a **manifest** (order, paths, optional full-tree index). Then “start at X” means “extract only volumes X…N” — knowing you only get **members wholly contained** in those chunks unless you also store **split-file records** in the manifest.
- Or **chunk = file-level or record-level** packaging instead of “slice one giant tar.”

That’s a **format / pipeline redesign**, not an incremental change to the present `tar -cM` / `tar -xM` flow.

## Narrow clarification

If what you actually need is **“volume X is on another disk; I’ll plug it in when `tar` asks”**, your design already moves that direction (prompt / change `bcs_source`). That still assumes **volume 1 is read first** and earlier volumes are **available when needed**, not skipped.

**Bottom line:** “Start from volume X and proceed to the end” **without** volumes 1…X−1 is **not** achievable while staying on **one multi-volume `tar`**; it **is** achievable only with a **new packaging model** where later chunks don’t depend on earlier bytes for decoding meaning.

---

**User**

Postulate on if it is even possible to do "run restore (or “replay” the archive) beginning at volume X’s bytes and still treat it like one Bacchus backup through to the end" by "Independent archives per chunk: each volume is a complete tar (or cpio, etc.) plus a manifest (order, paths, optional full-tree index)", and if so, what would it take to adjust the current code to work with that mode, taking full advantage of all the other quality of life niceties we have in the existing code, plus still support the current mode of operation 
(like a "use original mode" or "use new mode" command line feature flag

---

**Cursor**

Yes — **if** you redefine what a “volume” is so each one is a **self-contained archive** plus shared **manifest metadata**, then **starting restore at chunk X and processing X…N** is exactly what that format is for. Whether that matches your mental model of “the same Bacchus backup” depends on accepting one constraint: **you are no longer splitting one `tar` byte stream at arbitrary boundaries**, so **large single files** need an explicit policy.

Below is a concise postulate of feasibility and what it would take to add it **alongside** today’s mode behind a flag.

---

## Is “independent tar per chunk + manifest” enough?

**For “begin at volume X’s payload and go to the end”**: yes, **if**:

1. **Each chunk decodes to a valid, standalone archive** (e.g. one POSIX `tar` per chunk after decrypt/decompress).
2. Chunk boundaries are chosen so **no tar member is split across chunks** unless you add **another** mechanism (see large files below).
3. The **manifest** (or equivalent) tells restore **order**, **filenames**, and preferably **which paths live in which chunk** — so starting at X means “apply chunks **X…N** in order” without ever opening chunk `1…X−1`.

**What you do *not* get for free:** the **exact same bytes** as today’s single multi-volume stream; you get **the same tree** only if every path is covered **exactly once** across chunks and ordering/constraints are preserved.

**Large files (`>` one chunk budget)**  

Today, `tar -M` can split **inside** a file. With **one complete tar per chunk**, it cannot.

You must pick one of:

- **Cap**: refuse backup if any file exceeds max raw tar size for a chunk (simplest).
- **Split large files**: pre-split (e.g. `split`) and record parts + reassembly in the manifest (more code, full fidelity).
- **Per-file tar stream**: exotic and usually not worth it vs split.

So the new mode is **possible and clean**, but **not** a drop-in semantic duplicate of legacy `-M` for huge single files unless you implement split/reassemble.

---

## Dual-mode design (legacy vs chunked)

**CLI**  
Something like `--archive-mode legacy|chunked` (names like `--compat-multivolume` / `--file-aligned-chunks` also work). Default **`legacy`** preserves current behavior.

**Manifest**  
- **Minimum**: ordered list of chunk ids → output basename keys; global options (compression, cipher, basename, source root, optional `--sort=name`).
- **Better QoL**: per-chunk byte sizes, path prefixes or file lists, checksums, format/schema version.
- **Start-from-X without chunk 1**: manifest must be **reachable without chunk 1** — e.g. **duplicate** a small `manifest.json` on **every** removable volume, or a **header** inside each encrypted blob, or a sidecar the operator copies once.

**Backup (chunked mode)**  

Conceptually replace `tar -cM` + `new-volume-script` with:

1. Walk source in deterministic order (same spirit as `--sort=name`).
2. **Grow** a tar into a temp file (ramdisk or disk), adding whole files until adding the **next** whole file would exceed chunk budget **or** hit edge cases (symlinks/hardlinks — see below).
3. Finalize tar → same pipeline you already have: `pigz` → `gpg` → write to `dest` with stable naming (`basename.chunkNNN.tar.gz.gpg` or keep `.tar-NN` with a mode bit in manifest).
4. Append chunk record to manifest; optionally flush manifest to disk + replicas.

You keep: ramdisk option, low-disk prompts (between chunks), password modes, stats (per chunk instead of per `-M` slice), `jo`/`jq` persistence (extended schema).

**Restore (chunked mode)**  

1. Load manifest (from provided path or discovered header/sidecar).
2. If “start at X”: **skip** chunks `< X` in the ordered list.
3. For each chunk from X to N: decrypt/decompress (reuse **`Process_Volume`**-style logic), **`tar -x`** **once per chunk** into `BCS_DEST` (same exclusions/overwrite policy as today — likely `-x` with consistent flags).

You keep: missing-medium loop (path change per chunk), ramdisk, stats, cleanup traps — wired to **chunk loop** instead of `tar -xM` + `new-volume-script`.

**Hard links / special cases**  

Hard links spanning chunks are awkward (two paths, one inode). Typical approaches: **duplicate data** in later chunk with a manifest note, **reserve** linked paths for same chunk, or **normalize** to copies for chunked mode only. This is one place dual-mode needs explicit rules.

---

## What it would take to adjust **current** code

Rough layering (max reuse, minimal duplication):

| Area | Legacy | Chunked |
|------|--------|---------|
| CLI | Extend argbash `bacchus.m4` / parsing lib | New `--archive-mode` + optional manifest path / start chunk index |
| Backup driver | `bacchus-backup.sh` + `bacchus-backup-new-volume.sh` | New `bacchus-backup-chunked.sh` (or functions in same file behind `case`) |
| Restore driver | `bacchus-restore.sh` + `bacchus-restore-new-volume.sh` | New `bacchus-restore-chunked.sh` loop |
| Compress/encrypt | `pigz`/`gpg` in new-volume script | Shared shell functions extracted from current script |
| Persistence/stats | `BCS_DATAFILE` JSON | Same pattern; schema adds `mode`, `chunk_index`, manifest references |
| Cleanup/ramdisk | `cleanup.sh`, backup/restore ramdisk blocks | Reuse; chunk loop recomputes sizes from manifest or max chunk size |

**Estimate (order of magnitude):** moderate shell project — **new backup iterator + manifest read/write + dual entrypoints**, refactor **one** shared “finalize chunk” pipeline. Not trivial because chunked backup **replaces** `tar -M` orchestration; but **most** QoL is orthogonal.

---

## Bottom line

- **Possible:** Yes — **chunked independent tars + manifest** is the standard way to make **“start at X, go to end”** well-defined.
- **Same as today’s semantics:** Only if you accept **file-aligned chunks** and a policy for **oversized files** (cap vs split).
- **Dual mode:** Straightforward with a **mode flag**, branching early in `bacchus-backup.sh` / `bacchus-restore.sh`, sharing crypto/compress/stats/cleanup.

If you want to implement it later, the first locked-down decisions should be: **manifest transport** (every-volume copy vs sidecar), **chunk naming**, and **large-file policy** — everything else can follow the patterns you already use in this repo.

---

**User**

I would be OK if the per-volume size needed to exceed the requested value because a particular file is too big, within an abolute maximum size. So if my desired size if 500MB and I set an absolute size of 4GB, then a 5GB file with need to span two volumes. In that case, I would want the script to handle that segement of the backup to be a "mini" multifile tar instance, and then past the multiple volumes needed to backup the 5GB file, it would go back to one-tarfile-per-volume using the desired size

---

**Cursor**

Your rule set is coherent, and it fits a **three-tier chunking model**: normal **single-tar chunks** (size-guided), **single-tar chunks stretched past the target up to an absolute cap** for one huge member, and **occasional embedded GNU `tar -M` runs** when one member exceeds the cap. Below is how that hangs together and what the tooling must record.

## Tier 1 — “Nominal” chunks (target ~500 MB)

Walk the tree in a fixed order (same spirit as today’s `--sort=name`). Append **whole files** to the current tar until the **next** whole file would push the **closed** tar past your **desired** size. Close tar → compress → encrypt → manifest entry (`standalone`).

## Tier 2 — “Stretch” chunk (desired < size ≤ absolute max, e.g. 4 GB)

If the **next file alone** is larger than the remaining budget for the **desired** target but **≤ absolute max**, you **do not split the file**: you put it in **one** standalone tar (that chunk may be >500 MB). Optionally you can still merge smaller trailing files into that same tar if they fit under the absolute max — policy choice; simplest rule is “this chunk is dominated by one oversize member.”

That matches: *OK if per-volume size exceeds requested because one file forces it, as long as ≤ absolute max.*

## Tier 3 — “Mini” multi-volume `tar` for one member > absolute max (e.g. 5 GB file, cap 4 GB)

When a **single file** (or symlink policy aside, “single archive member”) exceeds **absolute max** unstored size:

1. **Flush** the current open standalone tar if it has any members (so you don’t mix modes inside one file).
2. Run an **inner** `tar -cM -L <slice_kb> -f …` over **only that file** (and nothing else), producing `mini.tar`, `mini.tar-2`, … as raw slices.
3. Each slice goes through the **same** pigz + gpg pipeline as today’s volumes (so operational behavior stays familiar).
4. On restore, that sequence is **one logical extract**: `tar -xM` (or equivalent) over **only those slices**, not `tar -x` per slice.

So your “mini multifile tar instance” is exactly **scoped multi-volume create/extract** for that oversize member only; afterward you return to **one standalone tar per chunk** subject again to desired + absolute rules.

**Slice size for the mini run:** Use something aligned with your nominal chunking (e.g. same `-L` as 500 MB target in KB) or a dedicated constant; it only affects how many `.tar-N` pieces exist for that big file, not correctness.

## Manifest (required so restore knows which mode to use)

Each stored blob needs metadata so restore never guesses wrong:

- **`standalone`**: one blob → one `tar -x`.
- **`mv_group`**: ordered list of blob ids (same order as `tar -M` expects), shared `group_id`, `member_index` / `member_count` if you ever allow multiple MV groups in one backup.

Restore algorithm:

- For each manifest entry in order: if `standalone`, decrypt/decompress/extract once; if `mv_group`, run **one** multi-volume extract across the listed blobs, then continue.

Starting restore at **volume X** (in your future chunked design) becomes: skip manifest entries before X; if you skip into the **middle** of an `mv_group`, that remains **invalid** unless you also support partial MV groups (you shouldn’t advertise that — same as classic tar).

## Interaction with current Bacchus

- **Legacy mode** (`tar -M` for the whole tree): unchanged.
- **New mode**: implements the **state machine** above plus manifest; **reuses** password handling, ramdisk, prompts, stats shape, cleanup — replaces only the **driver** that currently assumes one global `-M` stream.

## Practical nuances (worth deciding up front)

1. **Sparse files**: size seen by `stat` vs bytes on disk — define whether “file too big” uses logical size (usually yes for backup intent).
2. **Trailing partial chunks**: after an MV group, open a **new** standalone tar for following files.
3. **Only one huge file in an MV group**: keeps restore simple; don’t mix multiple pathnames in one inner `-M` unless you need to (not required for your 5 GB example).

So yes: your desired behavior — **stretch single tar up to absolute max**, then **fallback to a bounded mini `tar -M` only for that huge member**, then **back to one-tar-per-chunk** — is **possible** and is a standard way to combine **file-aligned chunks** with **faithful handling of monster files** without abandoning the rest of the design.

