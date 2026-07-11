#!/usr/bin/env python3
"""
tcbp.py - Total Commander Batch Python (v1.5)
TOML 기반 범용 배치 처리 엔진

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]
"""

import sys, ctypes, tomllib, unicodedata, logging, subprocess
import argparse, shutil, tempfile, threading, uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows 콘솔 UTF-8 출력 보장
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── CLI 파싱 ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tcbp",
        description="Total Commander Batch Python - TOML 기반 배치 처리 엔진",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python tcbp.py Conv2PNG       list.txt
  python tcbp.py ResizeImages   list.txt size=1024
  python tcbp.py CropImages     list.txt x=10 y=20 width=800 height=600
  python tcbp.py ResizeImages   list.txt size=1024 --dry-run
  python tcbp.py Conv2PNG       list.txt --config custom.toml
        """,
    )
    parser.add_argument("job",      help="실행할 Job 이름")
    parser.add_argument("filelist", help="입력 파일 목록 텍스트 파일")
    parser.add_argument("params",   nargs=argparse.REMAINDER, metavar="key=value", help="Named 파라미터")
    parser.add_argument("--config", default=None, help="설정 파일 경로 (기본: tcbp.py와 같은 폴더의 config.toml)")
    parser.add_argument("--dry-run", action="store_true", help="명령 출력만 하고 실행 안 함")
    return parser.parse_args()


# ── Named params 파싱 ─────────────────────────────────────────────────────────

def prompt_missing_params(job: dict, user_params: dict) -> dict:
    declared = job.get("params", [])
    if not declared:
        return user_params
    result = dict(user_params)
    for meta in declared:
        key = meta.get("key", "")
        if not key or key in result:
            continue
        while True:
            raw = input(f"  {meta.get('desc', key)}: ").strip()
            if meta.get("type") == "int":
                if raw.lstrip("-").isdigit():
                    result[key] = raw
                    break
                print("  [오류] 정수를 입력하세요.")
            else:
                result[key] = raw
                break
    return result


def parse_params(raw: list[str]) -> dict[str, str]:
    result = {}
    for item in raw:
        if "=" in item:
            k, _, v = item.partition("=")
            result[k.strip()] = v.strip()
        else:
            print(f"[WARNING] 파라미터 형식 오류 (무시됨): '{item}' — key=value 형식 필요", file=sys.stderr)
    return result


# ── Config 로드 ───────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent

def load_config(config_path: str | None) -> dict:
    if config_path is None:
        path = _SCRIPT_DIR / "config.toml"
    else:
        path = Path(config_path)
        if not path.is_absolute():
            path = _SCRIPT_DIR / path
    if not path.exists():
        sys.exit(f"[ERROR] 설정 파일 없음: {path}")
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"[ERROR] {path.name} 문법 오류 — {e}")


# ── Job resolve: global 기본값 + job override ────────────────────────────────

def resolve_job(config: dict, job_name: str) -> dict:
    g    = config.get("global", {})
    jobs = config.get("jobs", {})

    if job_name not in jobs:
        available = ", ".join(jobs.keys()) if jobs else "(없음)"
        sys.exit(f"[ERROR] Job '{job_name}' 없음.\n사용 가능한 Job: {available}")

    job = jobs[job_name]

    _STANDARD_KEYS = {
        "desc", "tool", "on_error", "parallel", "max_workers", "output",
        "pre", "commands", "post", "pause", "stderr_quiet", "params",
    }

    resolved = {
        "desc":         job.get("desc", ""),
        "tool_name":    job.get("tool", g.get("default_tool", "")),
        "on_error":     job.get("on_error",    g.get("on_error",    "continue")),
        "parallel":     job.get("parallel",    g.get("parallel",    False)),
        "max_workers":  job.get("max_workers", g.get("max_workers", 4)),
        "output":       job.get("output", g.get("output", "{dir}/{base}_out{ext}")),
        "pre":          job.get("pre",      []),
        "commands":     job.get("commands", []),
        "post":         job.get("post",     []),
        "log":          g.get("log",      False),
        "log_file":     g.get("log_file", "tcbp.log"),
        "pause":        job.get("pause",  g.get("pause", False)),
        "tools":        g.get("tools",    {}),
        "stderr_quiet": job.get("stderr_quiet", g.get("stderr_quiet", False)),
        "params":       job.get("params", []),
        # 비표준 키는 placeholder 기본값으로 — CLI 파라미터가 있으면 덮어씀
        "defaults":     {k: str(v) for k, v in job.items() if k not in _STANDARD_KEYS},
    }

    # commands 배열 내 { msg = "..." } 항목 개수 — 파일당 고정 예약 줄 수 (병렬 출력 블록 크기)
    resolved["notes_per_file"] = sum(1 for c in resolved["commands"] if isinstance(c, dict))

    # commands가 {output}을 실제로 참조하는 job만 "exit 0인데 출력 파일 미생성"을 실패로 검증한다.
    # (commands 키에 출력 경로를 직접 박아넣는 예외적인 job은 검증 대상에서 자동 제외됨)
    resolved["uses_output"] = any(
        isinstance(c, str) and "{output}" in c for c in resolved["commands"]
    )

    # tool 경로 resolve
    tool_name = resolved["tool_name"]
    if tool_name:
        resolved["tool_path"] = resolved["tools"].get(tool_name, tool_name)
    else:
        resolved["tool_path"] = ""

    return resolved


# ── 파일 목록 로드 ────────────────────────────────────────────────────────────

def load_file_list(filelist_path: str) -> list[Path]:
    path = Path(filelist_path)
    if not path.exists():
        sys.exit(f"[ERROR] 파일 목록 없음: {filelist_path}")

    files = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = Path(line)
            if not p.exists():
                print(f"[WARNING] 파일 없음 (건너뜀): {line}", file=sys.stderr)
                continue
            files.append(p)

    if not files:
        sys.exit("[ERROR] 처리할 파일이 없습니다.")

    return files


# ── Placeholder 치환 ──────────────────────────────────────────────────────────

class SafeDict(dict):
    # SafeDict: 미정의 placeholder는 원문 유지
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

def substitute(template: str, context: dict) -> str:
    return template.format_map(SafeDict(context))


# ── Windows 단축 경로 (8.3) 변환 ─────────────────────────────────────────────

def _get_short_path(path: str) -> str:
    """GetShortPathNameW로 8.3 ASCII 단축 경로를 반환한다.
    파일/디렉토리가 존재하지 않으면 부모 디렉토리까지 재귀적으로 올라간다."""
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 32768)
    if n > 0:
        return buf.value
    p = Path(path)
    if p.parent == p:
        return path
    return str(Path(_get_short_path(str(p.parent))) / p.name)


def _has_non_acp(s: str) -> bool:
    """시스템 ACP(cp949 등)로 인코딩 불가능한 문자가 포함되어 있으면 True."""
    try:
        s.encode('mbcs')
        return False
    except UnicodeEncodeError:
        return True


# ── Context 빌드 (파일 단위) ──────────────────────────────────────────────────

def build_file_context(file_path: Path, index: int, job: dict, user_params: dict) -> tuple[dict, dict, str, str]:
    file_path = file_path.resolve()
    input_dir = file_path.parent
    ctx: dict[str, str] = {
        "input":  str(file_path),
        "dir":    str(input_dir),
        "name":   file_path.name,
        "base":   file_path.stem,
        "ext":    file_path.suffix,
        "index":  str(index),
        "tool":   job["tool_path"],
        **job.get("defaults", {}),  # job 내 비표준 키 (기본값)
        **user_params,              # CLI 파라미터가 우선
    }
    output_path = substitute(job["output"], ctx)
    output_p = Path(output_path).resolve()
    same_dir = (output_p.parent == input_dir)

    # { msg = "..." } 메시지 치환용 — 명령 인자용 따옴표를 씌우기 전 원본(raw) 값을 보존한다.
    raw_ctx = dict(ctx)
    raw_ctx["output"] = output_path

    # {input}/{output}를 파일명(상대 경로)으로 줄이고 cwd=input_dir 로 실행.
    # subprocess.run(cwd=unicode_dir)은 CreateProcessW lpCurrentDirectory로 전달되어
    # OS가 내부적으로 Unicode 절대 경로로 해석하므로 ANSI 도구도 정상 동작한다.
    ctx["input"]  = f'"{file_path.name}"'
    ctx["output"] = f'"{output_p.name}"' if same_dir else f'"{_get_short_path(str(output_p))}"'
    ctx["dir"]    = f'"{_get_short_path(str(input_dir))}"'
    ctx["name"]   = f'"{file_path.name}"'
    ctx["base"]   = f'"{file_path.stem}"'
    ctx["tool"]   = f'"{job["tool_path"]}"' if job["tool_path"] else ""
    return ctx, raw_ctx, output_path, str(input_dir)


# ── Pre/Post용 Context (파일 단위 placeholder 제외) ──────────────────────────

def build_global_context(job: dict, user_params: dict) -> tuple[dict, dict]:
    tool = job["tool_path"]
    raw_ctx = {
        "tool":        tool,
        "max_workers": str(job.get("max_workers", "")),
        **job.get("defaults", {}),  # job 내 비표준 키 (기본값)
        **user_params,              # CLI 파라미터가 우선
    }
    ctx = dict(raw_ctx)
    ctx["tool"] = f'"{tool}"' if tool else ""
    return ctx, raw_ctx


# ── 화면 표시용 파일명 축약 ────────────────────────────────────────────────────

def _display_width(s: str) -> int:
    """한글/한자/가나 등 전각 문자는 폭 2, 그 외는 폭 1로 콘솔 표시 폭을 계산한다."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _max_name_display_len() -> int:
    """"[idx] in → out" 한 줄에 맞도록 파일명 1개당 최대 표시 폭을 계산한다.
    input/output 두 개가 나란히 출력되므로 각각 콘솔 폭의 절반보다 약간 작게 잡는다."""
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    overhead = len("[9999] ") + len(" → ")
    per_name = (cols - overhead) // 2 - 2
    return max(per_name, 10)


def _truncate_filename(name: str, max_width: int) -> str:
    """긴 파일명을 표시할 때 확장자는 항상 남기고, 중간을 "..."로 생략한다.
    폭 계산은 전각 문자를 2칸으로 취급하는 _display_width 기준."""
    if _display_width(name) <= max_width:
        return name
    stem = Path(name).stem
    ext = Path(name).suffix
    budget = max_width - _display_width(ext) - 3  # "..." 폭 3 제외
    if budget < 10:
        budget = 10  # 최소 폭 보장
    if _display_width(stem) <= budget:
        return stem + ext
    width = 0
    cut = 0
    for i, ch in enumerate(stem):
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return stem[:cut] + "..." + ext


def _max_message_display_len() -> int:
    """{ msg = ... } 한 줄 표시에 맞는 최대 폭. 콘솔 줄바꿈이 생기면 ANSI 커서 계산이
    어긋나므로 반드시 한 줄 안에 들어오도록 자른다."""
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    return max(cols - 4, 10)


def _truncate_message(text: str, max_width: int) -> str:
    """긴 메시지를 한 줄 폭에 맞춰 말미를 "..."로 생략한다."""
    if _display_width(text) <= max_width:
        return text
    budget = max_width - 3
    width = 0
    cut = 0
    for i, ch in enumerate(text):
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return text[:cut] + "..."


# ── 멀티스레드 순서 보장 출력 매니저 ──────────────────────────────────────────

def _enable_win_ansi() -> None:
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode   = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class OutputManager:
    """스레드로부터 start/note/finish 이벤트를 받아 출력한다.

    파일 1개는 고정 크기 블록(1 + notes_per_file 줄)을 차지한다.
    on_start()  → 버퍼링 후 순서가 되면 블록 전체(제목줄 + note 예약 빈 줄)를 한 번에 출력
    on_note()   → 블록 내 지정된 예약 줄을 그 자리에서 덮어씀 (ANSI, 도착 순서 무관)
    on_finish() → 블록의 제목줄을 완료 순서대로 즉시 결과로 덮어씀 (ANSI, 번호 순서 무관)

    on_error=stop 등으로 뒤의 note가 아예 발생하지 않으면, 예약된 빈 줄이 그대로 남아
    "중단 시 빈 칸으로 flush"를 별도 코드 없이 자연스럽게 만족한다.
    """

    def __init__(self, logger: logging.Logger, notes_per_file: int = 0) -> None:
        _enable_win_ansi()
        self._logger        = logger
        self._lock          = threading.Lock()
        self._notes_per_file = notes_per_file
        self._block_height   = 1 + notes_per_file
        self._start_buf  : dict[int, str]                   = {}
        self._finish_buf : dict[int, tuple[str, str, bool]] = {}
        self._pending_notes: dict[int, dict[int, str]]      = {}
        self._rows       : dict[int, int]                   = {}
        self._line_count  = 0
        self._next_start  = 1

    def on_start(self, idx: int, filename: str) -> None:
        with self._lock:
            self._start_buf[idx] = _truncate_filename(filename, _max_name_display_len())
            self._flush()

    def on_note(self, idx: int, slot: int, text: str) -> None:
        with self._lock:
            if idx not in self._rows:
                # 블록이 아직 화면에 안 나왔으면(거의 없는 경우) 대기했다가 start flush 시 반영
                self._pending_notes.setdefault(idx, {})[slot] = text
                return
            self._write_note(idx, slot, text)

    def on_finish(self, idx: int, in_name: str, out_name: str, ok: bool) -> None:
        with self._lock:
            self._finish_buf[idx] = (in_name, out_name, ok)
            self._flush()

    def _write_note(self, idx: int, slot: int, text: str) -> None:
        base_row = self._rows[idx]
        row      = base_row + 1 + slot
        line     = f"  {_truncate_message(text, _max_message_display_len())}"
        up       = self._line_count - row
        sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
        sys.stdout.flush()
        self._logger.debug(line)

    def _flush(self) -> None:
        # start 이벤트를 순서대로 출력 (제목줄 + note용 예약 빈 줄을 블록으로 한 번에 출력)
        while self._next_start in self._start_buf:
            idx      = self._next_start
            filename = self._start_buf.pop(idx)
            self._rows[idx] = self._line_count
            sys.stdout.write(f"[{idx:>4}] {filename}\n")
            sys.stdout.write("\n" * self._notes_per_file)
            self._line_count += self._block_height
            sys.stdout.flush()
            self._next_start += 1
            for slot, text in sorted(self._pending_notes.pop(idx, {}).items()):
                self._write_note(idx, slot, text)

        # finish 이벤트: start가 출력된 항목은 완료 순서대로 즉시 출력 (번호 순서 무관)
        for idx in sorted(k for k in list(self._finish_buf) if k in self._rows):
            in_name, out_name, ok = self._finish_buf.pop(idx)
            row                   = self._rows.pop(idx)
            mark                  = "→" if ok else "✗"
            max_len               = _max_name_display_len()
            line                  = f"[{idx:>4}] {_truncate_filename(in_name, max_len)} {mark} {_truncate_filename(out_name, max_len)}"
            up                    = self._line_count - row
            # \033[{up}A\r : 목표 행으로 이동  \033[K : 행 지우기  \033[{up}B\r : 복귀
            sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
            sys.stdout.flush()
            # 콘솔은 ANSI 덮어쓰기, 로그 파일에는 완성된 결과 행만 기록
            self._logger.debug(line)


# ── Logging 설정 ──────────────────────────────────────────────────────────────

def setup_logging(log: bool, log_file: str) -> logging.Logger:
    logger = logging.getLogger("tcbp")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log and log_file:
        log_path = Path(log_file) if Path(log_file).is_absolute() else _SCRIPT_DIR / log_file
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


# ── Windows 명령줄 파싱 (CommandLineToArgvW) ──────────────────────────────────

_CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
_CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)

def _parse_cmdline(cmd: str) -> list[str]:
    """cmd.exe를 거치지 않고 Windows API로 직접 파싱 → Unicode 경로 보존."""
    argc = ctypes.c_int(0)
    argv = _CommandLineToArgvW(cmd, ctypes.byref(argc))
    if not argv:
        return [cmd]
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


# ── 단일 명령 실행 ────────────────────────────────────────────────────────────

def run_command(cmd: str, logger: logging.Logger, dry_run: bool, cwd: str | None = None, quiet: bool = False, stderr_quiet: bool = False) -> tuple[bool, str]:
    if dry_run:
        logger.info(f"  [DRY-RUN] {cmd}")
        return True, ""

    args = _parse_cmdline(cmd)
    result = subprocess.run(
        args,
        shell=False,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if not quiet:
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                logger.info(f"  {line}")
        if result.stderr.strip() and not stderr_quiet:
            for line in result.stderr.strip().splitlines():
                logger.warning(f"  STDERR: {line}")

    return result.returncode == 0, result.stderr


# ── Pre / Post 실행 (배치 전체 1회) ──────────────────────────────────────────

def run_pre_post(
    commands: list,
    global_ctx: dict,
    global_raw_ctx: dict,
    logger: logging.Logger,
    dry_run: bool,
    label: str,
) -> None:
    for cmd_template in commands:
        if isinstance(cmd_template, dict):
            text = substitute(cmd_template.get("msg", ""), global_raw_ctx)
            logger.info(f"[DRY-RUN][{label}] {text}" if dry_run else text)
            continue

        cmd = substitute(cmd_template, global_ctx)
        if dry_run:
            logger.info(f"[DRY-RUN][{label}] {cmd}")
            continue

        # commands와 동일한 방식(shell 없이 CommandLineToArgvW로 파싱)으로 실행한다.
        # echo 등 cmd.exe 내장 명령은 "cmd /c echo ..." 처럼 명시적으로 작성해야 한다.
        args = _parse_cmdline(cmd)
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                logger.info(f"  {line}")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                logger.warning(f"  STDERR: {line}")


# ── 단일 파일 처리 ────────────────────────────────────────────────────────────

def process_file(
    file_path: Path,
    index: int,
    job: dict,
    user_params: dict,
    logger: logging.Logger,
    dry_run: bool,
    manager: "OutputManager | None" = None,
) -> tuple[bool, str]:
    ctx, raw_ctx, output_path, cwd = build_file_context(file_path, index, job, user_params)
    output_p = Path(output_path)
    quiet    = manager is not None

    if manager:
        manager.on_start(index, file_path.name)
    else:
        max_len = _max_name_display_len()
        logger.info(f"[{index:>4}] {_truncate_filename(file_path.name, max_len)} → {_truncate_filename(output_p.name, max_len)}")

    # ACP 범위 밖 문자(예: 일본어)가 경로/파일명에 포함된 경우,
    # ASCII 임시 경로로 복사해 ANSI 도구를 우회한다.
    need_temp = not dry_run and (_has_non_acp(str(file_path)) or _has_non_acp(cwd))
    tmp_dir: Path | None = None
    ret: tuple[bool, str] = (False, "")

    try:
        if need_temp:
            tmp_dir = Path(tempfile.gettempdir()) / f"tcbp_{uuid.uuid4().hex[:8]}"
            tmp_dir.mkdir()
            tmp_in  = tmp_dir / f"in{file_path.suffix}"
            tmp_out = tmp_dir / f"out{output_p.suffix}"
            shutil.copy2(str(file_path), str(tmp_in))
            ctx["input"]  = f'"{tmp_in}"'
            ctx["output"] = f'"{tmp_out}"'
            cwd = str(tmp_dir)

        last_stderr = ""
        stderr_quiet = job.get("stderr_quiet", False)
        note_slot = 0
        for cmd_template in job["commands"]:
            if isinstance(cmd_template, dict):
                text = substitute(cmd_template.get("msg", ""), raw_ctx)
                if dry_run:
                    logger.info(f"  [DRY-RUN][MSG] {text}")
                elif manager:
                    manager.on_note(index, note_slot, text)
                else:
                    logger.info(f"  {text}")
                note_slot += 1
                continue

            cmd = substitute(cmd_template, ctx)
            success, stderr = run_command(cmd, logger, dry_run, cwd=cwd, quiet=quiet, stderr_quiet=stderr_quiet)
            last_stderr = stderr
            if not success:
                msg = f"FAILED [{index}] {file_path.name} | CMD: {cmd} | ERR: {stderr.strip()}"
                if not quiet:
                    logger.error(msg)
                ret = (False, msg)
                return ret

        if need_temp:
            if not tmp_out.exists():
                msg = f"FAILED [{index}] {file_path.name} | 출력 파일 미생성 (tool이 exit 0으로 실패) | STDERR: {last_stderr.strip()}"
                if not quiet:
                    logger.error(msg)
                ret = (False, msg)
                return ret
            output_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_out), str(output_p))
        elif job["uses_output"] and not dry_run and not output_p.exists():
            # commands가 {output}을 참조하는데도 exit 0 이후 실제 파일이 없으면 조용한 성공을 막는다.
            msg = f"FAILED [{index}] {file_path.name} | 출력 파일 미생성 (tool이 exit 0으로 실패) | STDERR: {last_stderr.strip()}"
            if not quiet:
                logger.error(msg)
            ret = (False, msg)
            return ret

        ret = (True, "")
        return ret

    finally:
        if manager:
            manager.on_finish(index, file_path.name, output_p.name, ret[0])
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)


# ── Job 실행 오케스트레이터 ───────────────────────────────────────────────────

def run_job(
    job: dict,
    files: list[Path],
    user_params: dict,
    logger: logging.Logger,
    dry_run: bool,
) -> None:
    global_ctx, global_raw_ctx = build_global_context(job, user_params)
    total = len(files)

    # tool 존재 확인
    if job["tool_path"] and not dry_run:
        tool_p = Path(job["tool_path"])
        if not tool_p.exists():
            logger.warning(f"Tool 경로를 찾을 수 없습니다: {job['tool_path']}")

    # Pre
    run_pre_post(job["pre"], global_ctx, global_raw_ctx, logger, dry_run, "PRE")

    success_count = 0
    failed_count  = 0

    if job["parallel"] and total > 1:
        # ── 병렬 처리 ──────────────────────────────────────────────────────
        manager = OutputManager(logger, job["notes_per_file"])
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=job["max_workers"]) as executor:
            future_map = {
                executor.submit(process_file, f, i + 1, job, user_params, logger, dry_run, manager): i + 1
                for i, f in enumerate(files)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    ok, err = future.result()
                except Exception as exc:
                    ok  = False
                    err = f"[{idx}] 예외 발생: {exc}"
                if ok:
                    success_count += 1
                else:
                    failed_count += 1
                    if err:
                        errors.append((idx, err))
                    if job["on_error"] == "stop":
                        logger.error("on_error=stop: 나머지 작업 취소 중...")
                        for f in future_map:
                            f.cancel()
                        break
        for _, err in sorted(errors):
            logger.error(err)
    else:
        # ── 순차 처리 ──────────────────────────────────────────────────────
        for i, file_path in enumerate(files):
            try:
                ok, _ = process_file(file_path, i + 1, job, user_params, logger, dry_run)
            except Exception as exc:
                ok = False
                logger.error(f"[{i + 1}] 예외 발생: {exc}")
            if ok:
                success_count += 1
            else:
                failed_count += 1
                if job["on_error"] == "stop":
                    logger.error("on_error=stop: 처리 중단")
                    break

    # Post
    run_pre_post(job["post"], global_ctx, global_raw_ctx, logger, dry_run, "POST")

    # logger.info("=" * 60)
    logger.info(f"완료 — 성공: {success_count}  실패: {failed_count}  전체: {total}")
    # logger.info("=" * 60)


# ── 오류 출력 / 긴급 로그 (setup_logging 이전 크래시용) ──────────────────────

def _emergency_log(msg: str) -> None:
    """logger가 초기화되기 전 오류를 스크립트 폴더의 tcbp_error.log에 기록한다."""
    try:
        import datetime
        path = _SCRIPT_DIR / "tcbp_error.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n{msg}\n")
    except Exception:
        pass


def _pause_on_error(msg: str) -> None:
    """오류 내용을 콘솔에 출력하고 Enter를 기다려 창이 닫히지 않게 한다."""
    print(f"\n{msg}", flush=True)
    input("\n--- 오류 발생. Enter 키를 누르면 종료합니다. ---")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    _logger: logging.Logger | None = None
    _job:    dict | None           = None
    try:
        args        = parse_args()
        user_params = parse_params(args.params)
        config      = load_config(args.config)
        _job        = resolve_job(config, args.job)
        _logger     = setup_logging(_job["log"], _job["log_file"])

        # 로그 파일에 이 줄이 있으면 setup_logging까지는 성공한 것
        if _job["desc"]:
            _logger.info(f"Job: {args.job} — {_job['desc']}")
        if args.dry_run:
            _logger.info("[DRY-RUN 모드] 명령 출력만 수행하고 실제 실행하지 않습니다.")

        user_params = prompt_missing_params(_job, user_params)
        files       = load_file_list(args.filelist)

        mode = f"parallel (max_workers={_job['max_workers']})" if _job["parallel"] else "sequential"
        _logger.info(f"파일 {len(files)}개  |  {mode}")

        run_job(_job, files, user_params, _logger, args.dry_run)

    except SystemExit as e:
        if e.code:
            msg = str(e)
            if _logger:
                _logger.error(msg)
            else:
                _emergency_log(msg)
            _pause_on_error(msg)
        raise
    except Exception:
        import traceback
        msg = traceback.format_exc()
        if _logger:
            _logger.error(msg)
        else:
            _emergency_log(msg)
        _pause_on_error(msg)
        raise

    if _job and _job.get("pause"):
        try:
            import keyboard
            print("\n아무 키나 누르면 종료합니다...", flush=True)
            keyboard.read_event(suppress=True)
        except ImportError:
            input("\n아무 키나 누르면 종료합니다...")


if __name__ == "__main__":
    main()
