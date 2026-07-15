#!/usr/bin/env python3
"""
tcbp.py - Total Commander Batch Python (v1.8)
TOML 기반 범용 배치 처리 엔진

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]
"""

import sys, ctypes, tomllib, unicodedata, logging, subprocess
import argparse, shutil, tempfile, threading, uuid
import re, string, difflib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from wcwidth import wcswidth as _wcswidth, wcwidth as _wcwidth_char
except ImportError:
    _wcswidth = None
    _wcwidth_char = None


# ── i18n: runtime message catalog (English / Korean) / i18n: 실행 중 출력 문구 카탈로그 (영어/한국어) ──
# Only messages tcbp.py itself prints (errors, warnings, log lines, --help text) go
# through this. User-authored content in config.toml (job `desc`, `{ msg = "..." }`
# text) is left as the author wrote it — never auto-translated.
# tcbp.py 자신이 출력하는 문구(오류, 경고, 로그 줄, --help 텍스트)만 이 경로를 거친다.
# config.toml에 사용자가 직접 작성한 콘텐츠(job desc, { msg = "..." } 문구)는
# 작성자가 쓴 그대로 두며 자동 번역하지 않는다.

_LANG = "ko"  # default; overridden by --lang or config.toml's [global].lang
              # 기본값. --lang 또는 config.toml의 [global].lang으로 재설정됨

_MESSAGES: dict[str, dict[str, str]] = {
    "ko": {
        "cli_description":       "Total Commander Batch Python - TOML 기반 배치 처리 엔진",
        "cli_epilog_header":     "예시:",
        "help_job":              "실행할 Job 이름",
        "help_filelist":         "입력 파일 목록 텍스트 파일",
        "help_params":           "Named 파라미터",
        "help_config":           "설정 파일 경로 (기본: tcbp.py와 같은 폴더의 config.toml)",
        "help_dry_run":          "명령 출력만 하고 실행 안 함",
        "help_lang":             "출력 언어 (ko/en). 기본값은 config.toml의 global.lang, 없으면 ko",
        "err_need_integer":      "  [오류] 정수를 입력하세요.",
        "warn_param_format":     "[WARNING] 파라미터 형식 오류 (무시됨)",
        "warn_param_format_hint": "key=value 형식 필요",
        "toml_syntax_error":     "[ERROR] {name} 문법 오류",
        "err_config_not_found":  "[ERROR] 설정 파일 없음",
        "err_job_not_found":     "[ERROR] Job '{job}' 없음.",
        "label_available_jobs":  "사용 가능한 Job",
        "none_placeholder":      "(없음)",
        "err_filelist_not_found": "[ERROR] 파일 목록 없음",
        "warn_file_missing":     "[WARNING] 파일 없음 (건너뜀)",
        "err_no_files":          "[ERROR] 처리할 파일이 없습니다.",
        "vc_undefined_placeholder": "정의되지 않은 Placeholder",
        "vc_suggestion_maybe":   "혹시",
        "vc_unknown_key":        "알 수 없는 Key",
        "vc_did_you_mean":       "혹시 다음을 의미하셨습니까?",
        "vc_unused_key":         "사용되지 않는 Key",
        "vc_missing_required_key": "필수 Key 누락",
        "vc_missing_tool_hint":  "또는 global.tools 에 등록된 tool 이름이 필요합니다",
        "vc_summary_line":       "총 오류 {errors}개  총 경고 {warnings}개  총 정보 {infos}개",
        "warn_tool_not_found":   "Tool 경로를 찾을 수 없습니다",
        "err_on_error_stop_cancel": "on_error=stop: 나머지 작업 취소 중...",
        "err_exception":         "예외 발생",
        "err_on_error_stop_abort": "on_error=stop: 처리 중단",
        "info_job_summary":      "완료 — 성공: {success}  실패: {failed}  전체: {total}",
        "err_output_not_created": "출력 파일 미생성 (tool이 exit 0으로 실패)",
        "prompt_error_pause":    "\n--- 오류 발생. Enter 키를 누르면 종료합니다. ---",
        "info_dry_run_mode":     "[DRY-RUN 모드] 명령 출력만 수행하고 실제 실행하지 않습니다.",
        "info_file_count":       "파일 {count}개  |  {mode}",
        "prompt_press_any_key":  "\n아무 키나 누르면 종료합니다...",
    },
    "en": {
        "cli_description":       "Total Commander Batch Python - a generic TOML-based batch processing engine",
        "cli_epilog_header":     "Examples:",
        "help_job":              "Name of the Job to run",
        "help_filelist":         "Text file listing the input files",
        "help_params":           "Named parameters",
        "help_config":           "Config file path (default: config.toml next to tcbp.py)",
        "help_dry_run":          "Print commands only; don't execute them",
        "help_lang":             "Output language (ko/en). Defaults to config.toml's global.lang, or ko if unset",
        "err_need_integer":      "  [ERROR] Please enter an integer.",
        "warn_param_format":     "[WARNING] Invalid parameter format (ignored)",
        "warn_param_format_hint": "expected key=value format",
        "toml_syntax_error":     "[ERROR] {name} syntax error",
        "err_config_not_found":  "[ERROR] Config file not found",
        "err_job_not_found":     "[ERROR] Job '{job}' not found.",
        "label_available_jobs":  "Available Jobs",
        "none_placeholder":      "(none)",
        "err_filelist_not_found": "[ERROR] File list not found",
        "warn_file_missing":     "[WARNING] File not found (skipped)",
        "err_no_files":          "[ERROR] No files to process.",
        "vc_undefined_placeholder": "Undefined placeholder",
        "vc_suggestion_maybe":   "Did you mean",
        "vc_unknown_key":        "Unknown key",
        "vc_did_you_mean":       "Did you mean:",
        "vc_unused_key":         "Unused key",
        "vc_missing_required_key": "Missing required key",
        "vc_missing_tool_hint":  "or a tool name registered in global.tools is required",
        "vc_summary_line":       "Total: {errors} error(s), {warnings} warning(s), {infos} info",
        "warn_tool_not_found":   "Tool path not found",
        "err_on_error_stop_cancel": "on_error=stop: cancelling remaining tasks...",
        "err_exception":         "Exception occurred",
        "err_on_error_stop_abort": "on_error=stop: processing aborted",
        "info_job_summary":      "Done — success: {success}  failed: {failed}  total: {total}",
        "err_output_not_created": "Output file was not created (tool exited 0 but actually failed)",
        "prompt_error_pause":    "\n--- An error occurred. Press Enter to exit. ---",
        "info_dry_run_mode":     "[DRY-RUN mode] Printing commands only; nothing will actually run.",
        "info_file_count":       "{count} file(s)  |  {mode}",
        "prompt_press_any_key":  "\nPress any key to exit...",
    },
}


def _t(key: str, **kwargs) -> str:
    template = _MESSAGES.get(_LANG, _MESSAGES["ko"]).get(key) or _MESSAGES["ko"].get(key, key)
    return template.format(**kwargs) if kwargs else template


def _set_lang(lang: str | None) -> None:
    global _LANG
    if lang in _MESSAGES:
        _LANG = lang


def _prescan_lang(argv: list[str]) -> str | None:
    """Detect --lang before argparse runs, so --help text is shown in the right
    language too. / --lang 값을 argparse 파싱 전에 미리 알아내어 --help 텍스트도
    올바른 언어로 보여준다."""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


# Guarantee UTF-8 console output on Windows / Windows 콘솔 UTF-8 출력 보장
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── CLI Parsing / CLI 파싱 ─────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tcbp",
        description=_t("cli_description"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{_t("cli_epilog_header")}
  python tcbp.py Conv2PNG       list.txt
  python tcbp.py ResizeImages   list.txt size=1024
  python tcbp.py CropImages     list.txt x=10 y=20 width=800 height=600
  python tcbp.py ResizeImages   list.txt size=1024 --dry-run
  python tcbp.py Conv2PNG       list.txt --config custom.toml
        """,
    )
    parser.add_argument("job",      help=_t("help_job"))
    parser.add_argument("filelist", help=_t("help_filelist"))
    parser.add_argument("params",   nargs=argparse.REMAINDER, metavar="key=value", help=_t("help_params"))
    parser.add_argument("--config", default=None, help=_t("help_config"))
    parser.add_argument("--dry-run", action="store_true", help=_t("help_dry_run"))
    parser.add_argument("--lang", choices=["ko", "en"], default=None, help=_t("help_lang"))
    return parser.parse_args()


# ── Named Params Parsing / Named params 파싱 ──────────────────────────────────

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
                print(_t("err_need_integer"))
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
            print(f"{_t('warn_param_format')}: '{item}' — {_t('warn_param_format_hint')}", file=sys.stderr)
    return result


# ── TOML Syntax Error Message Improvement / TOML 문법 오류 메시지 개선 ─────────
# tomllib does not expose line/column as separate attributes; it embeds them in
# the message as "(at line N, column M)", so we parse that and show it together
# with the original source code frame.
# tomllib은 라인/컬럼 속성을 따로 노출하지 않고 "(at line N, column M)" 형태로
# 메시지에 포함시키므로, 이를 파싱해 원문 코드 프레임과 함께 보여준다.

_TOML_ERR_RE     = re.compile(r"^(.*?)\s*\(at line (\d+), column (\d+)\)\s*$")
_TOML_ERR_EOF_RE = re.compile(r"^(.*?)\s*\(at end of document\)\s*$")

# (regex, Korean reason, English reason) — each reason is a literal string or a
# lambda taking the regex match, for reasons that embed a captured value.
# (정규식, 한국어 설명, 영어 설명) — 캡처값을 삽입해야 하는 사유는 람다로 작성.
_TOML_REASON_PATTERNS: list[tuple[str, object, object]] = [
    (r"^Cannot overwrite a value$",
     "이미 값이 정의된 키를 다시 정의했습니다.",
     "This key's value has already been defined and cannot be redefined."),
    (r"^Cannot declare (.+) twice$",
     lambda m: f"키 '{m.group(1)}' 를 두 번 선언했습니다.",
     lambda m: f"Key '{m.group(1)}' was declared twice."),
    (r"^Cannot mutate immutable namespace (.+)$",
     lambda m: f"'{m.group(1)}' 테이블은 이미 확정되어 더 이상 수정할 수 없습니다.",
     lambda m: f"Table '{m.group(1)}' is already finalized and can no longer be modified."),
    (r"^Cannot redefine namespace (.+)$",
     lambda m: f"'{m.group(1)}' 테이블을 다시 정의했습니다.",
     lambda m: f"Table '{m.group(1)}' was redefined."),
    (r"^Expected '=' after a key in a key/value pair$",
     "키 뒤에 '=' 가 필요합니다.",
     "An '=' is required after the key."),
    (r"^Expected '\]' at the end of a table declaration$",
     "테이블 선언을 닫는 ']' 가 필요합니다.",
     "A closing ']' is required to end the table declaration."),
    (r"^Expected '\]\]' at the end of an array declaration$",
     "배열 테이블 선언을 닫는 ']]' 가 필요합니다.",
     "A closing ']]' is required to end the array-of-tables declaration."),
    (r"^Expected '(.+)'$",
     lambda m: f"'{m.group(1)}' 이(가) 필요합니다.",
     lambda m: f"'{m.group(1)}' is required."),
    (r"^Invalid initial character for a key part$",
     "키의 시작 문자가 올바르지 않습니다.",
     "The key starts with an invalid character."),
    (r"^Invalid statement$",
     "올바르지 않은 구문입니다.",
     "Invalid statement."),
    (r"^Invalid value$",
     "값 형식이 올바르지 않습니다. 문자열은 큰따옴표로 감싸고, 숫자/불리언/배열/테이블 형식을 확인하세요.",
     "The value has an invalid format. Wrap strings in double quotes, and check the number/boolean/array/table syntax."),
    (r"^Invalid date or datetime$",
     "날짜/시간 형식이 올바르지 않습니다.",
     "Invalid date/datetime format."),
    (r"^Invalid hex value$",
     "16진수 이스케이프 값이 올바르지 않습니다.",
     "Invalid hexadecimal escape value."),
    (r"^Unclosed array$",
     "배열이 닫히지 않았습니다. 항목 뒤 콤마(,) 또는 닫는 ']' 를 확인하세요.",
     "The array was never closed. Check for a comma (,) after the item or a closing ']'."),
    (r"^Unclosed inline table$",
     "인라인 테이블이 닫히지 않았습니다. 닫는 '}' 를 확인하세요.",
     "The inline table was never closed. Check for a closing '}'."),
    (r"^Unterminated string$",
     "문자열을 닫는 따옴표가 없습니다.",
     "The string is missing its closing quote."),
    (r"^Unescaped '\\' in a string$",
     "문자열 안의 '\\' 는 이스케이프 처리가 필요합니다.",
     "A '\\' inside a string must be escaped."),
    (r"^Escaped character is not a Unicode scalar value$",
     "이스케이프된 문자가 올바른 유니코드 문자가 아닙니다.",
     "The escaped character is not a valid Unicode scalar value."),
    (r"^Duplicate inline table key '(.+)'$",
     lambda m: f"인라인 테이블 키 '{m.group(1)}' 가 중복되었습니다.",
     lambda m: f"Inline table key '{m.group(1)}' is duplicated."),
    (r"^Found invalid character '(.+)'$",
     lambda m: f"허용되지 않는 문자 '{m.group(1)}' 가 있습니다.",
     lambda m: f"Contains a disallowed character '{m.group(1)}'."),
    (r"^Illegal character '(.+)'$",
     lambda m: f"허용되지 않는 문자 '{m.group(1)}' 가 있습니다.",
     lambda m: f"Contains a disallowed character '{m.group(1)}'."),
]


def _translate_toml_reason(reason: str) -> str:
    """Translate tomllib's English error reason into an easy-to-understand
    explanation in the current language. A reason not in the mapping is
    returned as-is (no information loss). / tomllib의 영문 오류 사유를 현재
    언어로 이해하기 쉽게 변환한다. 매핑에 없는 사유는 원문 그대로 반환한다
    (정보 손실 방지)."""
    for pattern, ko_repl, en_repl in _TOML_REASON_PATTERNS:
        m = re.match(pattern, reason)
        if m:
            repl = en_repl if _LANG == "en" else ko_repl
            return repl(m) if callable(repl) else repl
    return reason


def _format_toml_error(path: Path, e: tomllib.TOMLDecodeError) -> str:
    """Build a user-friendly message including the error line number, cause, and
    original source code frame. / 오류 라인 번호, 원인, 원문 코드 프레임을 포함한
    사용자 친화적 메시지를 만든다."""
    msg = str(e)
    m = _TOML_ERR_RE.match(msg)
    if not m:
        m_eof = _TOML_ERR_EOF_RE.match(msg)
        reason = _translate_toml_reason(m_eof.group(1)) if m_eof else msg
        return f"{_t('toml_syntax_error', name=path.name)}\n\n{reason}"

    reason_raw, lineno_s, colno_s = m.groups()
    lineno, colno = int(lineno_s), int(colno_s)
    reason = _translate_toml_reason(reason_raw)

    try:
        src_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        src_lines = []

    out = [_t("toml_syntax_error", name=path.name), "", f"Line {lineno}, Column {colno}", ""]
    if 1 <= lineno <= len(src_lines):
        start = max(1, lineno - 1)
        end   = min(len(src_lines), lineno + 1)
        width = len(str(end))
        for i in range(start, end + 1):
            out.append(f"{i:>{width}} | {src_lines[i - 1]}")
            if i == lineno:
                out.append(" " * width + " | " + " " * max(colno - 1, 0) + "^")
    out.append("")
    out.append(reason)
    return "\n".join(out)


# ── Config Loading / Config 로드 ───────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent

def load_config(config_path: str | None) -> dict:
    if config_path is None:
        path = _SCRIPT_DIR / "config.toml"
    else:
        path = Path(config_path)
        if not path.is_absolute():
            path = _SCRIPT_DIR / path
    if not path.exists():
        sys.exit(f"{_t('err_config_not_found')}: {path}")
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            sys.exit(_format_toml_error(path, e))


# ── Job Resolve: global defaults + job override / Job resolve: global 기본값 + job override ──

# Reserved keys that may be defined in a job table. Any key not in this list is
# treated as a placeholder default (defaults/Custom Key) — also used by
# validate_config()'s typo detection.
# Job 테이블에 정의될 수 있는 예약 Key. 이 목록에 없는 Key는 전부 placeholder
# 기본값(defaults/Custom Key)으로 취급된다 — validate_config()의 오탈자 감지에도 사용.
_JOB_STANDARD_KEYS = {
    "desc", "tool", "on_error", "parallel", "max_workers", "output",
    "pre", "commands", "post", "pause", "stderr_quiet", "params",
}

def resolve_job(config: dict, job_name: str) -> dict:
    g    = config.get("global", {})
    jobs = config.get("jobs", {})

    if job_name not in jobs:
        available = ", ".join(jobs.keys()) if jobs else _t("none_placeholder")
        sys.exit(f"{_t('err_job_not_found', job=job_name)}\n{_t('label_available_jobs')}: {available}")

    job = jobs[job_name]

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
        # Non-standard keys become placeholder defaults — overridden by CLI params if given
        # 비표준 키는 placeholder 기본값으로 — CLI 파라미터가 있으면 덮어씀
        "defaults":     {k: str(v) for k, v in job.items() if k not in _JOB_STANDARD_KEYS},
    }

    # Count of { msg = "..." } entries in the commands array — fixed number of
    # reserved lines per file (parallel output block size)
    # commands 배열 내 { msg = "..." } 항목 개수 — 파일당 고정 예약 줄 수 (병렬 출력 블록 크기)
    resolved["notes_per_file"] = sum(1 for c in resolved["commands"] if isinstance(c, dict))

    # Only jobs whose commands actually reference {output} are checked for the
    # "exit 0 but output file missing" failure case.
    # (a job that hardcodes the output path directly in commands is automatically
    # excluded from this check)
    # commands가 {output}을 실제로 참조하는 job만 "exit 0인데 출력 파일 미생성"을 실패로 검증한다.
    # (commands 키에 출력 경로를 직접 박아넣는 예외적인 job은 검증 대상에서 자동 제외됨)
    resolved["uses_output"] = any(
        isinstance(c, str) and "{output}" in c for c in resolved["commands"]
    )

    # Resolve tool path / tool 경로 resolve
    tool_name = resolved["tool_name"]
    if tool_name:
        resolved["tool_path"] = resolved["tools"].get(tool_name, tool_name)
    else:
        resolved["tool_path"] = ""

    return resolved


# ── Config Validation (diagnose config-file authoring mistakes) / Config Validation (설정 파일 작성 실수 진단) ──
# The goal is not to enforce a schema but to catch common typos/omissions early.
# Only ERROR aborts execution; WARNING/INFO are printed and execution continues normally.
# Custom Keys (non-standard job keys) remain freely allowed — this only diagnoses them.
# 목적은 스키마 강제가 아니라 흔한 오탈자/누락을 조기에 알려주는 것이다.
# ERROR만 실행을 중단시키고, WARNING/INFO는 출력 후 정상적으로 계속 진행한다.
# Custom Key(비표준 job key)는 계속 자유롭게 허용된다 — 여기서는 진단만 한다.

# The two kinds of context that actually fill in {input}/{output} etc.
# (must always be kept in sync with build_file_context / build_global_context)
# {input}/{output} 등이 실제로 채워지는 두 종류의 Context (build_file_context /
# build_global_context와 반드시 동일하게 유지할 것)
_FILE_CTX_BUILTIN_KEYS   = {"input", "dir", "name", "base", "ext", "index", "tool", "taskid", "itemid"}
_GLOBAL_CTX_BUILTIN_KEYS = {"tool", "max_workers", "taskid"}


def _extract_placeholders(template: str) -> set[str]:
    """Extract only {name} placeholder names, using the same rules as
    template.format_map() (escaped {{ }} is already filtered out by
    string.Formatter). / template.format_map()과 동일한 규칙으로 {name}
    placeholder 이름만 추출한다 (이스케이프된 {{ }} 는 string.Formatter가
    알아서 걸러준다)."""
    names: set[str] = set()
    try:
        for _, field_name, _, _ in string.Formatter().parse(template):
            if not field_name:
                continue
            base = field_name.split(".")[0].split("[")[0]
            if base:
                names.add(base)
    except ValueError:
        pass  # A malformed format string itself will surface at runtime via str.format_map()
              # 잘못된 포맷 문자열 자체는 실행 시점에 str.format_map()에서 드러남
    return names


def _job_command_text(entry) -> str:
    return entry.get("msg", "") if isinstance(entry, dict) else entry


def _collect_placeholder_findings(resolved: dict) -> tuple[list[str], set[str]]:
    """Return the list of undefined placeholders (WARNING text) and the set of
    all placeholder names actually referenced (used to determine unused Custom
    Keys). / 정의되지 않은 placeholder 목록(WARNING 문구)과, 실제로 참조된 모든
    placeholder 이름 집합(미사용 Custom Key 판정용)을 반환한다."""
    dynamic_keys = set(resolved["defaults"]) | {p.get("key") for p in resolved["params"] if p.get("key")}
    file_known   = _FILE_CTX_BUILTIN_KEYS | {"output"} | dynamic_keys
    output_known = _FILE_CTX_BUILTIN_KEYS | dynamic_keys       # the output template itself cannot reference {output}
                                                                 # output 템플릿 자신은 {output} 참조 불가
    global_known = _GLOBAL_CTX_BUILTIN_KEYS | dynamic_keys
    all_known    = file_known | global_known

    used_names: set[str] = set()
    undefined: dict[str, None] = {}  # dedup while preserving appearance order / 등장 순서를 보존한 dedup 용도

    def scan(template: str, known: set[str]) -> None:
        for name in _extract_placeholders(template):
            used_names.add(name)
            if name not in known and name not in undefined:
                undefined[name] = None

    scan(resolved["output"], output_known)
    for entry in resolved["commands"]:
        scan(_job_command_text(entry), file_known)
    for entry in resolved["pre"] + resolved["post"]:
        scan(_job_command_text(entry), global_known)

    warnings = []
    for name in undefined:
        line = f"{_t('vc_undefined_placeholder')}: {{{name}}}"
        suggestion = difflib.get_close_matches(name, all_known, n=1, cutoff=0.6)
        if suggestion:
            line += f"\n{_t('vc_suggestion_maybe')}: {{{suggestion[0]}}}"
        warnings.append(line)

    return warnings, used_names


def _collect_key_findings(resolved: dict, used_names: set[str]) -> tuple[list[str], list[str]]:
    """Among Custom Keys (non-standard job keys), report ones that look like a
    typo of a reserved word as WARNING, and ones never referenced anywhere as
    INFO (the typo case takes priority — no double reporting).
    Custom Key(비표준 job key) 중 예약어와 비슷한 오탈자는 WARNING으로,
    어디에서도 참조되지 않는 값은 INFO로 보고한다 (오탈자 쪽을 우선시하며 중복 보고하지 않음)."""
    warnings, infos = [], []
    for key in resolved["defaults"]:
        match = difflib.get_close_matches(key, _JOB_STANDARD_KEYS, n=1, cutoff=0.6)
        if match:
            warnings.append(f"{_t('vc_unknown_key')}: {key}\n{_t('vc_did_you_mean')} {match[0]}")
        elif key not in used_names:
            infos.append(f"{_t('vc_unused_key')}: {key}")
    return warnings, infos


def _collect_required_key_findings(resolved: dict) -> list[str]:
    errors = []
    if not resolved["tool_path"]:
        errors.append(f"{_t('vc_missing_required_key')}: tool ({_t('vc_missing_tool_hint')})")
    if not str(resolved["output"]).strip():
        errors.append(f"{_t('vc_missing_required_key')}: output")
    if not resolved["commands"]:
        errors.append(f"{_t('vc_missing_required_key')}: commands")
    return errors


# Reserved keys allowed at the top level of the [global] section
# (must always match what resolve_job() actually reads)
# [global] 섹션 최상위에 올 수 있는 예약 Key (resolve_job()이 실제로 읽는 것과 반드시 일치시킬 것)
_GLOBAL_STANDARD_KEYS = {
    "on_error", "parallel", "max_workers", "output", "log", "log_file",
    "pause", "stderr_quiet", "tools", "default_tool", "lang",
}


def _collect_global_key_findings(config: dict) -> tuple[list[str], list[str]]:
    """Diagnose non-standard keys in the [global] section. Unlike the job section,
    non-standard [global] keys are never used as placeholders anywhere (since
    build_global_context only merges the job's defaults), so even ones that
    don't resemble a typo are all reported as 'unused'.
    [global] 섹션의 비표준 key를 진단한다. job 섹션과 달리 [global]의 비표준 key는
    어디에서도 placeholder로 쓰이지 않으므로(build_global_context가 job의 defaults만 병합함),
    오탈자와 비슷하지 않아도 전부 '미사용'으로 보고한다."""
    warnings, infos = [], []
    for key in config.get("global", {}):
        if key in _GLOBAL_STANDARD_KEYS:
            continue
        match = difflib.get_close_matches(key, _GLOBAL_STANDARD_KEYS, n=1, cutoff=0.6)
        if match:
            warnings.append(f"{_t('vc_unknown_key')} (global): {key}\n{_t('vc_did_you_mean')} {match[0]}")
        else:
            infos.append(f"{_t('vc_unused_key')} (global): {key}")
    return warnings, infos


def _format_validation_report(job_name: str, errors: list[str], warnings: list[str], infos: list[str]) -> str:
    lines = ["=== Config Validation Result ===", "", f"Job: {job_name}"]
    for label, items in (("ERROR", errors), ("WARNING", warnings), ("INFO", infos)):
        if not items:
            continue
        lines.append("")
        lines.append(f"[{label}]")
        for item in items:
            sub_lines = item.split("\n")
            lines.append(f"- {sub_lines[0]}")
            lines.extend(f"  {s}" for s in sub_lines[1:])
    lines.append("")
    lines.append(_t("vc_summary_line", errors=len(errors), warnings=len(warnings), infos=len(infos)))
    return "\n".join(lines)


def validate_config(config: dict, job_name: str) -> None:
    """Diagnose common mistakes in the specified Job definition. When the Job
    itself doesn't exist, resolve_job() handles that separately as before, so
    it is left untouched here. / 지정된 Job 정의의 흔한 실수를 진단한다.
    Job 자체가 없는 경우는 resolve_job()이 기존 방식대로 별도 처리하므로
    여기서는 건드리지 않는다."""
    if job_name not in config.get("jobs", {}):
        return

    resolved = resolve_job(config, job_name)

    errors = _collect_required_key_findings(resolved)
    placeholder_warnings, used_names = _collect_placeholder_findings(resolved)
    key_warnings, infos = _collect_key_findings(resolved, used_names)
    global_warnings, global_infos = _collect_global_key_findings(config)
    warnings = key_warnings + placeholder_warnings + global_warnings
    infos    = infos + global_infos

    if not (errors or warnings or infos):
        return

    report = _format_validation_report(job_name, errors, warnings, infos)
    if errors:
        sys.exit(report)
    print(report)


# ── File List Loading / 파일 목록 로드 ─────────────────────────────────────────

def load_file_list(filelist_path: str) -> list[Path]:
    path = Path(filelist_path)
    if not path.exists():
        sys.exit(f"{_t('err_filelist_not_found')}: {filelist_path}")

    files = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = Path(line)
            if not p.exists():
                print(f"{_t('warn_file_missing')}: {line}", file=sys.stderr)
                continue
            files.append(p)

    if not files:
        sys.exit(_t("err_no_files"))

    return files


# ── Placeholder Substitution / Placeholder 치환 ────────────────────────────────

class SafeDict(dict):
    # SafeDict: an undefined placeholder is left as-is / 미정의 placeholder는 원문 유지
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

def substitute(template: str, context: dict) -> str:
    return template.format_map(SafeDict(context))


# ── Windows Short Path (8.3) Conversion / Windows 단축 경로 (8.3) 변환 ─────────

def _get_short_path(path: str) -> str:
    """Return the 8.3 ASCII short path via GetShortPathNameW. If the file/directory
    doesn't exist, recurse up to the parent directory.
    GetShortPathNameW로 8.3 ASCII 단축 경로를 반환한다.
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
    """True if the string contains a character that cannot be encoded in the
    system ACP (cp949, etc). / 시스템 ACP(cp949 등)로 인코딩 불가능한 문자가
    포함되어 있으면 True."""
    try:
        s.encode('mbcs')
        return False
    except UnicodeEncodeError:
        return True


# ── Temp ID Generation (UUID-based, avoids multiprocess filename collisions) / 임시 ID 생성 (UUID 기반, 멀티프로세싱 파일명 충돌 회피용) ──

def _gen_tmp_id() -> str:
    return "tmp_" + uuid.uuid4().hex[:12]


# ── Context Building (per file) / Context 빌드 (파일 단위) ────────────────────

def build_file_context(file_path: Path, index: int, job: dict, user_params: dict, task_id: str) -> tuple[dict, dict, str, str]:
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
        "taskid": task_id,
        "itemid": _gen_tmp_id(),
        **job.get("defaults", {}),  # non-standard keys in job (defaults) / job 내 비표준 키 (기본값)
        **user_params,              # CLI param takes priority / CLI 파라미터가 우선
    }
    output_path = substitute(job["output"], ctx)
    output_p = Path(output_path).resolve()
    same_dir = (output_p.parent == input_dir)

    # For { msg = "..." } message substitution — preserve the original (raw) value
    # before it gets wrapped in quotes for use as a command argument.
    # { msg = "..." } 메시지 치환용 — 명령 인자용 따옴표를 씌우기 전 원본(raw) 값을 보존한다.
    raw_ctx = dict(ctx)
    raw_ctx["output"] = output_path

    # Shorten {input}/{output} to just the filename (relative path) and run with
    # cwd=input_dir. subprocess.run(cwd=unicode_dir) passes cwd via CreateProcessW's
    # lpCurrentDirectory, which the OS resolves internally as a Unicode absolute
    # path, so ANSI-only tools also work correctly.
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


# ── Context for Pre/Post (excludes per-file placeholders) / Pre/Post용 Context (파일 단위 placeholder 제외) ──

def build_global_context(job: dict, user_params: dict, task_id: str) -> tuple[dict, dict]:
    tool = job["tool_path"]
    raw_ctx = {
        "tool":        tool,
        "max_workers": str(job.get("max_workers", "")),
        "taskid":      task_id,
        **job.get("defaults", {}),  # non-standard keys in job (defaults) / job 내 비표준 키 (기본값)
        **user_params,              # CLI param takes priority / CLI 파라미터가 우선
    }
    ctx = dict(raw_ctx)
    ctx["tool"] = f'"{tool}"' if tool else ""
    return ctx, raw_ctx


# ── Filename Truncation for Screen Display / 화면 표시용 파일명 축약 ───────────

def _char_width(ch: str) -> int:
    """Console display width of a single character. Uses the wcwidth package if
    installed, otherwise falls back to an east_asian_width-based approximation.
    단일 문자의 콘솔 표시 폭. wcwidth 패키지가 설치되어 있으면 이를 사용하고,
    없으면 east_asian_width 기반 근사치로 대체한다."""
    if _wcwidth_char is not None:
        w = _wcwidth_char(ch)
        if w >= 0:
            return w
        return 0  # Treat combining characters etc. (wcwidth returns negative) as width 0
                  # 결합문자 등 wcwidth가 음수를 반환하는 경우 폭 0 취급
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(s: str) -> int:
    """Compute console display width, treating fullwidth characters (Hangul,
    Hanja, Kana, etc.) as width 2 and everything else as width 1. Uses wcwidth's
    wcswidth for an accurate terminal display width if the package is installed,
    otherwise falls back to an east_asian_width-based approximation.
    한글/한자/가나 등 전각 문자는 폭 2, 그 외는 폭 1로 콘솔 표시 폭을 계산한다.
    wcwidth 패키지가 설치되어 있으면 wcswidth로 정확한 터미널 표시 폭을 계산하고,
    없으면 east_asian_width 기반 근사치로 대체한다."""
    if _wcswidth is not None:
        w = _wcswidth(s)
        if w >= 0:
            return w
    return sum(_char_width(ch) for ch in s)


def _max_name_display_len() -> int:
    """Compute the max display width per filename so that "[idx] in → out" fits on
    one line. Since input/output are printed side by side, each is set to a bit
    less than half the console width. / "[idx] in → out" 한 줄에 맞도록 파일명
    1개당 최대 표시 폭을 계산한다. input/output 두 개가 나란히 출력되므로 각각
    콘솔 폭의 절반보다 약간 작게 잡는다."""
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    overhead = len("[9999] ") + len(" → ")
    per_name = (cols - overhead) // 2 - 2
    return max(per_name, 10)


def _truncate_filename(name: str, max_width: int) -> str:
    """When displaying a long filename, always keep the extension and elide the
    middle with "...". Width is computed via _display_width, which treats
    fullwidth characters as 2 columns. / 긴 파일명을 표시할 때 확장자는 항상
    남기고, 중간을 "..."로 생략한다. 폭 계산은 전각 문자를 2칸으로 취급하는
    _display_width 기준."""
    if _display_width(name) <= max_width:
        return name
    stem = Path(name).stem
    ext = Path(name).suffix
    budget = max_width - _display_width(ext) - 3  # subtract the "..." width of 3 / "..." 폭 3 제외
    if budget < 10:
        budget = 10  # guarantee a minimum width / 최소 폭 보장
    if _display_width(stem) <= budget:
        return stem + ext
    width = 0
    cut = 0
    for i, ch in enumerate(stem):
        w = _char_width(ch)
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return stem[:cut] + "..." + ext


def _max_message_display_len() -> int:
    """Max width that fits a { msg = ... } line on one line. If the console line
    wraps, the ANSI cursor math breaks, so it must always be truncated to fit on
    a single line. / { msg = ... } 한 줄 표시에 맞는 최대 폭. 콘솔 줄바꿈이 생기면
    ANSI 커서 계산이 어긋나므로 반드시 한 줄 안에 들어오도록 자른다."""
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    return max(cols - 4, 10)


def _truncate_message(text: str, max_width: int) -> str:
    """Truncate the tail of a long message with "..." to fit a single line's width.
    긴 메시지를 한 줄 폭에 맞춰 말미를 "..."로 생략한다."""
    if _display_width(text) <= max_width:
        return text
    budget = max_width - 3
    width = 0
    cut = 0
    for i, ch in enumerate(text):
        w = _char_width(ch)
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return text[:cut] + "..."


# ── Order-Preserving Output Manager for Multithreading / 멀티스레드 순서 보장 출력 매니저 ──

def _enable_win_ansi() -> None:
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode   = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class OutputManager:
    """Receives start/note/finish events from threads and prints them.

    Each file occupies a fixed-size block (1 + notes_per_file lines).
    on_start()  -> buffers, and once its turn comes, prints the whole block
                   (title line + reserved blank lines for notes) at once
    on_note()   -> overwrites the reserved line within the block in place
                   (via ANSI, regardless of arrival order)
    on_finish() -> immediately overwrites the block's title line with the result,
                   in completion order (via ANSI, regardless of index order)

    If a later note never fires at all (e.g. due to on_error=stop), the reserved
    blank line simply stays blank — satisfying "flush as a blank line on abort"
    naturally, with no extra code needed.

    스레드로부터 start/note/finish 이벤트를 받아 출력한다.

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
                # If the block hasn't appeared on screen yet (rare), wait and apply it
                # when start is flushed / 블록이 아직 화면에 안 나왔으면(거의 없는 경우) 대기했다가 start flush 시 반영
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
        # Print start events in order (print the block — title line + reserved
        # blank lines for notes — all at once)
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

        # finish events: items whose start was printed are shown immediately in
        # completion order (regardless of index order)
        # finish 이벤트: start가 출력된 항목은 완료 순서대로 즉시 출력 (번호 순서 무관)
        for idx in sorted(k for k in list(self._finish_buf) if k in self._rows):
            in_name, out_name, ok = self._finish_buf.pop(idx)
            row                   = self._rows.pop(idx)
            mark                  = "→" if ok else "✗"
            max_len               = _max_name_display_len()
            line                  = f"[{idx:>4}] {_truncate_filename(in_name, max_len)} {mark} {_truncate_filename(out_name, max_len)}"
            up                    = self._line_count - row
            # \033[{up}A\r : move to target row  \033[K : clear the row  \033[{up}B\r : move back
            # \033[{up}A\r : 목표 행으로 이동  \033[K : 행 지우기  \033[{up}B\r : 복귀
            sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
            sys.stdout.flush()
            # Console is overwritten via ANSI; the log file only records the final result row
            # 콘솔은 ANSI 덮어쓰기, 로그 파일에는 완성된 결과 행만 기록
            self._logger.debug(line)


# ── Logging Setup / Logging 설정 ───────────────────────────────────────────────

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


# ── Windows Command-Line Parsing (CommandLineToArgvW) / Windows 명령줄 파싱 (CommandLineToArgvW) ──

_CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
_CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)

def _parse_cmdline(cmd: str) -> list[str]:
    """Parse directly via the Windows API without going through cmd.exe ->
    preserves Unicode paths. / cmd.exe를 거치지 않고 Windows API로 직접 파싱
    → Unicode 경로 보존."""
    argc = ctypes.c_int(0)
    argv = _CommandLineToArgvW(cmd, ctypes.byref(argc))
    if not argv:
        return [cmd]
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


# ── Single Command Execution / 단일 명령 실행 ──────────────────────────────────

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


# ── Pre / Post Execution (once for the whole batch) / Pre / Post 실행 (배치 전체 1회) ──

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

        # Run the same way as commands (parsed via CommandLineToArgvW, no shell).
        # cmd.exe builtins like echo must be written explicitly, e.g. "cmd /c echo ...".
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


# ── Single File Processing / 단일 파일 처리 ────────────────────────────────────

def process_file(
    file_path: Path,
    index: int,
    job: dict,
    user_params: dict,
    logger: logging.Logger,
    dry_run: bool,
    task_id: str,
    manager: "OutputManager | None" = None,
) -> tuple[bool, str]:
    ctx, raw_ctx, output_path, cwd = build_file_context(file_path, index, job, user_params, task_id)
    output_p = Path(output_path)
    quiet    = manager is not None

    if manager:
        manager.on_start(index, file_path.name)
    else:
        max_len = _max_name_display_len()
        logger.info(f"[{index:>4}] {_truncate_filename(file_path.name, max_len)} → {_truncate_filename(output_p.name, max_len)}")

    # When the path/filename contains a character outside the ACP range (e.g.
    # Japanese), copy it to a temporary ASCII path to work around ANSI-only tools.
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
                msg = f"FAILED [{index}] {file_path.name} | {_t('err_output_not_created')} | STDERR: {last_stderr.strip()}"
                if not quiet:
                    logger.error(msg)
                ret = (False, msg)
                return ret
            output_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_out), str(output_p))
        elif job["uses_output"] and not dry_run and not output_p.exists():
            # Prevent a silent success when commands references {output} but the
            # file doesn't actually exist after exit 0.
            # commands가 {output}을 참조하는데도 exit 0 이후 실제 파일이 없으면 조용한 성공을 막는다.
            msg = f"FAILED [{index}] {file_path.name} | {_t('err_output_not_created')} | STDERR: {last_stderr.strip()}"
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


# ── Job Execution Orchestrator / Job 실행 오케스트레이터 ──────────────────────

def run_job(
    job: dict,
    files: list[Path],
    user_params: dict,
    logger: logging.Logger,
    dry_run: bool,
) -> None:
    task_id = _gen_tmp_id()
    global_ctx, global_raw_ctx = build_global_context(job, user_params, task_id)
    total = len(files)

    # Verify tool exists / tool 존재 확인
    if job["tool_path"] and not dry_run:
        tool_p = Path(job["tool_path"])
        if not tool_p.exists():
            logger.warning(f"{_t('warn_tool_not_found')}: {job['tool_path']}")

    # Pre
    run_pre_post(job["pre"], global_ctx, global_raw_ctx, logger, dry_run, "PRE")

    success_count = 0
    failed_count  = 0

    if job["parallel"] and total > 1:
        # ── Parallel Processing / 병렬 처리 ─────────────────────────────────
        manager = OutputManager(logger, job["notes_per_file"])
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=job["max_workers"]) as executor:
            future_map = {
                executor.submit(process_file, f, i + 1, job, user_params, logger, dry_run, task_id, manager): i + 1
                for i, f in enumerate(files)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    ok, err = future.result()
                except Exception as exc:
                    ok  = False
                    err = f"[{idx}] {_t('err_exception')}: {exc}"
                if ok:
                    success_count += 1
                else:
                    failed_count += 1
                    if err:
                        errors.append((idx, err))
                    if job["on_error"] == "stop":
                        logger.error(_t("err_on_error_stop_cancel"))
                        for f in future_map:
                            f.cancel()
                        break
        for _, err in sorted(errors):
            logger.error(err)
    else:
        # ── Sequential Processing / 순차 처리 ───────────────────────────────
        for i, file_path in enumerate(files):
            try:
                ok, _ = process_file(file_path, i + 1, job, user_params, logger, dry_run, task_id)
            except Exception as exc:
                ok = False
                logger.error(f"[{i + 1}] {_t('err_exception')}: {exc}")
            if ok:
                success_count += 1
            else:
                failed_count += 1
                if job["on_error"] == "stop":
                    logger.error(_t("err_on_error_stop_abort"))
                    break

    # Post
    run_pre_post(job["post"], global_ctx, global_raw_ctx, logger, dry_run, "POST")

    # logger.info("=" * 60)
    logger.info(_t("info_job_summary", success=success_count, failed=failed_count, total=total))
    # logger.info("=" * 60)


# ── Error Output / Emergency Log (for crashes before setup_logging) / 오류 출력 / 긴급 로그 (setup_logging 이전 크래시용) ──

def _emergency_log(msg: str) -> None:
    """Record an error that occurred before the logger was initialized into
    tcbp_error.log in the script's folder. / logger가 초기화되기 전 오류를
    스크립트 폴더의 tcbp_error.log에 기록한다."""
    try:
        import datetime
        path = _SCRIPT_DIR / "tcbp_error.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n{msg}\n")
    except Exception:
        pass


def _pause_on_error(msg: str) -> None:
    """Print the error to the console and wait for Enter so the window doesn't
    close immediately. / 오류 내용을 콘솔에 출력하고 Enter를 기다려 창이
    닫히지 않게 한다."""
    print(f"\n{msg}", flush=True)
    input(_t("prompt_error_pause"))


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    _logger: logging.Logger | None = None
    _job:    dict | None           = None
    _set_lang(_prescan_lang(sys.argv[1:]))  # so --help itself shows in the right language
                                             # --help 자체도 올바른 언어로 보이도록
    try:
        args        = parse_args()
        _set_lang(args.lang)
        user_params = parse_params(args.params)
        config      = load_config(args.config)
        if args.lang is None:
            _set_lang(config.get("global", {}).get("lang"))
        validate_config(config, args.job)
        _job        = resolve_job(config, args.job)
        _logger     = setup_logging(_job["log"], _job["log_file"])

        # If this line is in the log file, setup_logging succeeded
        # 로그 파일에 이 줄이 있으면 setup_logging까지는 성공한 것
        if _job["desc"]:
            _logger.info(f"Job: {args.job} — {_job['desc']}")
        if args.dry_run:
            _logger.info(_t("info_dry_run_mode"))

        user_params = prompt_missing_params(_job, user_params)
        files       = load_file_list(args.filelist)

        mode = f"parallel (max_workers={_job['max_workers']})" if _job["parallel"] else "sequential"
        _logger.info(_t("info_file_count", count=len(files), mode=mode))

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
            print(_t("prompt_press_any_key"), flush=True)
            keyboard.read_event(suppress=True)
        except ImportError:
            input(_t("prompt_press_any_key"))


if __name__ == "__main__":
    main()
