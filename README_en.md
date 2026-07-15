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
- No external libraries required (standard library only). However, the following are used automatically if installed:
  - `keyboard`: used for the "press any key to exit" wait when `pause = true` (falls back to waiting for the Enter key if not installed)
  - `wcwidth`: used to calculate the display width of file names/messages on screen (falls back to an approximate calculation if not installed)
- Windows environment (full Unicode path support)
### 3.2 File Structure
```filelist
tcbp.py           Execution engine
config.toml       Job definition file (default)
tcbp.log          Execution log (auto-created when log=true)
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
log_file     = "tcbp.log"               # log file path
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
log_file = "tcbp.log"
```
- `log = false`: console output only
- `log = true`: console + file logging simultaneously
- The log file is always created **in the same folder as tcbp.py** (regardless of the run location).
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

### 4.11 Automatic Config Validation
Right after `config.toml` is loaded, the job to be run is automatically checked for common authoring mistakes. This does not change the structure or writing style of `config.toml` in any way, and a correctly written job runs exactly as before, with no messages at all.

Checks performed:
- **Missing required keys** — if `tool`, `output`, or `commands` is actually empty, it is treated as an error and execution is aborted.
- **Misspelled reserved words** — a key that closely resembles a standard key (`tool`, `output`, `pre`, etc.), such as `tool_pat`, is flagged as a suspected typo with a warning.
- **Misspelled placeholders** — a placeholder that is never filled in anywhere, such as `{basename}`, triggers a warning, and if a similarly named real placeholder exists, it is suggested.
- **Unused custom keys** — a value defined in the job but never referenced as `{key}` in `pre`/`commands`/`post`/`output` is reported as informational.

If there are any errors (ERROR), execution is aborted; warnings (WARNING) and info (INFO) are just reported and execution continues as normal.

```
=== Config Validation Result ===

Job: ResizeImage

[ERROR]
- Missing required key: tool (or a tool name registered in global.tools is required)

[WARNING]
- Unknown key: tool_pat
  Did you mean: tool
- Undefined placeholder: {basename}
  Did you mean: {name}

[INFO]
- Unused key: quality

Total 1 error(s)  2 warning(s)  1 info(s)
```

---

## 5. How to Add a New Job
1. Add a `[jobs.NewJobName]` section to `config.toml`
2. Define `tool`, `output`, and `commands`
3. If parameters are needed, write them in `commands` as `{param_name}`
4. Pass them as `key=value` at run time
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

## 6. Total Commander Integration
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

---
## 7. Technical Note: Unicode Path Handling Policy
Some external tools (e.g. gm.exe) are ANSI builds, so if a path or file name contains characters outside the system code page (cp949) range (e.g. Japanese), the tool may fail to open the file. TCBP works around this by passing the Unicode directory as the working directory (cwd) via `subprocess.run(cwd=unicode_dir)`, and passing only the file name as a relative path in the tool's arguments. This lets programs that only support ANSI path names correctly handle files with Unicode paths without issue.
```
gm.exe convert -quality 95 "001.jpg" "001.png"
(cwd = X:\publisher\双葉社\)
```
- This is passed via the `lpCurrentDirectory` parameter of `CreateProcessW`, so Python sets the Unicode directory as the cwd.
- When the tool calls `fopen("001.jpg")`, the OS internally resolves it as `cwd + file name`.

## 8. Technical Note: TCBL → TCBP Migration Table
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

## 9. Technical Note: `shell=True` vs `shell=False`, and Rules for Writing Built-in vs External Commands

TCBP runs every `pre` / `commands` / `post` command via `subprocess` with **`shell=False`**. This chapter explains why, and the rules to follow when writing commands in `config.toml`.

### 9.1 Two Ways `subprocess` Launches a Process

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

`shell=False` bypasses cmd.exe entirely, so the problems above disappear at the root, and it lets the Unicode path workaround described in Chapter 7 work reliably, on the premise that arguments are passed through as-is. This is why TCBP runs every command uniformly with `shell=False`.

### 9.2 If You Want to Use a Shell Built-in Command

`echo`, `del`, `copy`, `dir`, `cd`, `set`, and similar commands are **not executable files — they exist only as built-in commands inside cmd.exe** (there are no files like `echo.exe` or `del.exe` on Windows). If you run `"echo hello"` as-is with `shell=False`, the OS tries to find an executable file named `echo`, but no such executable exists, so it fails with `FileNotFoundError`.

Therefore, if you want to use a shell built-in command in `config.toml`, you must explicitly prefix it with `cmd /c`. `cmd /c ...` works correctly even under `shell=False` because `args[0]` is `cmd.exe` (an actual executable file) — this makes it an explicit statement by the config author that a built-in command is intended. (However, if the goal is only to print text to the screen/log, using the `{ msg = "..." }` from section 4.2.1 is recommended instead of `cmd /c echo`.)

```toml
commands = [
    "cmd /c echo \"Text to print\" ",
    "cmd /c copy {input} C:\\src.tmp",
]
```

## 10. Version History
- **v1.0:** Initial release
- **v1.1:** Fixed multi-processing so that whichever result finishes first is printed first (previously, a file that started later but finished earlier would have its output held back until the earlier file's output was printed)
- **v1.2:** Renamed the `output_rule` key to `output` (for consistency with the `{output}` placeholder)
- **v1.3:** When output is too long to fit on one line, the file name is now shown with the middle truncated
- **v1.4:** Changed `pre`/`post` to run with `shell=False` (`CommandLineToArgvW` parsing) just like `commands`. `cmd.exe` built-in commands must now always be written with `cmd /c` with no exceptions (applies across all of `config.toml`), and pre/post results (STDOUT/STDERR) are now also recorded in the log file. As a result, writing something like `cmd /c echo ----banner-text----` to print banners became too cumbersome, so a dedicated `msg` command for printing messages was added.
- **v1.5:** Fixed a silent-failure bug where a command that referenced `{output}` but did not actually create the file was still counted as a 'success'; it is now counted as a 'failure'
- **v1.6:** Added `{taskid}` (shared across the whole batch) / `{itemid}` (per-file) placeholders to avoid file name collisions when a temporary file is needed in a multi-step command. Updated the Chapter 7 Unicode path handling policy description in the docs to match the actual implementation (relative-path mode). Cleaned up the Chapter 9 technical notes content.
- **v1.7:** Improved the on-screen file name length calculation to prefer using `wcwidth` (falls back to the previous method if not installed). Added a feature that automatically validates job definitions right after loading `config.toml` (improved TOML syntax error messages; diagnoses missing required keys, misspelled reserved words, misspelled placeholders, and unused keys).
- **v1.8:** Added bilingual Korean/English support for text that tcbp.py itself outputs (errors, warnings, logs, `--help`). Selectable via `--lang ko|en` or `[global] lang` in `config.toml` (default `ko`). Content the user writes in `config.toml` (`desc`, `msg`) is excluded from translation.
