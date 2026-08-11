# TCBP Plugin Authoring Guide

This document is a guide for developers who want to create or maintain plugins
that run under a TCBP (Total Commander Batch Python) `plugin = "..."` Job. For
general TCBP usage, see `README_en.md` (Chapter 5) in the parent folder — this
document focuses on the plugin **author's** perspective.

> **Requirement:** TCBP runs on Python 3.11 or later (see `README_en.md`). The
> skeleton code in this document likewise uses 3.10+ syntax such as `str |
> None` and `list[str]`, so it won't work as-is on an older interpreter.

## 1. Table of Contents

- [1. Table of Contents](#1-table-of-contents)
- [2. TCBP Plugin Overview & Concepts](#2-tcbp-plugin-overview--concepts)
  - [2.1 `tool` vs `plugin`](#21-tool-vs-plugin)
  - [2.2 Design Principles](#22-design-principles)
  - [2.3 Session Types — FileSession / BatchSession](#23-session-types--filesession--batchsession)
  - [2.4 Processing Flow Overview](#24-processing-flow-overview)
- [3. API Specification](#3-api-specification)
  - [3.1 The `@plugin(...)` Decorator and `PluginInfo`](#31-the-plugin-decorator-and-plugininfo)
  - [3.2 `FileSession`](#32-filesession)
  - [3.3 `BatchSession`](#33-batchsession)
  - [3.4 Return Value Contract — `ExecResult` / `BatchResult`](#34-return-value-contract--execresult--batchresult)
  - [3.5 `session.log()` and Slot Rules](#35-sessionlog-and-slot-rules)
  - [3.6 `session.params` and Type Coercion](#36-sessionparams-and-type-coercion)
  - [3.7 Declaring a Plugin Job in config.toml](#37-declaring-a-plugin-job-in-configtoml)
  - [3.8 What You Can Import from `tcbp`](#38-what-you-can-import-from-tcbp)
- [4. Basic Structure of a Plugin Python Program](#4-basic-structure-of-a-plugin-python-program)
  - [4.1 File Location and Naming Rules](#41-file-location-and-naming-rules)
  - [4.2 Skeleton — FileSession Plugin](#42-skeleton--filesession-plugin)
  - [4.3 Skeleton — BatchSession Plugin](#43-skeleton--batchsession-plugin)
  - [4.4 Standalone CLI Entry Point Rules](#44-standalone-cli-entry-point-rules)
  - [4.5 Declaring Dependencies (`requirements`)](#45-declaring-dependencies-requirements)
  - [4.6 Writing Tests](#46-writing-tests)
- [5. Technical Notes](#5-technical-notes)
  - [5.1 Two-Stage Fail-Fast Validation](#51-two-stage-fail-fast-validation)
  - [5.2 Validation Strength With/Without pydantic](#52-validation-strength-withwithout-pydantic)
  - [5.3 The log() Slot Reservation Mechanism in Parallel Mode](#53-the-log-slot-reservation-mechanism-in-parallel-mode)
  - [5.4 The `--strict` Flag](#54-the---strict-flag)
  - [5.5 BatchSession Progress-Output Rules](#55-batchsession-progress-output-rules)
  - [5.6 Exceptions vs. Return Values — When to Use Which](#56-exceptions-vs-return-values--when-to-use-which)
  - [5.7 dry-run Behavior](#57-dry-run-behavior)
  - [5.8 Sessions Are Read-Only](#58-sessions-are-read-only)
  - [5.9 Common Mistakes Checklist](#59-common-mistakes-checklist)
  - [5.10 Thread Safety of Plugin Code in Parallel Mode](#510-thread-safety-of-plugin-code-in-parallel-mode)

---

## 2. TCBP Plugin Overview & Concepts

### 2.1 `tool` vs `plugin`

A TCBP Job specifies how a file (or a group of files) is processed in one of
two ways.

| | `tool = "..."` | `plugin = "..."` |
|---|---|---|
| Processing logic | External CLI executable (via `subprocess`) | A Python function in `./plugin/<name>.py` |
| Target | Existing executables such as GraphicsMagick, oxipng | Processing implemented directly in Python |
| `commands` key | Required | Not used (a warning if present) |

`tool` and `plugin` cannot be set on the same Job at the same time — if both
are specified, tcbp.py aborts immediately with an error.

### 2.2 Design Principles

The separation-of-concerns principle that runs through all of TCBP applies to
plugins as well.

1. **File selection is Total Commander's job, batch orchestration is TCBP's
   job, and the actual processing of a file (or group) is the tool's or
   plugin's job.** Plugins do not implement file-list discovery, wildcard
   expansion, or recursive traversal — Total Commander (file selection) and
   TCBP (reading/iterating the list) have already handled that.
2. **File objects are never passed across the interface.** A plugin always
   receives only a file's path (`str`) and parameters (`dict`). Both
   `FileSession.input`/`output` and every element of `BatchSession.filelist`
   are plain `str` values (never a `Path` object or a file handle).
3. **A plugin must also be runnable as a standalone CLI without tcbp** (see
   Chapter 4). This lets plugin development/debugging be verified quickly, one
   file at a time (or, for BatchSession, one list file at a time), without
   going through the whole tcbp pipeline.

### 2.3 Session Types — FileSession / BatchSession

A plugin is written as one of two types, depending on its unit of processing.

| | FileSession | BatchSession |
|---|---|---|
| Processing unit | A single file | The entire file list |
| Entry-function signature | `run(session: FileSession) -> ExecResult` | `run(session: BatchSession) -> BatchResult` |
| `parallel` | Supported (concurrent up to `max_workers`) | Ignored (always sequential — silently ignored even if enabled) |
| `output` | Required | Optional (`output = ""` or the key omitted entirely) |
| Representative examples | `remove_bom`, `mozjpeg`, `bmp2png` | `group_md5` |

Choose FileSession when each file can be processed independently. Choose
BatchSession when files must be considered together as a group to produce a
result (e.g., grouping by filename similarity and producing one output per
group).

### 2.4 Processing Flow Overview

```
Total Commander (file selection, passes the list via %UL)
        │
        ▼
tcbp.py  ── resolves the Job definition from config.toml
        │     (plugin = "name" → deterministically loads ./plugin/<name>.py)
        ▼
PluginJobExecutor  ── decides dry-run or not, calls run(), converts
        │             exceptions into a result value
        ▼
run(session) in plugin/<name>.py ── the actual file-processing logic
        │
        ▼
Returns ExecResult (FileSession) or BatchResult (BatchSession)
        │
        ▼
tcbp.py ── tallies success/failure, prints to console/log
```

There is no separate plugin discovery/registration mechanism. `plugin =
"resize"` always maps deterministically to `./plugin/resize.py`; when a Job is
resolved, TCBP only checks whether that file exists.

---

## 3. API Specification

### 3.1 The `@plugin(...)` Decorator and `PluginInfo`

A plugin's entry-point function must be named `run`, and must be wrapped with
the `@plugin(...)` decorator provided by `tcbp` to attach its metadata.

```python
from tcbp import plugin

@plugin(
    name="remove_bom",       # Plugin identifier (usually kept identical to the filename)
    contract_version="1.0",  # The contract version this plugin targets (required, see below)
    version="1.0",
    author="...",
    session_type="file",     # "file" | "batch" (see 2.3)
    requirements=[],         # List of required external packages (see 4.5). Default []
    notes_per_file=0,        # Number of log() slots used per file under FileSession + parallel. Default 0
    thread_safe=True,        # Whether the plugin is thread-safe under FileSession + parallel. Default True (see 5.10)
)
def run(session):
    ...
```

The values passed to `@plugin(...)` are validated internally as `PluginInfo`
(a frozen dataclass).

```python
@strict_dataclass(frozen=True)
class PluginInfo:
    name: str
    contract_version: str
    version: str
    author: str
    session_type: Literal["file", "batch"]
    requirements: list = []
    notes_per_file: int = 0
    thread_safe: bool = True
```

If `session_type` is given a value other than `"file"`/`"batch"`, or any field
has the wrong type, an exception is raised **immediately at plugin import
time**, when the decorator is evaluated (see the fail-fast discussion in 5.1)
— long before the Job actually runs, and even before that, at
`validate_config.py`'s pre-flight check stage.

#### `contract_version` — the plugin contract version (required)

`contract_version` is a different concept from `bmp2png`/`mozjpeg`/`group_md5`/
`remove_bom`'s own `version` (the plugin author's own version number) — it's a
`"MAJOR.MINOR"` string (e.g. `"1.0"`) declaring the version of the **shape of
`FileSession`/`BatchSession`/`PluginInfo` themselves**, and it's independent of
TCBP's own product version (`pyproject.toml`).

Every time `load_plugin()` imports a plugin, it compares this value against
the contract version TCBP currently implements:

- **A different MAJOR is rejected immediately** — meaning a change happened
  that breaks existing plugins (a removed field, a changed type, etc.).
- **The same MAJOR but a declared MINOR greater than TCBP's is rejected** —
  meaning the plugin requires a contract feature this TCBP version doesn't
  have yet.
- **The same MAJOR with MINOR equal or lower passes** — meaning TCBP has only
  added backward-compatible fields since, so there's no issue.

In practice, you only need to bump this value when the contract genuinely
breaks (which isn't common) — otherwise leave it as-is. An invalid
`"MAJOR.MINOR"` format or an incompatible value is rejected on the spot with a
`TcbpError` from `load_plugin()` — the same plugin-import-time fail-fast as a
typo'd `session_type`.

### 3.2 `FileSession`

The argument received by a plugin that processes a single file. Its fields
are read-only (aside from calling `log()`).

```python
@strict_dataclass(frozen=True)
class FileSession:
    input:  str    # Absolute path of the input file
    output: str    # Absolute path of the output file (already substituted from the job.output template)
    itemid: int    # 1-based per-file sequence number (this file's position within the batch)
    taskid: str    # A shared temp ID generated once for the whole batch (string)
    params: dict   # Merge of job.params (type-declared ones coerced) and job.defaults (see 3.6)

    def log(self, text: str, slot: int = 0) -> None: ...
```

> **Note:** `session.itemid` is a 1-based per-file sequence number (an
> integer). It shares a name with, but is unrelated to, config.toml's
> `{itemid}` placeholder (a freshly generated random string used for temp
> filenames) — don't confuse the two.

### 3.3 `BatchSession`

The argument received by a plugin that processes an entire group of files at
once.

```python
@strict_dataclass(frozen=True)
class BatchSession:
    filelist: list       # list[str] — absolute paths TCBP has already read and confirmed exist
    output:   str | None # None if job.output is empty
    taskid:   str
    params:   dict

    def log(self, text: str, slot: int = 0) -> None: ...
```

`filelist` is not "the path to the list file" — it is a list of absolute-path
strings that TCBP has already read from the list file and already confirmed
exist. A plugin does not need to re-check file existence (though it should
still handle the ordinary exceptions that can occur if a file disappears
during actual processing, since existence can't be guaranteed to hold for the
entire run).

> **Note:** `BatchSession.output` means something different from
> `FileSession.output`. `FileSession.output` is a fully substituted absolute
> path string, with per-file placeholders like `{dir}`/`{base}` already
> resolved. `BatchSession`, by contrast, isn't tied to a single file, so there
> is no file to resolve those per-file placeholders against in the first
> place — so whenever `job.output` isn't empty, it is passed through
> **completely unsubstituted, exactly as written in the TOML** (e.g., the
> literal string `"{dir}/report.txt"`). If you want to use this value as an
> actual path, the plugin itself has to interpret or substitute it. The
> bundled BatchSession plugin (`group_md5`) never touches this field at all
> and always declares `output = ""` (→ `None`) — unless your new BatchSession
> plugin genuinely needs `output`, it's recommended to leave it empty the
> same way.

### 3.4 Return Value Contract — `ExecResult` / `BatchResult`

Instead of the implicit rule "no exception means success," plugins report
success/failure via an **explicit return value**.

```python
@strict_dataclass(frozen=True)
class ExecResult:
    success: bool
    message: str = ""

@strict_dataclass(frozen=True)
class BatchResult:
    succeeded: list = []   # List of successfully processed file paths
    failed:    list = []   # List of failed file paths
```

- FileSession: `run(session: FileSession) -> ExecResult`
- BatchSession: `run(session: BatchSession) -> BatchResult`

TCBP does not enforce that `BatchResult.succeeded + failed` covers the whole
of `session.filelist` (i.e., some files may be silently skipped). That said,
the "succeeded/failed" counts in the summary log directly reflect the lengths
of these two lists, so it's recommended that every file you actually process
end up in one of them.

**If an exception escapes `run()`,** TCBP catches it right there and
synthesizes a result as follows.

- FileSession: `ExecResult(success=False, message=str(exc))`
- BatchSession: a `BatchResult` with the entire `session.filelist` filled into
  `failed` (any partial-success information the plugin may have accumulated
  before the exception is discarded)

In other words, **an exception from `run()` should be reserved for a
catastrophic situation where this file/Job can no longer be trusted at all.**
For expected partial failures within the processing target (e.g., one
corrupted file within a group), the convention plugin authors are expected to
follow is to report them in structured form via the return value.
`group_md5` is the reference example of this pattern — inside its per-group
loop, individual file failures are caught with `try/except` and accumulated
into the `failed` list, while `run()` itself returns a normal `BatchResult`.

**Where a successful FileSession's `message` is displayed.** If a
successful (`success=True`) `ExecResult`'s `message` is non-empty, TCBP
appends it directly to the `[idx] input → output` result line itself,
with no line break, rather than printing it on a separate line (e.g.
`[   1] 001.bmp → 001.png  [source deleted]`, see `bmp2png`). This merge
onto the same line only happens in parallel mode (the ANSI block) —
in sequential mode, an already-printed line can't be overwritten via ANSI,
so it's printed on the line right below instead. Either way, the plugin
code is identical: just return `ExecResult(True, "short note")`. For
anything that needs to update the same spot repeatedly, such as a
progress percentage, use `session.log()`/slots (3.5) instead — `message`
is only meant for a short, one-line piece of info shown once on completion.

### 3.5 `session.log()` and Slot Rules

```python
session.log(text: str, slot: int = 0) -> None
```

- `slot` only has meaning under the **FileSession + `parallel = true`**
  combination. Calling the same slot multiple times updates that spot on
  screen (useful for e.g. a `%` progress display). In every other case
  (BatchSession, or `parallel = false`), the `slot` value is ignored and the
  text is simply printed as one log line in order.
- **The number of `log()` slots a plugin will use in parallel mode must be
  declared ahead of time via `@plugin(notes_per_file=N)`.** Using a slot index
  outside the declared count is handled per the rules in 5.3/5.4.

### 3.6 `session.params` and Type Coercion

`session.params` is a `dict` merged from the following two sources (CLI
values take precedence).

1. Non-standard keys in the `job` section (placeholder defaults, e.g.
   `watermark = "..."`) — always strings
2. Keys declared in `job.params` — from CLI `key=value` or the config default

TCBP only coerces a key into an actual `int`/`bool` if it is declared in
`job.params` with `type = "int"` or `type = "bool"`. Keys that aren't declared
always remain plain strings.

```toml
params = [
    { key="backup",   desc="Back up the original as .bak", type="bool" },
    { key="chunk_size", desc="Chunk size (MB)",             type="int"  },
]
```

```python
session.params["backup"]      # True/False (bool)
session.params["chunk_size"]  # 64 (int)
session.params["watermark"]   # "c:/path/logo.png" (str — non-standard keys are never coerced)
```

`bool` coercion rules (case-insensitive):

| True | False |
|---|---|
| `true`, `1`, `yes`, `on` | `false`, `0`, `no`, `off` |

Any other string is treated as a coercion error, aborting the Job (at the
`_coerce_params` stage) with a clear error message *before it ever runs* — you
don't need to perform this validation yourself inside the plugin. Note,
however, that a plugin's standalone CLI (Section 4.4) does not go through this
automatic coercion, so call `tcbp._to_bool()` directly there if you need it
(Section 3.8).

### 3.7 Declaring a Plugin Job in config.toml

```toml
# FileSession plugin Job
[jobs.RemoveBOM]
desc                   = "Remove BOM from text files"
plugin                 = "remove_bom"        # loads ./plugin/remove_bom.py, calls run(session)
output                 = "{dir}/{base}{ext}" # output is required for FileSession
allow_output_overwrite = true                # must be explicitly allowed if output is meant to overwrite input
params = [
    { key="backup",   desc="Back up the original as .bak", type="bool" },
    { key="eachline", desc="Remove BOM from every line",    type="bool" },
]

# BatchSession plugin Job
[jobs.GroupMD5]
desc   = "Generate grouped MD5 hash files"
plugin = "group_md5"
# output may be omitted — session.output becomes None
params = [
    { key="bom", desc="Write MD5 files with a BOM", type="bool" },
]
```

Details:

- `commands` is not used in a plugin Job (`validate_config.py` warns about it
  as an "unused key" if present). The processing logic itself is the
  `run(session)` call, so no shell-command template is needed.
- `pre`/`post` (including `{ msg = "..." }` banners) run once for the whole
  batch, exactly as for a tool Job.
- `params`, `desc`, and `on_error` behave identically to a CLI Job.
- `parallel`/`max_workers`: applied normally for FileSession, ignored for
  BatchSession (`validate_config.py` warns if a BatchSession Job has `parallel
  = true`).
- `stderr_quiet`: plugins have no notion of subprocess stderr, so this is
  silently ignored (not an error).
- Custom keys that aren't standard keys go into `job.defaults` as before and
  are merged into `session.params` as strings (Section 3.6).
- `input_mode`/`recursive`/`include` (Chapter 12, directory input mode) apply
  to plugin Jobs exactly the same way as tool Jobs — e.g. `config.toml`'s
  `Bmp2PngRecursive` Job declares `input_mode = "directory"` alongside `plugin
  = "bmp2png"` to accept a folder directly and scan it recursively. From the
  plugin code's perspective, no special handling is needed — it still just
  receives the `filelist`/`input` that tcbp has already built (Section 2.2).

### 3.8 What You Can Import from `tcbp`

A plugin adds the parent folder's `tcbp.py` to `sys.path` and imports the
symbols it needs with `from tcbp import ...`. The main symbols you'll actually
use when writing a plugin:

| Symbol | Purpose |
|---|---|
| `plugin` | The decorator attached to the entry-point function (3.1) |
| `FileSession` / `BatchSession` | Session types (3.2/3.3) |
| `ExecResult` / `BatchResult` | Return value types (3.4) |
| `parse_params` | Parses a list of `key=value` strings into `dict[str, str]` in a standalone CLI |
| `_to_bool` | Converts a string to bool in a standalone CLI (same rules as 3.6) |
| `_truncate_filename` | Truncates a filename for on-screen display — measures width by on-screen display columns (treating fullwidth characters like Hangul/Hanja/Kana as width 2), which avoids console wrapping better than a plain `len()`-based cut. Used by `group_md5` for progress/log display (Section 5.5) |

`from tcbp import ...` is handled inside tcbp.py so that it always resolves to
the same running module instance whether `tcbp.py` is running as `__main__`
or is being imported as a library (e.g. from `validate_config.py`) — plugin
authors don't need to worry about this.

---

## 4. Basic Structure of a Plugin Python Program

### 4.1 File Location and Naming Rules

- A plugin must live at `./plugin/<name>.py` (under the `plugin` subfolder
  next to `tcbp.py`).
- `config.toml`'s `plugin = "name"` becomes the filename (minus extension)
  verbatim — case and spelling must match exactly.
- Plugin-specific test fixtures go in `./plugin/testdata/<name>/` (`input.*`,
  `expected_output.*`, optional `params.json`/`tolerance.json` — see 4.6).

### 4.2 Skeleton — FileSession Plugin

```python
#!/usr/bin/env python3
"""
plugin/<name>.py - TCBP FileSession plugin: <one-line description>.

Usage (standalone):
    python <name>.py <input> <output> [param1=value1] [param2=value2]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # parent folder containing tcbp.py
from tcbp import plugin, FileSession, ExecResult, parse_params, _to_bool


# ── Core logic — shared by run() and the standalone CLI ─────────────────
def _process(input_path: str, output_path: str, params: dict) -> None:
    ...  # Process a single file. Raise an exception on failure.


@plugin(
    name="<name>", contract_version="1.0", version="1.0", author="...",
    session_type="file", requirements=[], notes_per_file=0,
)
def run(session: FileSession) -> ExecResult:  # TCBP entry point
    try:
        _process(session.input, session.output, session.params)
    except Exception as exc:
        return ExecResult(False, str(exc))
    return ExecResult(True, "")


if __name__ == "__main__":  # Standalone CLI entry point
    if len(sys.argv) < 3:
        print("Usage: python <name>.py <input> <output> [param1=value1]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {
        # Pull out just the keys you need, together with their defaults
    }
    try:
        _process(input_path, output_path, cli_params)
        print(f"OK: {input_path}")
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
```

This is the exact structure followed by `plugin/remove_bom.py`,
`plugin/mozjpeg.py`, and `plugin/bmp2png.py`. `run()` is just a thin wrapper
that calls `_process()` and converts exceptions into `ExecResult(False,
...)`; all of the real processing logic lives in `_process()` (and whatever
helper functions it calls).

### 4.3 Skeleton — BatchSession Plugin

```python
#!/usr/bin/env python3
"""
plugin/<name>.py - TCBP BatchSession plugin: <one-line description>.

Usage (standalone):
    python <name>.py <list_file> [param1=value1]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # parent folder containing tcbp.py
from tcbp import plugin, BatchSession, BatchResult, parse_params


# ── Core logic — shared by run() and the standalone CLI ─────────────────
def _process(filelist: list[str], params: dict, log_fn) -> BatchResult:
    succeeded, failed = [], []
    try:
        for fp in filelist:
            try:
                ...  # Process a single file
                succeeded.append(fp)
            except Exception:
                failed.append(fp)  # Report expected per-file failures via the return value (3.4)
    finally:
        print()  # If you printed \r progress to stdout, always finish with a newline (5.5)
    return BatchResult(succeeded=succeeded, failed=failed)


@plugin(
    name="<name>", contract_version="1.0", version="1.0", author="...",
    session_type="batch", requirements=[], notes_per_file=0,
)
def run(session: BatchSession) -> BatchResult:  # TCBP entry point
    # An exception from run() is reserved as a catastrophic signal (3.4) — don't swallow it here.
    return _process(session.filelist, session.params, log_fn=lambda t: session.log(t, slot=0))


if __name__ == "__main__":  # Standalone CLI entry point — reads the list file directly
    if len(sys.argv) < 2:
        print("Usage: python <name>.py <list_file> [param1=value1]")
        raise SystemExit(1)
    list_path = Path(sys.argv[1])
    files = [line.strip() for line in list_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    cli_params = parse_params(sys.argv[2:])
    result = _process(files, cli_params, log_fn=print)
    print(f"succeeded={len(result.succeeded)} failed={len(result.failed)}")
    raise SystemExit(0 if not result.failed else 1)
```

`plugin/group_md5.py` is the real implementation that follows this pattern.

### 4.4 Standalone CLI Entry Point Rules

The `if __name__ == "__main__":` block is a minimal CLI runnable directly from
the console, without tcbp. TCBP's runtime entry point (`run()`) and this
standalone CLI **must share the exact same `_process()` function** — this
prevents the processing logic from being implemented twice and drifting apart.

The sole purpose of this CLI is to quickly confirm that "processing of the one
file handed to it (or, for BatchSession, the one list file handed to it)
works correctly." Accordingly, the following are **out of scope for this
CLI** — Total Commander (file selection) and TCBP (batch iteration) already
handle all of it.

- Wildcard expansion
- Recursive directory traversal
- (FileSession) Batch processing over multiple files — it accepts exactly one
  file as an argument.
- (BatchSession) Logic to locate the list file itself — it reads the path it's
  given, as-is.

It's recommended to keep the argument format consistent with the examples.

```commandline
python plugin\<name>.py <input> <output> [key=value ...]     # FileSession
python plugin\<name>.py <list_file> [key=value ...]           # BatchSession
```

The standalone CLI does not go through TCBP's `_coerce_params()` (the
automatic bool/int coercion described in 3.6), so convert bool parameters
yourself by calling `tcbp._to_bool()` directly (Section 3.8), or use a
standard conversion like `int()`.

### 4.5 Declaring Dependencies (`requirements`)

If a plugin needs an external package beyond the standard library, list it in
`@plugin(requirements=[...])`.

```python
@plugin(
    name="mozjpeg", contract_version="1.0", version="1.0", author="...",
    session_type="file",
    requirements=["jpeglib", "numpy", "Pillow"],
    notes_per_file=0,
)
```

**TCBP does not auto-install this list** — it exists for documentation
purposes, and the user must install the packages manually (e.g. `pip install
jpeglib numpy Pillow`). Instead, follow these two rules so that "the package
isn't installed" can be distinguished from "there's a bug in the plugin
code."

1. **Never force-import an external package at module top-level.** Wrap it in
   `try/except ImportError` and fall back to `None`. This way, even in an
   environment without the package, `validate_config.py`'s metadata check
   (the import needed to inspect `run.plugin_info`) won't fail.

   ```python
   try:
       import jpeglib
   except ImportError:
       jpeglib = None
   ```

2. **Raise a clear `RuntimeError` if the value is `None` at actual processing
   time (`_process()`).**

   ```python
   def _process(input_path, output_path, params):
       if jpeglib is None:
           raise RuntimeError("mozjpeg plugin requires jpeglib — pip install jpeglib")
       ...
   ```

This way, `validate_config.py` passes cleanly even without the required
package installed (it only checks metadata and never actually runs the
processing), and failure only happens at actual execution time, with a clear,
unambiguous error message.

**When several packages can substitute for each other (an OR dependency):**
if more than one candidate library can provide the same functionality, so
that having just one of them is enough, list every candidate in
`requirements` and let the actual selection happen at the point of use, via
nested `try/except ImportError` blocks tried in priority order. In this case
you don't need to pre-import lazily at module top-level — it's fine to
`import` the package directly inside the function that actually uses it,
since all `validate_config.py` does is import the module to inspect
`run.plugin_info`, and a function-local import statement never executes
until that function is actually called. `bmp_to_png()` in
`plugin/bmp2png.py` is the reference example of this pattern — it tries
OpenCV first (faster), falls back to Pillow on `ImportError`, and if the
fallback also fails, converts that exception into a failure message.

```python
def bmp_to_png(bmp_path: str, png_path: str) -> tuple[bool, str]:
    """Convert BMP to PNG via OpenCV (preferred) or Pillow (fallback)."""
    try:
        import cv2
        ...  # convert with OpenCV
        return True, ""
    except ImportError:
        try:
            from PIL import Image
            ...  # convert with Pillow
            return True, ""
        except Exception as e:
            return False, f"ERROR (Pillow): {e}"   # the fallback failed too — report as an error
    except Exception as e:
        return False, f"ERROR (OpenCV): {e}"
```

The underlying principle is the same as the single-package case — the mere
fact that none of the candidate packages is installed must not fail the
module import itself; it should only surface as a clear failure at actual
processing time. The only difference from the single-package case is
whether that failure is raised as a `RuntimeError` or reported via a return
value (e.g. an `(ok, message)` tuple, as `bmp2png.py` does) — either is fine
as long as it honors the return-value contract from Section 3.4.

### 4.6 Writing Tests

The `tests/` suite is split into three layers, and what you need to do for
each layer differs when adding a new plugin.

| Layer | File | Work needed for a new plugin |
|---|---|---|
| unit | `tests/test_plugin_<name>.py` | **Write by hand** — a test that imports `_process()` directly and calls it with `tmp_path`. No subprocess; error paths are also verified here. |
| metadata | `tests/test_plugin_metadata.py` | Not needed — automatically walks all of `plugin/*.py` and verifies `run.plugin_info` is valid |
| cli (golden) | `tests/test_plugin_cli_golden.py` | Not needed — automatically discovered once you add `plugin/testdata/<name>/` |

**Preparing testdata for the cli(golden) layer:**

```
plugin/testdata/<name>/
    input.*              # Input file(s) (for BatchSession, an input/ folder etc., as appropriate)
    expected_output.*    # Expected output
    params.json          # Parameters to pass to the CLI (optional)
    tolerance.json        # Image outputs only — { "rmse": 2.5 } to override the default tolerance (optional)
```

`test_plugin_cli_golden.py` discovers this folder and actually runs `python
plugin/<name>.py <input> <output> [params...]` as a subprocess, comparing the
result against `expected_output` — this is the only layer that actually
verifies "runnable as a standalone CLI" (Section 4.4), since the unit layer
never goes through argparse and so cannot catch CLI argument-parsing bugs.

For image outputs (plugins like MozJPEG/bmp2png whose output bytes can vary by
encoder library version), pixel comparison via RMSE (after decoding with
Pillow) is used instead of a raw byte diff. The default tolerance is `RMSE <=
1.0` (on a 0–255 scale); a plugin whose lossy compression is aggressive enough
to produce frequent false positives at the default can override it per-plugin
with `tolerance.json`.

For fast local feedback, exclude the slow layers.

```commandline
pytest -m "not cli and not integration"   # unit + metadata only, no subprocess
pytest                                     # all layers (CI)
```

---

## 5. Technical Notes

### 5.1 Two-Stage Fail-Fast Validation

Missing or invalid plugin metadata fails immediately, at one of two stages.

**(a) At plugin import time** — if the values passed to `@plugin(...)`
themselves are invalid (e.g. a typo like `session_type="fil"`), constructing
`PluginInfo` fails right there and the module import fails outright.
`validate_config.py` runs this same check at the same point without actually
executing anything, so this can be caught before ever running the config as a
batch.

**(b) At Job execution time** — if `run` was never wrapped with `@plugin(...)`
at all, so `run.plugin_info` doesn't even exist, TCBP immediately aborts the
Job with a fail-fast guard (of the same nature as the existing
`_require_essentials()`), producing an error message that names the plugin
and the problem.

### 5.2 Validation Strength With/Without pydantic

`FileSession`, `BatchSession`, `PluginInfo`, `ExecResult`, and `BatchResult`
are all defined with `strict_dataclass(frozen=True)`, which behaves as
follows.

- **With pydantic installed**: uses `pydantic.dataclasses.dataclass` as-is —
  field types are strictly validated at construction time, raising a detailed
  `ValidationError` on failure. Value-range constraints such as
  `Literal["file", "batch"]` are also validated precisely.
- **Without pydantic**: automatically falls back to a standard
  `dataclasses.dataclass(frozen=True)` plus minimal `isinstance`-based
  validation inside `__post_init__`. In this mode, recursive validation of
  nested types and `Literal` value-range checks are not as thorough as
  pydantic's — for example, it filters out grossly wrong types but may let
  subtler cases slip through.

From the plugin code's point of view, it doesn't matter which one is active —
both are exposed under the same name (`strict_dataclass`), and the code that
works with `FileSession`/`ExecResult`/etc. is identical either way. Just keep
this difference in validation strength in mind when writing tests that
exercise type errors in an environment without pydantic installed.

### 5.3 The log() Slot Reservation Mechanism in Parallel Mode

Under `parallel = true` + a FileSession plugin, TCBP pre-reserves a
fixed-size screen block per file, consisting of "one title line + as many
message lines as `notes_per_file`." Even though multiple worker threads
process different files concurrently and finish out of order, each file's
log lines are written only to its own reserved spot via ANSI cursor movement,
so the screen stays in order (for what this "multiple worker threads
processing concurrently" fact means for your own plugin code, see 5.10).

For this mechanism to work, **a plugin must declare, ahead of time, how many
`log()` slots it will use per file**, via `@plugin(notes_per_file=N)`. Calling
the same slot repeatedly to update its content (e.g. a `%` progress display)
is allowed — the constraint is on "how many distinct slots are used
concurrently," not "how many times log() is called."

Using a slot index outside the declared count (`slot >= notes_per_file` or
`slot < 0`) is handled per the rules in Section 5.4. This constraint applies
**only in parallel mode** — in sequential mode (`parallel = false`, including
BatchSession), no block reservation is needed, so there is no constraint at
all on the number of `log()` calls.

### 5.4 The `--strict` Flag

What happens on slot overflow depends on the run mode. If "skip the console,
log only" were the only behavior, a plugin developer would have no way to
find out why progress isn't showing on the console — so an operational mode
and a development mode are kept separate.

- **Default (production/batch) mode**: no exception is raised. Only the
  console block update is skipped; if `log = true`, that `log()` call's
  content is written to the log file only, as a `[WARNING]` (including the
  plugin name, the slot index used, and the declared `notes_per_file` value).
  **It is never printed to the console (stdout)** — in parallel mode,
  multiple workers are concurrently updating a fixed block via ANSI cursor
  movement, and if this warning leaked into stdout even slightly, the warning
  itself would cause exactly the "console output gets scrambled" problem it
  was meant to prevent.
- **`--strict` mode** (a global CLI flag at the same level as `--dry-run`): on
  slot overflow, immediately raises `IndexError` and aborts that Job
  (fail-fast).

```commandline
python tcbp.py MyPluginJob list.txt --strict
```

When creating or modifying a plugin, it's recommended to **first verify
correct slot usage with a small file list + `parallel = true` +
`--strict`**, and then run production/scheduled executions without
`--strict`. The standalone CLI entry point (Section 4.4) has no
parallel/ANSI-block management at all, so it cannot reproduce or verify this
bug — `--strict` is effectively the only way to verify it.

### 5.5 BatchSession Progress-Output Rules

BatchSession has no parallel processing, so while the plugin is running, TCBP
writes nothing else to the console. This means **it is safe for the plugin to
print numeric `%` progress directly to stdout using `\r`** (`group_md5` uses
this approach — avoid a library like `rich`, whose ANSI cursor movement is
incompatible with TCBP's own ANSI block management).

However, the following two rules must be observed.

1. The final result after each group finishes (e.g. `"created: xxx.md5 (12
   files)"`) should be reported back via `session.log()`, not the `\r`
   progress line, so it also ends up in the log file.
2. **The plugin must always finish with a newline (`print()`) before `run()`
   returns — whether it exits normally or via an exception.** If the plugin
   dies mid-processing, or returns right after a progress line with no
   trailing newline, that line can collide with TCBP's summary log printed
   immediately afterward. Guarantee the newline with `try/finally`, as
   `group_md5` does.

```python
def _process(filelist, params, log_fn):
    try:
        for fp in filelist:
            print(f"\r{...}", end="", flush=True)
            ...
    finally:
        print()  # Guarantee a newline even if it dies mid-way or returns without one
    return BatchResult(...)
```

### 5.6 Exceptions vs. Return Values — When to Use Which

| Situation | How to handle it |
|---|---|
| Only some files in a group fail (e.g. one corrupted file) | Report via `BatchResult.failed` (not an exception) |
| An expected failure while processing a single file (format error, unsupported extension, etc.) | `_process()` raises; `run()` catches it and converts it to `ExecResult(False, str(exc))` |
| A catastrophic situation that makes the Job itself untrustworthy (BatchSession) | Let the exception propagate out of `run()` — TCBP synthesizes the entire `filelist` as failed |
| A required package isn't installed | `RuntimeError` from `_process()` (Section 4.5) |

For most FileSession plugins, the pattern of `run()` wrapping `_process()`'s
exceptions into `ExecResult(False, ...)` (the skeleton in 4.2) is sufficient.
BatchSession plugins need to distinguish between "an expected per-group/
per-file failure" and "a failure that makes the whole Job untrustworthy"
(Section 3.4, see `group_md5`) — catch the former inside the loop and
accumulate it into `failed`; only let the latter propagate as an exception.

### 5.7 dry-run Behavior

When `--dry-run` is given, TCBP does not call `run()` at all; instead, it logs
a message showing how the parameters were substituted.

```
[DRY-RUN] plugin=resize input=... output=... params={...}          # FileSession
[DRY-RUN] plugin=group_md5 files=42 params={...}                    # BatchSession
```

In this case, the result is treated as `ExecResult(True, "")` or
`BatchResult(succeeded=[], failed=[])`, respectively, and counted as a
success. Plugin authors do not need to implement a dry-run-specific branch
themselves — TCBP already filters this out before `run()` is ever entered.

### 5.8 Sessions Are Read-Only

`FileSession`/`BatchSession` are constructed with `frozen=True`, so their
fields cannot be reassigned aside from calling `log()` (mutating the contents
of `params` itself, e.g. `session.params["x"] = 1`, is possible since `params`
is a plain `dict` — but reassigning a field, e.g. `session.input = "..."`,
raises an exception). The only channels a plugin has for reporting state back
through the session are `log()` and the return value (`ExecResult`/
`BatchResult`).

### 5.9 Common Mistakes Checklist

Once you've written a new plugin, check the following.

- [ ] Is the `run` function wrapped with `@plugin(...)`, and does
      `session_type` match the actual processing unit (`"file"`/`"batch"`)?
- [ ] Did you declare `@plugin(contract_version=...)`? (Section 3.1 — check
      TCBP's current contract version via `tcbp.CONTRACT_VERSION`)
- [ ] Do `run()` and the standalone CLI call the exact same `_process()`
      function? (Section 4.4)
- [ ] Does the standalone CLI avoid implementing file-list/wildcard/recursive
      traversal? (If it does, that's something to remove — Section 2.2)
- [ ] Are external packages guarded with `try/except ImportError` instead of
      being force-imported at module top-level? (Section 4.5)
- [ ] Does `@plugin(requirements=[...])` list every package actually needed?
- [ ] If `log()` is used in parallel mode, does `notes_per_file` exactly match
      the number of slots actually used? (Section 5.3)
- [ ] Does the BatchSession plugin guarantee a trailing newline before
      `run()` returns? (Section 5.5, `try/finally`)
- [ ] Does the BatchSession plugin report expected per-file failures via
      `BatchResult.failed` rather than raising an exception for them?
      (Section 5.6)
- [ ] Have golden test fixtures been added under `plugin/testdata/<name>/`?
      (Section 4.6)
- [ ] If a `parallel = true` FileSession plugin uses state shared across files
      (a module-level global, a class variable), is it a caching pattern that's
      safe without a lock — idempotent regardless of write order? If not, is
      `@plugin(thread_safe=False)` declared? (Section 5.10)

### 5.10 Thread Safety of Plugin Code in Parallel Mode

Under `parallel = true` + FileSession, TCBP uses a `ThreadPoolExecutor` to run
multiple worker threads that call `run()` (and therefore `_process()`)
concurrently for different files (Sections 2.3/5.3). Each file gets its own
freshly constructed `session` instance, so that part is inherently safe — but
**state shared across files, such as a module-level global or a class
variable, is the plugin author's own responsibility to make thread-safe.**
tcbp does not guarantee this for you.

A practical rule of thumb:

- **Safe without a lock:** an idempotent cache where multiple threads
  computing the same value concurrently and assigning it to the same global
  always produce the same result regardless of write order.
  `plugin/mozjpeg.py`'s `_CHOSEN_MOZJPEG` (a cached detection of the installed
  MozJPEG version) is this pattern — even if two threads both call
  `_ensure_mozjpeg_selected()` and each compute the value independently,
  they always compute the same value, so whichever one's assignment lands
  last doesn't change the outcome, and no lock is needed.
- **Needs a lock (or a thread-local / thread-safe data structure):** an
  accumulating counter, state whose result depends on write order, or an
  external resource that isn't itself thread-safe (a file handle, a network
  connection) shared across threads. It's better to avoid making this kind
  of state global in the first place — keep it as a local variable inside
  `_process()` instead. Once nothing is actually shared, the thread-safety
  question disappears along with it.
- **When in doubt, remove the global state entirely.** Rather than having to
  prove "is this cache idempotent?" every time, it's simpler and safer to
  write a function that carries no state at all — where every call is fully
  independent.

This constraint applies **only to FileSession + `parallel = true`**.
BatchSession (Section 3.3) is never run in parallel by TCBP, so this issue
doesn't arise there at all.

**If you can't make it thread-safe by the above criteria, declare
`@plugin(thread_safe=False)`.** `thread_safe` is the `PluginInfo` field from
Section 3.1, defaulting to `True` (assumed thread-safe unless declared
otherwise). If a `session_type="file"` plugin declares `thread_safe=False`,
two places **refuse to run it immediately, by the same rule**:

- **The tcbp.py runtime** — right after resolving the Job, `_require_essentials()`
  (a fail-fast guard of the same nature as Section 5.1's (b)) checks whether
  it matches `parallel=true` + `max_workers>1`, and if so, aborts on the spot
  with a clear error message.
- **`validate_config.py`** — `_check_plugin()` diagnoses the same condition
  ahead of time and reports it as `[ERROR]` (unlike the BatchSession+parallel
  combination, which is harmless enough to warrant only a warning since it's
  simply ignored, this combination can silently turn into a real race
  condition, so it's an error, not a warning).

With `max_workers=1`, even if `parallel=true`, only one worker exists so no
two files are ever processed concurrently — this combination is not rejected.
Keeping `parallel=true` but lowering `max_workers` to `1` is a legitimate way
to work around this constraint.

> **Aside: is it valid for `validate_config.py` to read a plugin's
> `@plugin(...)` metadata?** This check isn't a new kind of coupling — it
> extends an existing pattern. `validate_config.py`'s `_check_plugin()`
> already imports the plugin via `load_plugin()` to read
> `plugin_info.session_type` and warn about "BatchSession+parallel=true is
> ignored" (Section 3.7). It never calls `run(session)` — only imports the
> module to inspect its metadata — so it stays within this tool's "diagnose
> without executing" design principle (Section 5.5). The `thread_safe` check
> just reads one more field the same way, so it's valid on the same grounds.
