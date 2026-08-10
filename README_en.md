# TCBP — Total Commander Batch Python
[TOC]
## 1. Overview
This tool is a Python re-implementation of similar functionality, inspired by [TCBL (Total Commander Batch Builder & Launcher)](https://totalcmd.net/plugring/TCBL_1.02.html).

## 2. Features
The main features of this tool are as follows.

### 2.1 Features shared with `TCBL`
- Repeatedly runs a CLI (command line interface) based tool that processes a single file, as a batch.
- Files to process are read in from a list file.
- Combined with a file manager such as [Total Commander](https://www.ghisler.com/) or [Directory Opus](https://www.gpsoft.com.au/), it becomes very powerful. (Select target files in the file manager and pass the list file to this tool; the selected files are then batch processed.)
- You can specify a command to run once at the start (pre), a command to run repeatedly on each target file (command), and a command to run once at the end (post).

### 2.2 Features improved over `TCBL`
- In addition to external CLI tools, you can add a Python program that processes a single file as a plugin. (Four plugins — `bmp2png`, `mozjpeg`, `group_md5`, `remove_bom` — are bundled by default.)
- Supports recursive processing — files inside a given folder, and optionally its subfolders, can be processed directly.
- File processing can be multi-threaded, allowing multiple files to be processed concurrently. This is advantageous for processing-heavy tasks such as `MP3` or `PNG` encoding.
- Even when files are processed out of order due to multi-threading, screen output is kept in sequential order.
- During multi-processing, a UUID4-based temporary ID can be generated and used so that intermediate file names don't collide across processes.
- Supports `Unicode` file names and paths. Even if an external CLI tool does not support Unicode and only supports `ANSI` codes, this tool handles the path workaround internally and still produces the correct final output.
- Desired parameters can be entered manually before batch execution.
- Unlike `TCBL`, whose config file format is `INI`, this tool's config file format is `TOML`, which handles Unicode without issues.

---

## 3. Program Structure and Usage
### 3.1 Requirements
- Python 3.11 or later (built-in `tomllib`)
- Works with no external libraries (standard library only). However, the following are used automatically if installed:
  - `pydantic`: used for strict type validation of Session objects / plugin metadata (falls back to looser standard-dataclass-based validation if not installed — prints a notice, see Chapter 5)
  - `keyboard`: used for the "press any key to exit" wait when `pause = true` (falls back to waiting for the Enter key if not installed)
  - `wcwidth`: used to calculate the display width of file names/messages on screen (falls back to an approximate calculation if not installed)
- Packages required by individual plugins (e.g. `jpeglib` for MozJPEG) are separate — they are never auto-installed and must be installed manually (see section 5.7).
- Windows environment (full Unicode path support)
### 3.2 File Structure
```filelist
tcbp.py             Execution engine
validate_config.py  config.toml pre-flight validation tool (see section 4.11)
config.toml         Job definition file (default)
plugin/              Plugin folder (see Chapter 5)
logs/                Execution log folder (auto-created when log=true, one file per run)
```
### 3.3 Basic Usage

```commandline
python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run] [--lang ko|en]
```

The default output language is Korean, and this applies only to text that tcbp.py itself outputs (errors, warnings, logs, etc.) — content that users write directly in config.toml, such as `desc` or `{ msg = "..." }`, is not translated and is printed exactly as written. The language is determined by the following priority.
1. `--lang ko` / `--lang en` (CLI argument; also applies to `--help` text)
2. `[global] lang = "en"` in `config.toml`
3. Default `ko`
### 3.4 Example — Basic Usage
```commandline
:: Simple conversion (no parameters)
python tcbp.py Conv2PNG list.txt

:: Print the command only, without executing (dry-run)
python tcbp.py ResizeImages list.txt size=1024 --dry-run

:: Use a separate config file
python tcbp.py Conv2PNG list.txt --config my_project.toml
```

### 3.4 Example — Passing Parameters
- You can pass parameters specified in the `params = []` entry in the config file.
- Parameters can be passed on the command line at execution time; if omitted, the user is prompted to type them in directly at run time.
```commandline
:: Passing parameters
python tcbp.py ResizeImages list.txt size=1024
python tcbp.py CropImages   list.txt x=10 y=20 width=800 height=600
python tcbp.py Helix_MP3    list.txt bitrate=64
```


### 3.5 dry-run Mode
```commandline
python tcbp.py ResizeImages list.txt size=1024 --dry-run
```
- Performs file listing, placeholder substitution, and command construction
- Prints the commands only, without actually running any subprocess
- Useful for validating configuration and debugging

Sample output:
```log
[DRY-RUN mode] Only prints commands; nothing is actually executed.
Job: ResizeImages — Resize images (keep aspect ratio, only to smaller size)
3 files  |  sequential
[DRY-RUN][PRE] Resize images
[DRY-RUN][PRE] Side Length: 1024 pixels
[   1] photo01.jpg → photo01_out.jpg
  [DRY-RUN] "C:/.../gm.exe" convert -resize 1024x1024> "photo01.jpg" "photo01_out.jpg"
[   2] photo02.png → photo02_out.png
...
Done — success: 3  failed: 0  total: 3
```

### 3.6 Input File List Format (list.txt)
- The input file list is a text document encoded in `UTF-8` or `UTF-8 with BOM`.
- Each target is recorded as a Unicode full path (directory + file name).
- In the file manager Total Commander, passing `%UL` as a parameter causes Total Commander to write the list of selected files to a temporary list file, which is then passed to this tool.
```listfile
# Comments start with #
C:\images\photo01.jpg
C:\images\photo02.png
C:\images\photo03.bmp
```

Instead of a list file, you can also pass **a folder path directly** and have TCBP find and process the files inside it automatically — see section 4.12 (Directory Input Mode).

---

## 4. `config.toml` Structure and Configuration

### 4.1 Global Section Settings

```toml
[global]
on_error     = "continue"               # "continue" | "stop"
parallel     = false                    # overall default
max_workers  = 4                        # max worker count for multi-threaded parallel processing
output       = "{dir}/{base}_out{ext}"  # output path rule
log          = false                    # whether to write a log file
log_file     = "logs/tcbp_{job}_{timestamp}.log"  # log file path ({job}/{timestamp} placeholders supported)
pause        = false                    # whether to wait for a key press after completion
stderr_quiet = false                    # whether to suppress the tool's STDERR output
lang         = "ko"                     # "ko" | "en" — tcbp.py output language (CLI --lang takes priority)

[global.tools]
magick   = "C:/path/magick.exe"         # graphics processing/format conversion: https://imagemagick.org/ (slower but more powerful, handles advanced features)
gm       = "C:/path/gm.exe"             # graphics processing/format conversion: https://imagemagick.org/ (fast, suited to general tasks)
flac     = "C:/path/flac.exe"           # lossless audio format: https://xiph.org/flac/
hmp3     = "C:/path/hmp3.exe"           # ultra-fast MP3 encoder: https://www.rarewares.org/mp3-others.php#helix_enc
pngcrush = "C:/path/pngcrush.exe"       # PNG image optimizer/recompressor: https://pmt.sourceforge.io/pngcrush/
oxipng   = "c:/path/oxipng.exe"         # PNG image optimizer/recompressor: https://github.com/oxipng/oxipng/releases
```

### 4.2 Job Section Settings
```toml
[jobs.MyJob]
desc         = "Job description"
tool         = "gm"             # a key from global.tools, or a direct path
on_error     = "continue"       # global override
parallel     = false            # global override
max_workers  = 4                # global override
output       = "{dir}/{base}_out{ext}"  # global override
pause        = false            # global override
stderr_quiet = false            # suppress the tool's STDERR output

pre      = [ { msg = "Starting..." } ]
commands = [ "{tool} convert {input} {output}" ]
post     = [ { msg = "Done." } ]

# Parameter declaration (optional)
params = [
    { key="size", desc="Output size (pixels)", type="int" },
]
```
- The command specified in `pre` runs only once, at the start.
- The command specified in `command` runs repeatedly, batch-processing each file in the list.
- The command specified in `post` runs only once, at the end.
- `pre`/`post`/`commands` are all executed without a shell (`shell=False`). If you actually need to run a cmd.exe built-in command such as `del`/`copy`/`dir`, it is not an executable file, so you must explicitly prefix it with `cmd /c`, as in the example in section 4.8. For simple informational messages, use the `{ msg = "..." }` table instead of `cmd /c echo` — see section 4.2.1.
- Write your own job name in place of MyJob, and pass that job name as a parameter at run time.
```commandline
python tcbp.py MyJob filelist.txt
```

### 4.2.1 Printing Messages — `{ msg = "..." }`
Each element of the `pre` / `commands` / `post` arrays can be either a string (a command to run) or a `{ msg = "..." }` table (a message to be printed to the screen/log only). Messages never spawn a process — Python writes them directly to the log.

```toml
pre = [
    { msg = "-------------------------------------------------------------------------------" },
    { msg = "   Convert images PNG format" },
    { msg = "-------------------------------------------------------------------------------" },
]
```

Inside `commands`, you can interleave these between actual commands to use them as **per-file progress messages**. In this context, `{input}`/`{output}`/`{name}`/`{base}`/`{dir}`/`{tool}`/`{index}` are substituted with their raw, unquoted values as used for command arguments (see the example in section 4.8 below).

```toml
commands = [
    "cmd /c copy {input} C:\\src.tmp",
    { msg = "[{index}] {name} starting temporary conversion" },
    "C:\\path\\HCONV.EXE C:\\src.tmp C:\\tgt.tmp /k",
    { msg = "[{index}] {name} moving final result" },
    "cmd /c copy C:\\tgt.tmp {output}",
]
```

- Even in a `parallel = true` job, per-file message lines keep their order. Since the number of messages inside a job's `commands` is fixed, a screen region of "title line + message lines" is pre-reserved per file, and each line is overwritten in its designated position regardless of when it actually completes.
- If a later step never runs (e.g. because of `on_error = "stop"`) and its message is never emitted, the reserved line is simply left blank (no special handling needed).
- If a message line would exceed the console width, it would wrap and break the display layout, so the end of the line is automatically truncated with `...`.

#### Non-standard Keys in the Job Section — Placeholder Defaults
Any key added to a job section that is not one of the standard fields (`desc`, `tool`, `pre`, `commands`, etc.) automatically becomes available as a `{placeholder}` default.

```toml
[jobs.AddWatermark]
tool      = "gm"
watermark = "c:/_FIX/images/logo.png"   # ← non-standard key → usable as {watermark}

commands = [
    "{tool} composite -gravity southeast \"{watermark}\" {input} {output}",
]
```

- Passing a CLI parameter with the same name overrides the value defined in the job. (CLI takes priority.)
- Path values are not automatically quoted, so you must wrap them with `\"{key}\"` inside the command.

### 4.2.2 Parameter `preset` — Selection UI
Declaring `preset` (a list of label+value entries) on a `params` entry replaces free-text input with an automatic arrow-key selection UI — implemented with ANSI escapes + keyboard input only, no external package (e.g. questionary).

```toml
params = [{
    key="ch_bitrate", desc="Audio quality (bitrate)", type="int", default=128,
    preset=[
        { label="128kbps", value=64 },
        { label="192kbps", value=96 },
        { label="256kbps", value=128 },
        { label="320kbps", value=160 },
    ],
}]
```

**Controls (in a real console)**
- Move between entries with ↑/↓, confirm with `Enter`.
- The currently highlighted entry is shown with a `>> Label` prefix and ANSI reverse-video coloring.
- The entry matching `default` is the initial selection. Pressing `Enter` immediately, with no navigation, confirms `default` as-is.
- Pressing `Esc` cancels the entire operation and exits with a clear cancellation message.

**`default` rules**
- `default` must be present among `preset`'s `value` entries (both value and type must match) — otherwise the run exits immediately with a config error.
- Omitting `default` entirely is not an error — the **first** `preset` entry is used as the initial selection instead.
- Each `preset` `value`'s type must match the param's declared `type` (`int`/`bool`/omitted = string).

**Interaction with CLI values**
- A param already supplied via CLI `key=value` skips its interactive question.
- However, if a param with `preset` receives a CLI value, its range is still validated against `preset` — a value outside the range exits with an error.
- A param with `default` but no `preset` still uses free-text input as before, but the prompt starts pre-filled with `default` (in a real console) so pressing `Enter` alone confirms it. With neither `preset` nor `default`, behavior is 100% unchanged from before.

**Environments without TTY/ANSI support (pipes/redirection, etc.)**
Where the arrow-key UI can't be used because the process isn't attached to a real console, it automatically falls back to numbered selection.
```
    >> [1] 128kbps
       [2] 192kbps
       [3] 256kbps
       [4] 320kbps
  Select number (Enter=default 3, c=cancel):
```
Pressing `Enter` alone confirms the default (marked `>>`); typing `c` cancels.

**Final confirmation before execution**
Even for a Job with `params` declared, if every required value was already supplied via CLI `key=value`, no extra screen appears at all (fully backward compatible). Only when at least one value had to be entered manually (including a preset selection) does a final parameter summary with a Proceed/Cancel choice appear right before execution.

**Mitigating "the value doesn't match the label I picked" confusion**
A `preset`'s `value` can differ from the number the user actually recognizes (e.g. `ch_bitrate` is a per-channel rate, so picking "128kbps" actually stores 64). When that's the case, using the following two together is recommended.
1. **Spell out the real value in the label text** — e.g. `label="128kbps (64kbps/ch)"`, so the label itself states what the stored value means.
2. **Use the `{key}_label` placeholder** — for every param declared with `preset`, `{key}_label` (the text of the label the user picked) is generated automatically and can be used inside `pre`/`post`/`commands`' `{ msg = "..." }` entries.
   ```toml
   { msg = "   Bitrate : {ch_bitrate_label} -> {ch_bitrate} kbps/channel" },
   ```
   The final confirmation screen also automatically pairs the picked label with the value for any param selected via `preset`: `ch_bitrate = 64  (selected: 128kbps (64kbps/ch))`.

### 4.3 Placeholder Reference
| Placeholder | Description | Example |
|---|---|---|
| `{input}` | Full path of the input file | `C:\images\photo.jpg` |
| `{dir}` | Directory of the input file | `C:\images` |
| `{name}` | File name (including extension) | `photo.jpg` |
| `{base}` | File name (excluding extension) | `photo` |
| `{ext}` | Extension (including the dot) | `.jpg` |
| `{index}` | Processing order number (starting at 1) | `1` |
| `{output}` | Resulting path after applying the output rule | `C:\images\photo_out.jpg` |
| `{tool}` | The tool path for that job | `C:\path\to\gm.exe` |
| `{max_workers}` | Number of parallel workers | `8` |
| `{key}` | CLI `key=value` parameter, or a non-standard key in the job section | `size=1024` → `{size}` = `1024` |
| `{taskid}` | A temporary ID generated once for the whole batch and shared throughout (mainly used for temporary folder names) | `tmp_550e8400e29b` |
| `{itemid}` | A temporary ID newly generated for each file (item). Stays the same across multiple command lines for the same item. (mainly used for temporary file names) | `tmp_3fa85f645717` |

`{taskid}` / `{itemid}` exist to avoid file name collisions (especially during `parallel = true` multi-threaded processing) when temporary files are needed in multi-step commands. The program automatically generates temporary names using random UUID4 values.

### 4.4 Placeholder Substitution Scope
| Location | Per-file placeholders | Named params | `{tool}` | `{max_workers}` | `{taskid}` | `{itemid}` |
|---|---|---|---|---|---|---|
| `pre` / `post` | Not substituted | Substituted | Substituted | Substituted | Substituted | Not substituted |
| `commands` | Substituted | Substituted | Substituted | Substituted | Substituted | Substituted |
| `output` | Substituted | Substituted | Substituted | Substituted | Substituted | Substituted |

- An undefined placeholder is not treated as a placeholder and is left as-is in the text. (`{unknown}` → `{unknown}`).

### 4.5 Automatic Quoting
- Placeholders that hold a path are automatically wrapped in quotes (`"..."`) when the command is executed.
- Therefore, you should not write `\"` directly in `config.toml`.
- However, if you insert a user-defined placeholder that is not one of the standard placeholders and its content is a path, you must write `\"` yourself.

| Placeholder | Auto-quoted | Notes |
|---|:---:|---|
| `{input}` | ✓ | Full path of the input file |
| `{output}` | ✓ | Full path of the output file |
| `{dir}` | ✓ | Directory path |
| `{name}` | ✓ | File name (including extension) |
| `{base}` | ✓ | File name (excluding extension) |
| `{tool}` | ✓ | Executable path |
| `{ext}` | — | Form like `.jpg`, no spaces |
| `{index}` | — | Number |
| `{max_workers}` | — | Number |
| `{key}` (user param) | — | Value type is unknown; handle manually if needed |
| `{taskid}` | — | `tmp_`-prefixed hex string, no spaces |
| `{itemid}` | — | `tmp_`-prefixed hex string, no spaces |

```toml
# Normal usage (no quotes needed) example 1
commands = [
    "{tool} convert -quality 95 {input} {output}",
]

# Normal usage (no quotes needed) example 2
commands = [
    "RemoveBOM.exe {name} {dir}",
]

```

```toml
# User-defined placeholder is a path -> quoting required
watermark = "c:/path/images/fuzzy-magick.png"
commands = [
    "{tool} composite -gravity southeast -quality 95 \"{watermark}\" {input} {output}",
]
```

### 4.6 `output` Writing Guide
#### 4.6.1 Changing the Extension (Format Conversion)

```toml
# Use with tools whose output format follows the extension attached to the output file name
output = "{dir}/{base}.png"     # always PNG
output = "{dir}/{base}.jpg"     # always JPG
output = "{dir}/{base}.bmp"     # always BMP
```

#### 4.6.2 Adding a Suffix
```toml
# Keep the output extension the same as the original, and add a suffix to avoid overwriting
output = "{dir}/{base}_out{ext}"        # photo_out.jpg
output = "{dir}/{base}_resized{ext}"    # photo_resized.jpg
```

#### 4.6.3 Including a Parameter
```toml
output = "{dir}/{base}_{size}px{ext}"   # photo_1024px.jpg
```

### 4.7 Parallel Processing
```toml
[jobs.Conv2PNG_Fast]
tool        = "gm"
output      = "{dir}/{base}.png"
parallel    = true
max_workers = 8

commands = [
    "{tool} convert -quality 95 {input} {output}",
]
```

- `parallel = true`: runs files in parallel per-file using a `ThreadPoolExecutor`.
- Even in parallel mode, `pre` / `post` still run only once.

---

### 4.8 Multi-step
- Runs multiple commands in sequence for a single file.
- Intermediate file paths are written directly in the commands.
- `{output}` refers to the final result path.
- If `parallel = true` processes multiple files concurrently, using a fixed intermediate file path string can cause file name collisions. In that case, use `{taskid}` / `{itemid}` (see section 4.3) in the intermediate file names to avoid collisions.
```toml
[jobs.Johap_to_KS]
tool     = ""
on_error = "stop"

pre = [
    { msg = "Creating temp folder: C:\\Temp\\{taskid}" },
    "cmd /c mkdir C:\\Temp\\{taskid}",
]

commands = [
    "cmd /c copy {input} C:\\Temp\\{taskid}\\{itemid}_src.tmp",
    { msg = "[{index}] {name} converting Johap→KS..." },
    "C:\\path\\HCONV.EXE C:\\Temp\\{taskid}\\{itemid}_src.tmp C:\\Temp\\{taskid}\\{itemid}_tgt.tmp /k",
    { msg = "[{index}] {name} moving result..." },
    "cmd /c copy C:\\Temp\\{taskid}\\{itemid}_tgt.tmp {output}",
    "cmd /c del C:\\Temp\\{taskid}\\{itemid}_src.tmp",
    "cmd /c del C:\\Temp\\{taskid}\\{itemid}_tgt.tmp",
]

post = [
    "cmd /c rmdir /s /q C:\\Temp\\{taskid}",
    { msg = "Temp folder deleted: C:\\Temp\\{taskid}" },
]
```
- See section 4.2.1 for `{ msg = "..." }`. Since `on_error = "stop"`, if the `HCONV.EXE` step fails, the second message is never printed at all, and that line is left blank.
- `{itemid}` keeps the same value across every step while processing a single file, so, as in the example above, multiple commands can reference the same intermediate file.
- `{taskid}` is generated only once for the entire batch and refers to the same value everywhere in `pre`/`commands`/`post`, so, as in the example above, it can be used to create a shared temporary folder in `pre` and clean it up in `post`. Within `commands`, `{itemid}` distinguishes per-file intermediate file names inside that folder, so it works without collisions even under `parallel = true`.

### 4.9 Error Handling
```toml
on_error = "continue"   # skip the failed file and keep going
on_error = "stop"       # stop immediately on the first failure
```
- Can be configured at either the `global` or `job` level
- In parallel mode with `stop`: cancels the remaining in-flight Futures
- Failed files are recorded in the log (including CMD + STDERR)

### 4.10 Logging
```toml
[global]
log      = true
log_file = "logs/tcbp_{job}_{timestamp}.log"
```
- `log = false`: console output only
- `log = true`: console + file logging simultaneously
- When `log_file` is a relative path, it's always anchored to **the same folder as tcbp.py** (regardless of the run location).
- `log_file` supports `{job}` (job name) and `{timestamp}` (`YYYYMMDD_HHMMSS` at run time) placeholders, so each run gets its own file instead of appending to one shared log.
- The console still shows plain messages only (no level prefix), while the file uses `%(asctime)s [%(levelname)s] %(message)s`, adding a timestamp and level to each line.
- There's no separate failed-run log file (`*_failed.log`) — failures can be filtered within the same log file by `[ERROR]` level.
- The log records job headers, per-file results, and error messages (CMD + STDERR).

#### Emergency Error Log (`tcbp_error.log`)
Errors that occur before the logger is initialized, such as a config file load failure, are recorded in `tcbp_error.log` with a timestamp.

```
[2026-06-27 23:51:15]
[ERROR] Syntax error in config.toml

Line 297, Column 1

296 | [jobs.Sharpen]
297 | desc
298 | tool = "gm"
      ^

A '=' is required after the key.
```

When an error occurs, the console window stays open automatically so you can check the content.

### 4.11 Config Validation

#### 4.11.1 tcbp.py's Own Minimal Guard
Right after resolving a Job, tcbp.py aborts immediately if `tool`, `output`, or `commands` is empty. This isn't a typo-diagnosis feature — it's the minimum safety net needed to keep a config mistake (like an empty `{tool}`) from turning into a confusing runtime failure instead (for example, Windows actually ships its own `convert.exe`, which could end up running by accident).

#### 4.11.2 Pre-flight Validation Tool — `validate_config.py`
Authoring diagnostics such as typos, unused keys, and undefined placeholders are handled entirely by a separate tool, `validate_config.py`. tcbp.py never calls it automatically during a run, so after editing `config.toml` you should run it manually (or from CI) before running the actual batch.

```commandline
python validate_config.py <config.toml> [--job JOB] [--sample <filelist>] [--lang ko|en]
```

Checks performed:
- **TOML syntax errors** — shown together with the line/column and the original source code frame.
- **Missing required keys** — `tool`, `output`, or `commands` actually being empty.
- **Misspelled reserved words** — a key that closely resembles a standard key, such as `tool_pat`.
- **Misspelled placeholders** — a `{placeholder}` that is never filled in anywhere; a similarly named real placeholder is suggested if one exists.
- **Unused custom keys** — a value defined in the job but never referenced anywhere as `{key}`.
- **`global.tools` path validity** — a full sweep confirming every registered tool executable actually exists.
- **Output/input overwrite risk** — a warning if the `output` template could resolve to the same file as `input`.
- **Type typos** — a `params` `type` that isn't `"int"`, a `parallel`/`log`/`pause`/`stderr_quiet`/`recursive` value that isn't a bool, an `input_mode` that isn't `"list"`/`"directory"`, an `include` that isn't a list of strings, and similar mistakes.
- **Misused directory-input settings** — a warning if `recursive`/`include` are set on a Job whose `input_mode` isn't `"directory"` (see section 4.12).
- **Sample dry-run check** (when `--sample` is given) — substitutes placeholders against a real file list to catch format errors before an actual run.

Omitting `--job` validates every Job defined in `config.toml` at once. Exits with code 1 if there are any errors (ERROR), so it can be used as a gate in CI or batch scripts; exits with code 0 if there are only warnings (WARNING) or info (INFO).

Sample output:
```
--- global ---
[WARNING] Tool path not found: gm -> C:/tools/gm.exe

--- ResizeImage ---
[ERROR] Missing required key: tool (or a tool name registered in global.tools is required)
[WARNING] Unknown key: tool_pat
        Did you mean: tool
[WARNING] Undefined placeholder: {basename}
        Did you mean: {name}
[INFO] Unused key: quality

Validated 1 job(s) — 1 error(s), 2 warning(s), 1 info
```

### 4.12 Directory (Folder) Input Mode

Instead of a list file (list.txt), you can pass **a folder path directly** as the FileList argument, and have TCBP find and process the files inside that folder (optionally including subfolders) on its own.

```toml
[jobs.Bmp2PngRecursive]
plugin      = "bmp2png"
input_mode  = "directory"   # this Job only accepts a folder path — passing a list.txt is an error
recursive   = true          # search subfolders too
include     = ["*.bmp"]     # glob patterns (every file, if omitted)
output      = "{dir}/{base}.png"
```

```commandline
python tcbp.py Bmp2PngRecursive D:\Images
```

| Key | Default | Description |
|---|---|---|
| `input_mode` | `"list"` | `"list"`: the FileList argument must be a list file (the existing behavior). `"directory"`: the FileList argument must be a folder. |
| `recursive` | `false` | Only meaningful when `input_mode = "directory"`. If `true`, subfolders are searched recursively too. |
| `include` | `[]` (everything) | Only meaningful when `input_mode = "directory"`. A list of glob patterns (e.g. `["*.bmp"]`, `["*.jpg", "*.jpeg"]`). A file matching more than one pattern is still only included once. |

All three keys can also be set as defaults in the `[global]` section and overridden per job (the same inheritance rule as other settings).

**Contract — an error if `input_mode` and the actual argument disagree**: `input_mode` is a contract that declares, ahead of time, what kind of FileList argument this Job expects. If the argument actually passed in disagrees with that contract (e.g., `input_mode="directory"` but a list file is given, or the reverse — a folder is given to a Job with the default `input_mode` of `"list"`), TCBP does not process any files; it aborts immediately with a clear error.

For how to wire this up with Total Commander (especially the caution around using `%P`), see section 7.1.

---

## 5. Plugin System

### 5.1 Overview — `tool` vs `plugin`
Instead of wrapping an external CLI tool with `tool = "..."`, you can write file-processing logic directly as a Python function and wire it into a Job. `tool` and `plugin` cannot both be set on the same Job.

| | `tool = "..."` | `plugin = "..."` |
|---|---|---|
| Processing logic | External CLI executable (`subprocess`) | A Python function in `./plugin/<name>.py` |
| Target | Existing executables like GraphicsMagick, oxipng | Logic implemented directly in Python |
| `commands` key | Required | Not used (warns if present) |

The plugin API spec (`FileSession`/`BatchSession`/`ExecResult`/`BatchResult`, `session.log()`, etc.) and how to write a new plugin are covered in detail in `plugin/plugin_guide_en.md` (the plugin authoring guide) — this chapter focuses on how to **use** the bundled plugins.

### 5.2 Session Types — FileSession / BatchSession
| | FileSession | BatchSession |
|---|---|---|
| Unit of work | 1 file | The whole file list |
| `parallel` | Supported (concurrent up to `max_workers`) | Ignored (always sequential) |
| `output` | Required | Optional (or `output = ""`) |
| `run()` return type | `ExecResult(success, message)` | `BatchResult(succeeded, failed)` |
| Examples | RemoveBOM, MozJPEG, bmp2png | GroupMD5 |

### 5.3 Declaring a Plugin Job in config.toml
```toml
[jobs.RemoveBOM]
plugin                  = "remove_bom"     # loads ./plugin/remove_bom.py
output                  = "{dir}/{base}{ext}"
allow_output_overwrite  = true             # a Job whose output intentionally overwrites its input must opt in explicitly
params = [
    { key="backup", desc="Back up the original as .bak", type="bool" },
]
```
BatchSession Jobs may omit `output` (or set `output = ""`) — this is for cases like GroupMD5 that write results per file group rather than per file.

### 5.4 Bundled Plugins
| Job name | Session type | Description | Key params |
|---|---|---|---|
| `RemoveBOM` | FileSession | Removes the UTF-8 BOM from text files | `backup`, `eachline` (bool) |
| `MozJPEG` | FileSession | Recompresses/converts images to JPEG using MozJPEG | `quality` (int, 1-100) |
| `bmp2png` | FileSession | Converts BMP to optimized PNG (via oxipng) | `delete` (bool) |
| `GroupMD5` | BatchSession | Groups files by filename similarity and generates a `.md5` list per group | `bom` (bool), `chunk_size` (int, MB) |

```commandline
python tcbp.py RemoveBOM list.txt backup=true
python tcbp.py MozJPEG   list.txt quality=90
python tcbp.py bmp2png   list.txt delete=true
python tcbp.py GroupMD5  list.txt bom=false chunk_size=8
```

### 5.5 Standalone Plugin CLI
Every plugin has a standalone CLI entry point that processes a single file (or, for GroupMD5, a single list file) without tcbp — intended for plugin development/debugging. Wildcards, recursive search, and list-file-based batch processing are not supported here.
```commandline
python plugin\remove_bom.py <input> <output> [backup=true] [eachline=true]
python plugin\mozjpeg.py    <input> <output> [quality=90]
python plugin\bmp2png.py    <input> <output> [delete=true] [oxipng_exe=...]
python plugin\group_md5.py  <list_file> [bom=true] [chunk_size=8]
```

### 5.6 The `--strict` Flag
When a FileSession plugin running in parallel mode (`parallel = true`) calls `log()` with a slot outside the declared count (`notes_per_file`), the default is to skip the console update and write a warning to the log file only; passing `--strict` aborts immediately with an error instead.

For how this works and the recommended workflow while developing a plugin, see Sections 5.3–5.4 (the log() slot reservation mechanism / the `--strict` flag) of `plugin/plugin_guide_en.md`.

### 5.7 Plugin Dependencies
Packages a plugin needs are **not auto-installed** by tcbp, so `pip install` them manually per the table below.

| Plugin | Required packages |
|---|---|
| `remove_bom` | None (standard library only) |
| `mozjpeg` | `jpeglib`, `numpy`, `Pillow` |
| `bmp2png` | `opencv-python`, `Pillow`, `numpy` |
| `group_md5` | None (standard library only) |

For how dependencies are declared and how `validate_config.py` treats them, see Section 4.5 of `plugin/plugin_guide_en.md`.

---

## 6. How to Add a New Job
1. Add a `[jobs.NewJobName]` section to `config.toml`
2. Define `tool`, `output`, and `commands`
3. If parameters are needed, write them in `commands` as `{param_name}`
4. Pass them as `key=value` at run time
5. (Recommended) Run `python validate_config.py config.toml --job NewJobName` as a pre-flight check before running the actual batch (see section 4.11)
```toml
[jobs.Sharpen]
desc        = "Sharpen images"
tool        = "gm"

commands = [
    "{tool} convert -unsharp {radius}x{sigma} -quality {quality} {input} {output}",
]
```

```batch
python tcbp.py Sharpen list.txt radius=3 sigma=1.5 quality=95
```

It's possible to skip the `output` key and `{output}` placeholder and instead write an output rule such as `{dir}/{base}_out{ext}` directly inside `commands`, but for tools that don't support Unicode, the path workaround logic will not apply correctly in that case. Using the `output` key and `{output}` placeholder is recommended. Likewise, you can skip the `tool` key and specify the tool executable directly inside `commands`, but if the same tool is used across several jobs, you'll have more places to update whenever the tool changes. Defining it in the `[global.tools]` section is recommended.

---

## 7. Total Commander Integration
- Configure this in Total Commander's button bar or in a custom menu under the Start menu, as follows.
- Leave the start path blank unless you have a specific reason not to. That way, Total Commander's current path becomes the working directory.
- `%UL` : the path of the selection list file that TC generates (acting as list.txt, UTF-8 encoded, containing the target files as full paths)

```
Command:    C:\python\python.exe
Parameters: C:\path\TCBP\tcbp.py Conv2PNG %UL
Start path: (blank)
```

To pass parameters to a job that takes parameters, configure it like this.
```
Parameters: C:\path\TCBP\tcbp.py ResizeImages %UL size=1024
```

### 7.1 Wiring Up a Folder (Directory) Input Job — Caution When Using `%P` with Total Commander

⚠️ Caution: For a Job declared with `input_mode = "directory"` (a Job that takes a folder itself, rather than a list file, and searches it recursively), wire it up to a TC button using the **`%P` macro, which passes the current panel's folder path**, instead of the selected file list (`%UL`). When you do, **you must add a period (`.`) right before the closing quote, as shown below.**

```
Parameters: C:\path\TCBP\tcbp.py Bmp2PngRecursive "%P."
```

**Explanation**: `%P` conventionally expands with a trailing backslash (`\`) at the end of the path (e.g., `D:\Images\`). If you simply wrap this in quotes in the Parameters field as `"%P"`, Windows' command-line argument-parsing rules mean that **the backslash right before the closing quote escapes that quote**, so the argument doesn't end where you intended. As a result, the Job name or other parameters that should come after it can get merged into the same argument, or an unexpected error can occur. Adding a trailing dot avoids this escaping problem. Once you write it as `"%P."`, the path that gets substituted becomes `D:\Images\.`, which is a valid path pointing to the exact same folder as `D:\Images\`.

| Way of writing it | Result |
|---|---|
| `%P` (no quotes) | ❌ If the folder path contains a space, the argument gets split into multiple pieces |
| `"%P"` (quoted, no period) | ❌ The trailing backslash escapes the closing quote, corrupting the argument |
| `"%P."` (period added) | ✅ Works correctly |

### 7.2 How Directory Input Mode Builds Its File List

**Sort logic**: Directory-scan results are always sorted by name, so ordering never depends on whatever order the filesystem happens to return files in — keeping the `{index}` placeholder and parallel-mode screen output ordering reproducible. When `recursive = true`, results are **not** produced by sorting the full path strings all at once; instead, each folder's own files are listed first (by name), then its subfolders are visited in name order (the same rule applied recursively within each).

If this rule weren't applied and the full absolute path strings were sorted directly instead, a subfolder with a numeric name (e.g. `001`) could end up compared against a numerically-named file in the current folder (e.g. `009.bmp`), scrambling the order. With `001/` and `009.bmp`–`012.bmp` at the root, the third character of `"001\013.bmp"` (`1`) is less than the third character of `"009.bmp"` (`9`), so all of `001`'s contents would sort before the root's own `009.bmp`–`012.bmp` — meaning the current folder's own files could end up interleaved among its subfolders in a way that contradicts what you'd intuitively expect.

**Relationship to existing features**: A directory input is internally converted into a file list (the same as with list.txt) and handed to the existing processing engine as-is. That means tool-based Jobs, FileSession/BatchSession plugins, `parallel` processing, placeholder substitution, logging, and every other feature work unmodified.

---
## 8. Technical Notes

### 8.1 Technical Note: Unicode Path Handling Policy
Some external tools (e.g. gm.exe) are ANSI builds, so if a path or file name contains characters outside the system code page (cp949) range (e.g. Japanese), the tool may fail to open the file. TCBP works around this by passing the Unicode directory as the working directory (cwd) via `subprocess.run(cwd=unicode_dir)`, and passing only the file name as a relative path in the tool's arguments. This lets programs that only support ANSI path names correctly handle files with Unicode paths without issue.
```
gm.exe convert -quality 95 "001.jpg" "001.png"
(cwd = X:\publisher\双葉社\)
```
- This is passed via the `lpCurrentDirectory` parameter of `CreateProcessW`, so Python sets the Unicode directory as the cwd.
- When the tool calls `fopen("001.jpg")`, the OS internally resolves it as `cwd + file name`.

### 8.2 Technical Note: TCBL → TCBP Migration Table
For those migrating from the existing TCBL tool to this tool, here is a placeholder mapping table.

| TCBL | TCBP |
|---|---|
| `$f` | `{input}` |
| `$x` | `{base}` (used together with output) |
| `$n` | `{name}` |
| `$e` | `{ext}` |
| `$p` | `{dir}` |
| `$i` | `{index}` |
| `$1`, `$2` | `{key}` (named param) |
| `pre=` | `pre = [...]` |
| `cmd=` | `commands = [...]` |
| `end=` | `post = [...]` |
| `batch_preset.ini [Section]` | `config.toml [jobs.JobName]` |

### 8.3 Technical Note: `shell=True` vs `shell=False`, and Rules for Writing Built-in vs External Commands

TCBP runs every `pre` / `commands` / `post` command via `subprocess` with **`shell=False`**. This section explains why, and the rules to follow when writing commands in `config.toml`.

### 8.4 Technical Note: Two Ways `subprocess` Launches a Process

| | Process actually launched | Fate of the command string |
|---|---|---|
| `shell=True` | `cmd.exe` | Passed as `cmd.exe /c "whole string"`, and **cmd.exe re-parses it** |
| `shell=False` (used by tcbp) | The program pointed to by `args[0]` itself | The argument array, already split via `CommandLineToArgvW`, is passed **as-is** to the target program |

```python
# shell=True  →  CreateProcess("cmd.exe", '/c echo hello & del temp.txt')
subprocess.run("echo hello & del temp.txt", shell=True)

# shell=False →  CreateProcess("gm.exe", ["convert", "photo.jpg", "photo.png"])
subprocess.run(["gm.exe", "convert", "photo.jpg", "photo.png"], shell=False)
```

Because `shell=True` has cmd.exe interpret the string one more time:
- Shell metacharacters such as `&`, `|`, `>`, `<`, `^`, `%VAR%` **get interpreted by cmd.exe**. If such characters appear in a file name, the command can be unintentionally split apart or misread as a redirection.
- Quote (`"`) handling follows cmd.exe's own rules, so once Unicode paths, spaces, or special characters get mixed in, it becomes subtle to determine how to safely wrap them in quotes.
- If an externally sourced string, such as a file name, is inserted directly into the command, there is a risk of **command injection**.

`shell=False` bypasses cmd.exe entirely, so the problems above disappear at the root, and it lets the Unicode path workaround described in section 8.1 work reliably, on the premise that arguments are passed through as-is. This is why TCBP runs every command uniformly with `shell=False`.

### 8.5 Technical Note: If You Want to Use a Shell Built-in Command

`echo`, `del`, `copy`, `dir`, `cd`, `set`, and similar commands are **not executable files — they exist only as built-in commands inside cmd.exe** (there are no files like `echo.exe` or `del.exe` on Windows). If you run `"echo hello"` as-is with `shell=False`, the OS tries to find an executable file named `echo`, but no such executable exists, so it fails with `FileNotFoundError`.

Therefore, if you want to use a shell built-in command in `config.toml`, you must explicitly prefix it with `cmd /c`. `cmd /c ...` works correctly even under `shell=False` because `args[0]` is `cmd.exe` (an actual executable file) — this makes it an explicit statement by the config author that a built-in command is intended. (However, if the goal is only to print text to the screen/log, using the `{ msg = "..." }` from section 4.2.1 is recommended instead of `cmd /c echo`.)

```toml
commands = [
    "cmd /c echo \"Text to print\" ",
    "cmd /c copy {input} C:\\src.tmp",
]
```

### 8.6 Technical Note: Placeholder `{key.label}` / `{key.value}` Syntactic Sugar
As explained in section 4.2.2, a param declared with `preset` can have a stored value (`value`) that differs from the label (`label`) the user picked (e.g. `ch_bitrate` is a per-channel rate, so picking "128kbps" actually stores 64). A `{key}_label` placeholder is auto-generated so this value/label pair can be shown together in `pre`/`post`/`commands`' `{ msg = "..." }`, but its name alone doesn't make it obvious that it's derived from `{key}`. To address that, `{key.label}` / `{key.value}` notation is also supported — so the relationship is visible in the notation itself.

**Important: this is not real Python attribute access.** Python `str.format()`'s `"{name.attr}"` syntax actually looks up the object `context[name]` first, then performs `getattr(obj, "attr")` on it. Supporting `{ch_bitrate.label}` this way for real would require wrapping the value stored in `context["ch_bitrate"]` in an `int`/`str` subclass carrying a `.label` attribute — but **`bool` cannot be subclassed in Python** (`TypeError: type 'bool' is not an acceptable base type`), so `type="bool"` preset params couldn't be supported this way.

So [substitute()](tcbp.py) in `tcbp.py` doesn't use the real attribute-access protocol at all. Instead, **before** calling `str.format_map()`, it rewrites the text with a regex ([_expand_dot_sugar()](tcbp.py)):
- `{key.label}` → `{key_label}` if `key_label` exists in the context, otherwise `{{key.label}}` (an escaped literal)
- `{key.value}` → `{key}` if `key` exists in the context, otherwise likewise an escaped literal

The actual value types (`int`/`bool`/`str`) inside the context are never touched — this is purely a text-preprocessing layer, so the `bool` problem never arises in the first place.

**Why the escaping is needed when nothing matches** — the first implementation, when no match was found, simply left the original text `"{key.label}"` as-is. But the following `format_map()` call would then re-parse that same string as a real `"{name.attr}"` attribute access. If `key` exists in the context (e.g. `size`) but its value has no `.label` attribute (e.g. a plain `int`), the whole substitution would crash with `AttributeError: 'int' object has no attribute 'label'`. To prevent this, an unmatched case is rewritten to an escaped form like `{{key.label}}` so `format_map()` sees pure literal text, and the final output correctly keeps `{key.label}` as a literal — safely reproducing the same result as [SafeDict](tcbp.py)'s "leave an undefined placeholder as-is" philosophy.

**Scope**
- Only two attributes, `.label` and `.value`, are supported — this is a narrow rule, not a general-purpose templating engine with arbitrary attribute access.
- The previously documented flat name (`{key}_label`) remains valid as-is under the hood — fully backward compatible.
- `validate_config.py`'s undefined-placeholder checker (`_extract_placeholders`) already strips everything after `.`/`[...]` and checks only the base name, so `{ch_bitrate.label}` notation is recognized as `ch_bitrate` (an already-declared param) without any extra change, and doesn't trigger a false positive.

## 9. Version History
- **v1.0:** Initial release
- **v1.1:** Fixed multi-processing so that whichever result finishes first is printed first (previously, a file that started later but finished earlier would have its output held back until the earlier file's output was printed)
- **v1.2:** Renamed the `output_rule` key to `output` (for consistency with the `{output}` placeholder)
- **v1.3:** When output is too long to fit on one line, the file name is now shown with the middle truncated
- **v1.4:** Changed `pre`/`post` to run with `shell=False` (`CommandLineToArgvW` parsing) just like `commands`. `cmd.exe` built-in commands must now always be written with `cmd /c` with no exceptions (applies across all of `config.toml`), and pre/post results (STDOUT/STDERR) are now also recorded in the log file. As a result, writing something like `cmd /c echo ----banner-text----` to print banners became too cumbersome, so a dedicated `msg` command for printing messages was added.
- **v1.5:** Fixed a silent-failure bug where a command that referenced `{output}` but did not actually create the file was still counted as a 'success'; it is now counted as a 'failure'
- **v1.6:** Added `{taskid}` (shared across the whole batch) / `{itemid}` (per-file) placeholders to avoid file name collisions when a temporary file is needed in a multi-step command. Updated the section 8.1 Unicode path handling policy description in the docs to match the actual implementation (relative-path mode). Cleaned up the section 8.3 technical notes content.
- **v1.7:** Improved the on-screen file name length calculation to prefer using `wcwidth` (falls back to the previous method if not installed). Added a feature that automatically validates job definitions right after loading `config.toml` (improved TOML syntax error messages; diagnoses missing required keys, misspelled reserved words, misspelled placeholders, and unused keys).
- **v1.8:** Added bilingual Korean/English support for text that tcbp.py itself outputs (errors, warnings, logs, `--help`). Selectable via `--lang ko`, `--lang en` or `[global] lang` in `config.toml` (default `ko`). Content the user writes in `config.toml` (`desc`, `msg`) is excluded from translation.
- **v1.9:** Added section-divider comments and relocated a few functions to group them by area (no code behavior changes).
- **v2.0:** Refactored into classes; added a new config.toml validation tool, `validate_config.py`.
- **v2.1:** Separated log files per Job.
- **v2.2:** Added the plugin system (Chapter 5) — a `plugin = "..."` Job type that processes files with a Python function instead of an external CLI tool. Two session types, FileSession (1 file, parallel-capable) and BatchSession (a file group, always sequential); a `--strict` flag (aborts immediately instead of warning on slot overflow); 4 bundled plugins (RemoveBOM/MozJPEG/bmp2png/GroupMD5). `pydantic` is now optionally used for Session/plugin metadata type validation (falls back to standard dataclasses if not installed). Added a `tests/` pytest suite.
- **v2.3:** Added directory (folder) input mode — a Job with `input_mode = "directory"` accepts a folder path instead of a list file as its FileList argument, and automatically builds the file list according to `recursive` (subfolder search) and `include` (glob-pattern filter) settings.
- **v2.4:** Added `thread_safe` metadata to plugins; plugins now re-confirm the calling thread mode themselves; added a corresponding validation routine to `validate_config.py`. Design guideline improvements.
- **v2.41:** Improved the grouping algorithm of the bundled `group_md5` plugin (plugin version v1.0 -> v1.1).
- **v2.5:** Added `preset` (a label+value list) declaration to `params` entries
  - Provides an arrow-key selection UI in place of free-text input, implemented with ANSI escapes + keyboard input only, no questionary (section 4.2.2).
  - A `default` outside the preset's value list is a config error; CLI-supplied values also have their preset range validated.
  - Environments without TTY/ANSI support automatically fall back to numbered selection.
  - The final parameter confirmation screen right before execution appears only when the user had to enter a value manually (an existing Job fully supplied via CLI sees no behavior change).
  - To mitigate confusion when a preset's value differs from the label the user picked, the final confirmation screen now pairs the picked label with the value, and the `{key.label}` / `{key.value}` placeholders (section 8.6) are available for use in `pre`/`post` messages, etc.
