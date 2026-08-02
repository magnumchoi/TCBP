#!/usr/bin/env python3
"""
[ko]
tcbp.py - Total Commander Batch Python (v2.4)
TOML 기반 범용 배치 처리 엔진

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]

[en]
tcbp.py - Total Commander Batch Python (v2.3)
A generic TOML-based batch processing engine

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]
"""

import sys, ctypes, tomllib, unicodedata, logging, subprocess
import argparse, shutil, tempfile, threading, uuid, datetime
import re, dataclasses, importlib.util, typing, fnmatch
from dataclasses import dataclass
from typing import Literal, Callable, TypeVar, ClassVar, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from wcwidth import wcswidth as _wcswidth, wcwidth as _wcwidth_char
except ImportError:
    _wcswidth = None
    _wcwidth_char = None

"""
[ko]
현재 실행 중인 모듈을 "tcbp"라는 고정 이름으로 별칭 등록한다. 이렇게 해야
동적으로 로드되는 플러그인(load_plugin(), PART 4 참고) 안의 `from tcbp import ...`가
tcbp.py가 __main__으로 실행 중이든 validate_config.py 등에서 라이브러리로
import됐든 항상 이 실행 중인 모듈 인스턴스를 가리킨다. 이게 없으면 플러그인의
`from tcbp import ...`가 tcbp.py를 별개의 모듈로 다시 실행시켜, 여기서 정의한
클래스(PluginInfo, FileSession 등)에 대한 isinstance 검사가 정상 플러그인에서도
항상 실패하게 된다.

[en]
Alias the currently-executing module under the fixed name "tcbp" so that
`from tcbp import ...` inside a dynamically-loaded plugin (see load_plugin(),
PART 4) always resolves to THIS running module instance — whether tcbp.py
itself is running as __main__ or is being imported as a library (e.g. from
validate_config.py). Without this, a plugin's own `from tcbp import ...`
would re-execute tcbp.py as a second, distinct module object, and isinstance
checks against classes defined here (PluginInfo, FileSession, ...) would
always fail even for a correctly-written plugin.
"""
sys.modules.setdefault("tcbp", sys.modules[__name__])


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 1. 초기화 & 다국어 메시지
# [en] PART 1. BOOTSTRAP & I18N (Internationalization)
# ═══════════════════════════════════════════════════════════════════════════
"""
[ko]
i18n - 실행 중 출력 문구 카탈로그 (영어/한국어)
tcbp.py 자신이 출력하는 문구(오류, 경고, 로그 줄, --help 텍스트)만 이 경로를 거친다.
config.toml에 사용자가 직접 작성한 콘텐츠(job desc, { msg = "..." } 문구)는
작성자가 쓴 그대로 두며 자동 번역하지 않는다.

[en]
i18n - runtime message catalog
Only messages tcbp.py itself prints (errors, warnings, log lines, --help text) go
through this. User-authored content in config.toml (job `desc`, `{ msg = "..." }`
text) is left as the author wrote it — never auto-translated.
"""
_LANG = "ko"  # [ko] 기본값. --lang 또는 config.toml의 [global].lang으로 재설정됨 / [en] default; overridden by --lang or config.toml's [global].lang

_MESSAGES: dict[str, dict[str, str]] = {
    "ko": {
        "cli_description":       "Total Commander Batch Python - TOML 기반 배치 처리 엔진",
        "cli_epilog_header":     "예시:",
        "help_job":              "실행할 Job 이름",
        "help_filelist":         "입력 파일 목록 텍스트 파일 (input_mode=\"directory\" Job은 대신 폴더 경로)",
        "help_params":           "Named 파라미터",
        "help_config":           "설정 파일 경로 (기본: tcbp.py와 같은 폴더의 config.toml)",
        "help_dry_run":          "명령 출력만 하고 실행 안 함",
        "help_strict":           "FileSession 플러그인의 log() slot 초과 시 경고 대신 즉시 예외로 중단 (플러그인 개발/검증용)",
        "help_lang":             "출력 언어 (ko/en). 기본값은 config.toml의 global.lang, 없으면 ko",
        "err_need_integer":      "  [오류] 정수를 입력하세요.",
        "err_need_bool":         "  [오류] true/false/1/0/yes/no/on/off 중 하나를 입력하세요.",
        "err_tool_and_plugin_both": "[오류] Job '{job}': tool과 plugin을 동시에 지정할 수 없습니다.",
        "err_plugin_not_found":  "[오류] 플러그인 '{name}'을(를) 찾을 수 없습니다: {path}",
        "err_plugin_import_failed": "[오류] 플러그인 '{name}' import 실패: {error}",
        "err_plugin_no_run":     "[오류] 플러그인 '{name}'에 run() 함수가 없습니다.",
        "err_plugin_invalid_metadata": "[오류] 플러그인 '{name}'의 run()에 @plugin(...) 메타정보가 없거나 유효하지 않습니다.",
        "err_plugin_not_thread_safe_parallel": "[오류] Job '{job}': 플러그인 '{name}'은(는) thread_safe=False로 선언되어 있어 parallel=true와 함께 쓸 수 없습니다. config.toml에서 parallel=false로 바꾸거나 max_workers=1로 순차 처리하세요.",
        "err_param_type_mismatch": "[오류] 파라미터 '{param}' 타입 불일치 (type=\"{type}\" 기대, 값={value!r})",
        "warn_param_format":     "[경고] 파라미터 형식 오류 (무시됨)",
        "warn_param_format_hint": "key=value 형식 필요",
        "toml_syntax_error":     "[오류] {name} 문법 오류",
        "err_config_not_found":  "[오류] 설정 파일 없음",
        "err_job_not_found":     "[오류] Job '{job}' 없음.",
        "label_available_jobs":  "사용 가능한 Job",
        "none_placeholder":      "(없음)",
        "err_filelist_not_found": "[오류] 파일 목록 없음",
        "warn_file_missing":     "[경고] 파일 없음 (건너뜀)",
        "err_no_files":          "[오류] 처리할 파일이 없습니다.",
        "err_directory_not_found": "[오류] 폴더를 찾을 수 없음",
        "err_input_mode_expects_directory": "[오류] Job '{job}'는 input_mode=\"directory\"로 선언되었는데, 전달된 경로가 폴더가 아닙니다",
        "err_input_mode_expects_list":      "[오류] Job '{job}'는 input_mode=\"list\"(기본값)인데, 전달된 경로가 폴더입니다 — 폴더를 입력하려면 config.toml에 input_mode = \"directory\"를 설정하세요",
        "vc_missing_required_key": "필수 Key 누락",
        "vc_missing_tool_hint":  "또는 global.tools 에 등록된 tool 이름이 필요합니다",
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
        "label_processing":      "처리 중...",
    },
    "en": {
        "cli_description":       "Total Commander Batch Python - a generic TOML-based batch processing engine",
        "cli_epilog_header":     "Examples:",
        "help_job":              "Name of the Job to run",
        "help_filelist":         "Text file listing the input files (or a folder path, for input_mode=\"directory\" Jobs)",
        "help_params":           "Named parameters",
        "help_config":           "Config file path (default: config.toml next to tcbp.py)",
        "help_dry_run":          "Print commands only; don't execute them",
        "help_strict":           "FileSession plugins: abort immediately on log() slot overflow instead of warning (for plugin dev/testing)",
        "help_lang":             "Output language (ko/en). Defaults to config.toml's global.lang, or ko if unset",
        "err_need_integer":      "  [ERROR] Please enter an integer.",
        "err_need_bool":         "  [ERROR] Please enter one of: true/false/1/0/yes/no/on/off.",
        "err_tool_and_plugin_both": "[ERROR] Job '{job}': tool and plugin cannot both be set.",
        "err_plugin_not_found":  "[ERROR] Plugin '{name}' not found: {path}",
        "err_plugin_import_failed": "[ERROR] Failed to import plugin '{name}': {error}",
        "err_plugin_no_run":     "[ERROR] Plugin '{name}' has no run() function.",
        "err_plugin_invalid_metadata": "[ERROR] Plugin '{name}''s run() is missing valid @plugin(...) metadata.",
        "err_param_type_mismatch": "[ERROR] Param '{param}' type mismatch (expected type=\"{type}\", value={value!r})",
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
        "err_directory_not_found": "[ERROR] Directory not found",
        "err_input_mode_expects_directory": "[ERROR] Job '{job}' is declared with input_mode=\"directory\", but the path given is not a directory",
        "err_input_mode_expects_list":      "[ERROR] Job '{job}' has input_mode=\"list\" (the default), but the path given is a directory — set input_mode = \"directory\" in config.toml to accept a folder",
        "vc_missing_required_key": "Missing required key",
        "vc_missing_tool_hint":  "or a tool name registered in global.tools is required",
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
        "label_processing":      "Processing...",
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
    """
    [ko] --lang 값을 argparse 파싱 전에 미리 알아내어 --help 텍스트도 올바른 언어로 보여준다.
    [en] Detect --lang before argparse runs, so --help text is shown in the right language too.
    """
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


# [ko] Windows 콘솔 UTF-8 출력 보장
# [en] Guarantee UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 1B. 엄격한 dataclass & 플러그인 계약
# [en] PART 1B. STRICT DATACLASS & PLUGIN CONTRACT
# ═══════════════════════════════════════════════════════════════════════════
"""
[ko]
strict_dataclass: pydantic이 있으면 pydantic.dataclasses.dataclass를 그대로
쓰고, 없으면 표준 dataclasses.dataclass + 최소 isinstance 기반 __post_init__
검증으로 폴백한다 (플러그인 확장 계획서 3.8.1). Session/PluginInfo/ExecResult/
BatchResult(PART 3)가 이 데코레이터에 의존하므로 그보다 먼저 정의한다.
PluginInfo/@plugin: 플러그인의 run() 함수에 메타정보를 부착하는 데코레이터
(모듈 레벨 PLUGIN_INFO dict 방식 대체, 5.2 참고).

[en]
strict_dataclass: uses pydantic.dataclasses.dataclass as-is if pydantic is
available, otherwise falls back to a standard dataclasses.dataclass plus
minimal isinstance-based validation in __post_init__ (plugin expansion plan
3.8.1). Defined before Session/PluginInfo/ExecResult/BatchResult (PART 3),
since they depend on this decorator.
PluginInfo/@plugin: the decorator that attaches metadata to a plugin's run()
function (replaces the old module-level PLUGIN_INFO dict approach, see 5.2).
"""

try:
    from pydantic.dataclasses import dataclass as strict_dataclass
except ImportError:
    def _loose_isinstance(value: Any, hint: Any) -> bool:
        origin = typing.get_origin(hint)
        if origin is Literal:
            return value in typing.get_args(hint)
        if origin is not None:
            return isinstance(value, origin)
        return not isinstance(hint, type) or isinstance(value, hint)

    def strict_dataclass(*, frozen: bool = True):
        """
        [ko]
        pydantic 미설치 시 폴백: 표준 dataclass + __post_init__에서 필드
        타입을 isinstance로 재검증한다 (완전한 pydantic 검증만큼 촘촘하지는
        않음 — 3.8.1의 알려진 한계 참고).

        [en]
        Fallback for when pydantic isn't installed: a standard dataclass plus
        re-validating field types via isinstance in __post_init__ (not as
        thorough as full pydantic validation — see the known limitation in
        3.8.1).
        """
        def _wrap(cls):
            hints = typing.get_type_hints(cls)
            user_post_init = cls.__dict__.get("__post_init__")

            def __post_init__(self):
                for f in dataclasses.fields(self):
                    v, hint = getattr(self, f.name), hints.get(f.name)
                    if hint is not None and not _loose_isinstance(v, hint):
                        raise TypeError(f"{cls.__name__}.{f.name}: expected {hint}, got {type(v).__name__}")
                if user_post_init:
                    user_post_init(self)

            cls.__post_init__ = __post_init__
            return dataclasses.dataclass(frozen=frozen)(cls)
        return _wrap

    print("[INFO] pydantic이 설치되지 않았습니다. pip install pydantic 으로 설치하면 더 엄격한 타입 검증을 받을 수 있습니다.", file=sys.stderr)
    print("[INFO] pydantic 없이 표준 dataclass 기반 폴백으로 계속 진행합니다.", file=sys.stderr)


@strict_dataclass(frozen=True)
class PluginInfo:
    name: str
    version: str
    author: str
    session_type: Literal["file", "batch"]
    requirements: list = dataclasses.field(default_factory=list)
    notes_per_file: int = 0
    # [ko] FileSession 플러그인이 모듈 전역/클래스 변수 등 파일 간 공유 상태를
    #      락 없이 안전하게 다룰 수 없게 작성됐다면 False로 선언한다 (플러그인
    #      가이드 5.10절). parallel=true(+max_workers>1) Job에 매칭되면
    #      _require_essentials()/validate_config.py가 즉시 실행을 거부한다.
    #      BatchSession은 애초에 병렬 실행되지 않으므로(2.3절) 의미가 없다.
    # [en] Declare False if a FileSession plugin can't safely handle state
    #      shared across files (a module-level global, a class variable)
    #      without a lock (plugin guide, Section 5.10). If matched with a
    #      parallel=true (+max_workers>1) Job, _require_essentials()/
    #      validate_config.py refuse to run it immediately. Meaningless for
    #      BatchSession, which is never run in parallel to begin with (2.3).
    thread_safe: bool = True


_PluginFunc = TypeVar("_PluginFunc", bound=Callable[..., Any])


def plugin(
    *, name: str, version: str, author: str,
    session_type: Literal["file", "batch"],
    requirements: list | None = None,
    notes_per_file: int = 0,
    thread_safe: bool = True,
) -> Callable[[_PluginFunc], _PluginFunc]:
    """
    [ko]
    플러그인의 run() 함수에 붙이는 데코레이터. PluginInfo를 만들어
    run.plugin_info에 부착한다 — 잘못된 값은 여기서(plugin import 시점) 즉시
    실패한다 (5.5의 (a) fail-fast).

    [en]
    The decorator attached to a plugin's run() function. Builds a PluginInfo
    and attaches it to run.plugin_info — an invalid value fails immediately
    right here, at plugin import time (5.5's (a) fail-fast).
    """
    info = PluginInfo(
        name=name, version=version, author=author,
        session_type=session_type,
        requirements=list(requirements or []),
        notes_per_file=notes_per_file,
        thread_safe=thread_safe,
    )
    def _decorator(func: _PluginFunc) -> _PluginFunc:
        func.plugin_info = info
        return func
    return _decorator


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 2. Windows API 유틸리티
# [en] PART 2. WINDOWS API UTILITIES
"""
[ko]
파일 전체에서 쓰이는 Win32 API 직접 호출 모음: 8.3 단축 경로 변환, ACP 인코딩
가능 여부 확인, ANSI 이스케이프 활성화, cmd.exe 없이 argv 파싱.

[en]
Direct Win32 calls used across the file: 8.3 short-path conversion, ACP
encodability check, ANSI escape enablement, and argv parsing without cmd.exe.
"""
# ═══════════════════════════════════════════════════════════════════════════

def _get_short_path(path: str) -> str:
    """
    [ko]
    GetShortPathNameW로 8.3 ASCII 단축 경로를 반환한다.
    파일/디렉토리가 존재하지 않으면 부모 디렉토리까지 재귀적으로 올라간다.

    [en]
    Return the 8.3 ASCII short path via GetShortPathNameW. If the file/directory
    doesn't exist, recurse up to the parent directory.
    """
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 32768)
    if n > 0:
        return buf.value
    p = Path(path)
    if p.parent == p:
        return path
    return str(Path(_get_short_path(str(p.parent))) / p.name)


def _has_non_acp(s: str) -> bool:
    """
    [ko] 시스템 ACP(cp949 등)로 인코딩 불가능한 문자가 포함되어 있으면 True.
    [en] True if the string contains a character that cannot be encoded in the system ACP (cp949, etc).
    """
    try:
        s.encode('mbcs')
        return False
    except UnicodeEncodeError:
        return True


def _enable_win_ansi() -> None:
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode   = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
_CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)

def _parse_cmdline(cmd: str) -> list[str]:
    """
    [ko] cmd.exe를 거치지 않고 Windows API로 직접 파싱 → Unicode 경로 보존.
    [en] Parse directly via the Windows API without going through cmd.exe -> preserves Unicode paths.
    """
    argc = ctypes.c_int(0)
    argv = _CommandLineToArgvW(cmd, ctypes.byref(argc))
    if not argv:
        return [cmd]
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 3. 데이터 모델
# [en] PART 3. DATA MODELS
"""
[ko]
ConfigLoader / ContextBuilder / CommandExecutor / JobRunner가 공유하는
데이터클래스. dict/tuple을 느슨하게 주고받는 대신 타입을 명시해두는 것이
클래스를 분리할 수 있게 하는 전제 조건이며, 향후 플러그인 코드가 기댈 수
있는 안정적인 계약이 된다.

[en]
Dataclasses shared across ConfigLoader / ContextBuilder / CommandExecutor /
JobRunner. Keeping these as explicit types (rather than loose dict/tuple
passing) is what lets those classes be split apart in the first place, and
gives future plugin code a stable contract to build against.
"""
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class JobParam:
    key: str
    desc: str = ""
    type: str = ""


@dataclass
class ResolvedJob:
    desc:           str
    tool_name:      str
    tool_path:      str
    on_error:       str
    parallel:       bool
    max_workers:    int
    output:         str
    pre:            list
    commands:       list
    post:           list
    log:            bool
    log_file:       str
    pause:          bool
    tools:          dict[str, str]
    stderr_quiet:   bool
    params:         list[JobParam]
    defaults:       dict[str, str]
    notes_per_file: int
    uses_output:    bool
    plugin_name:            str  = ""     # [ko] plugin = "..." (6장) — tool과 상호 배타적 / [en] plugin = "..." (Chapter 6) — mutually exclusive with tool
    allow_output_overwrite: bool = False  # [ko] output이 의도적으로 input을 덮어써도 되는 Job (범용 opt-out) / [en] a Job whose output intentionally overwrites input (general opt-out)
    input_mode: str       = "list"        # [ko] "list" | "directory" — FileList 인자의 계약(12장) / [en] "list" | "directory" — the contract for the FileList argument (Chapter 12)
    recursive:  bool      = False         # [ko] input_mode="directory"일 때 하위 폴더까지 재귀 탐색 / [en] when input_mode="directory", search subfolders recursively
    include:    list      = dataclasses.field(default_factory=list)  # [ko] input_mode="directory"일 때 적용할 글롭 패턴 목록 (비어있으면 전체) / [en] glob patterns applied when input_mode="directory" (empty means everything)


@dataclass
class FileContext:
    ctx:         dict
    raw_ctx:     dict
    output_path: str
    cwd:         str


@dataclass
class GlobalContext:
    ctx:     dict
    raw_ctx: dict


@strict_dataclass(frozen=True)
class ExecResult:
    """
    [ko]
    CLI Job과 FileSession 플러그인 Job이 공유하는 파일 1개 처리 결과.
    이제 plugin↔TCBP 경계를 넘는 값이므로(3.4), 다른 내부 전용 dataclass와
    달리 strict_dataclass로 검증한다.

    [en]
    The single-file processing result shared by CLI Jobs and FileSession
    plugin Jobs. Since this value now crosses the plugin↔TCBP boundary (3.4),
    unlike other internal-only dataclasses, it is validated via
    strict_dataclass.
    """
    success: bool
    message: str = ""


@strict_dataclass(frozen=True)
class BatchResult:
    """
    [ko]
    BatchSession 플러그인의 run() 반환값 (3.4/8.3.4). succeeded/failed는
    session.filelist 전체를 다 채우지 않아도 된다 — TCBP는 강제하지 않는다.

    [en]
    The return value of a BatchSession plugin's run() (3.4/8.3.4).
    succeeded/failed don't need to fully cover session.filelist — TCBP
    doesn't enforce that.
    """
    succeeded: list = dataclasses.field(default_factory=list)
    failed:    list = dataclasses.field(default_factory=list)


@strict_dataclass(frozen=True)
class FileSession:
    """
    [ko]
    FileSession 플러그인의 run(session) 인자 (3.4~3.7, 8.2). log() 호출을
    제외하고 읽기 전용이다. _log_fn은 ClassVar라 필드 검증 대상이 아니며,
    TCBP가 세션 생성 직후 object.__setattr__으로 인스턴스별 콜백을 주입한다
    (frozen 우회 — 3.5/8.1 참고).

    [en]
    The argument to a FileSession plugin's run(session) (3.4-3.7, 8.2).
    Read-only aside from calling log(). _log_fn is a ClassVar, so it's not
    subject to field validation; TCBP injects a per-instance callback via
    object.__setattr__ right after constructing the session (bypassing
    frozen — see 3.5/8.1).
    """
    input:  str
    output: str
    itemid: int   # [ko] 파일당 1-based 순번. ctx["itemid"](임시파일명용 랜덤 문자열)와는 무관 — 혼동 금지. / [en] 1-based per-file sequence number. Unrelated to ctx["itemid"] (a random string for temp filenames) — don't confuse the two.
    taskid: str
    params: dict

    _log_fn: ClassVar[Callable[[str, int], None] | None] = None

    def log(self, text: str, slot: int = 0) -> None:
        fn = getattr(self, "_log_fn", None)
        if fn is not None:
            fn(text, slot)


@strict_dataclass(frozen=True)
class BatchSession:
    """
    [ko]
    BatchSession 플러그인의 run(session) 인자 (8.3). filelist는 TCBP가 이미
    읽고 존재 확인까지 마친 절대경로 문자열 리스트다 (8.3.1).

    [en]
    The argument to a BatchSession plugin's run(session) (8.3). filelist is a
    list of absolute-path strings TCBP has already read and confirmed exist
    (8.3.1).
    """
    filelist: list
    output:   str | None
    taskid:   str
    params:   dict

    _log_fn: ClassVar[Callable[[str, int], None] | None] = None

    def log(self, text: str, slot: int = 0) -> None:
        fn = getattr(self, "_log_fn", None)
        if fn is not None:
            fn(text, slot)


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 4. CLI 파싱 & ConfigLoader
# [en] PART 4. CLI & CONFIG LOADER
# ═══════════════════════════════════════════════════════════════════════════

# [ko] CLI 파싱
# [en] CLI Parsing
"""
[ko]
`params`는 임의 개수의 key=value를 받기 위해 nargs=REMAINDER를 쓴다.
REMAINDER의 단점: 한 번 소비를 시작하면 이후 토큰을 전부 그대로 삼킨다 —
filelist 뒤에 오는 --dry-run 같은 플래그도 예외가 아니다. _split_known_flags()가
사용자가 어디에 입력했든 인식되는 플래그를 argv에서 미리 뽑아내어, REMAINDER는
job/filelist/key=value 토큰만 보게 한다.

[en]
`params` uses nargs=REMAINDER so it can collect an open-ended list of
key=value pairs. REMAINDER's downside: once it starts consuming, it grabs
every remaining token verbatim — including flags like --dry-run if they
appear after `filelist`. _split_known_flags() pulls recognized flags out of
argv up front (regardless of where the user typed them) so REMAINDER only
ever sees job/filelist/key=value tokens.
"""

_FLAGS_WITH_VALUE = {"--config", "--lang"}
_FLAGS_BOOL       = {"--dry-run", "-h", "--help", "--strict"}

def _split_known_flags(argv: list[str]) -> list[str]:
    """
    [ko]
    인식되는 플래그를 원래 상대 순서 그대로 앞으로 옮기고, 그 뒤에
    나머지 토큰(job/filelist/params)을 원래 상대 순서 그대로 이어붙인다.

    [en]
    Reorder argv so recognized flags come first, in original relative order,
    followed by the remaining tokens (job/filelist/params) in original relative
    order.
    """
    flags: list[str] = []
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        name = a.split("=", 1)[0]
        if name in _FLAGS_WITH_VALUE:
            if "=" in a:
                flags.append(a)
                i += 1
            elif i + 1 < len(argv):
                flags.extend([a, argv[i + 1]])
                i += 2
            else:
                flags.append(a)  # [ko] 값 누락; argparse가 평소대로 오류를 내도록 둠 / [en] missing value; let argparse raise its usual error
                i += 1
        elif a in _FLAGS_BOOL:
            flags.append(a)
            i += 1
        else:
            remaining.append(a)
            i += 1
    return flags + remaining


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
    parser.add_argument("--strict", action="store_true", help=_t("help_strict"))
    parser.add_argument("--lang", choices=["ko", "en"], default=None, help=_t("help_lang"))
    return parser.parse_args(_split_known_flags(sys.argv[1:]))


# [ko] Named params 파싱
# [en] Named Params Parsing

def prompt_missing_params(job: ResolvedJob, user_params: dict) -> dict:
    declared = job.params
    if not declared:
        return user_params
    result = dict(user_params)
    for meta in declared:
        key = meta.key
        if not key or key in result:
            continue
        while True:
            raw = input(f"  {meta.desc or key}: ").strip()
            if meta.type == "int":
                if raw.lstrip("-").isdigit():
                    result[key] = raw
                    break
                print(_t("err_need_integer"))
            elif meta.type == "bool":
                if raw.strip().lower() in (_BOOL_TRUE | _BOOL_FALSE):
                    result[key] = raw
                    break
                print(_t("err_need_bool"))
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


# [ko] bool·int 파라미터 타입 변환 (14.1)
# [en] bool/int Param Type Conversion (14.1)
# [ko] CLI key=value와 TOML params 값은 전부 문자열이므로, 파이썬 내장 bool("false")
#      == True인 함정을 피하기 위해 변환 규칙을 명시적으로 고정한다.
# [en] CLI key=value and TOML params values are always strings, so the
#      conversion rules are fixed explicitly to avoid the trap of Python's
#      built-in bool("false") == True.

_BOOL_TRUE  = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}


def _to_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v in _BOOL_TRUE:
        return True
    if v in _BOOL_FALSE:
        return False
    raise ValueError(f"invalid bool value: {raw!r} (expected one of {sorted(_BOOL_TRUE | _BOOL_FALSE)})")


def _coerce_params(user_params: dict, declared: list["JobParam"]) -> dict:
    """
    [ko]
    job.params에 type이 선언된 키만 실제 int/bool로 변환한다. 선언 안 된
    키(job.defaults 등)는 그대로 문자열로 둔다. 변환 실패 시 validate_config.py의
    vc_type_mismatch류 메시지와 같은 형태로 즉시 에러 처리한다.

    [en]
    Only converts keys declared with a type in job.params into actual
    int/bool values. Undeclared keys (e.g. job.defaults) are left as plain
    strings. On conversion failure, fails immediately with a message in the
    same style as validate_config.py's vc_type_mismatch family.
    """
    result = dict(user_params)
    for meta in declared:
        if meta.key not in result or not meta.type:
            continue
        raw = result[meta.key]
        try:
            if meta.type == "int":
                result[meta.key] = int(raw)
            elif meta.type == "bool":
                result[meta.key] = _to_bool(raw)
        except (ValueError, TypeError):
            sys.exit(_t("err_param_type_mismatch", param=meta.key, type=meta.type, value=raw))
    return result


# [ko] TOML 문법 오류 메시지 개선
# [en] TOML Syntax Error Message Improvement
# [ko] tomllib은 라인/컬럼 속성을 따로 노출하지 않고 "(at line N, column M)" 형태로
#      메시지에 포함시키므로, 이를 파싱해 원문 코드 프레임과 함께 보여준다.
# [en] tomllib does not expose line/column as separate attributes; it embeds them in
#      the message as "(at line N, column M)", so we parse that and show it together
#      with the original source code frame.

_TOML_ERR_RE     = re.compile(r"^(.*?)\s*\(at line (\d+), column (\d+)\)\s*$")
_TOML_ERR_EOF_RE = re.compile(r"^(.*?)\s*\(at end of document\)\s*$")

# [ko] (정규식, 한국어 설명, 영어 설명) — 캡처값을 삽입해야 하는 사유는 람다로 작성.
# [en] (regex, Korean reason, English reason) — each reason is a literal string or a
#      lambda taking the regex match, for reasons that embed a captured value.
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
    """
    [ko]
    tomllib의 영문 오류 사유를 현재 언어로 이해하기 쉽게 변환한다. 매핑에 없는
    사유는 원문 그대로 반환한다 (정보 손실 방지).

    [en]
    Translate tomllib's English error reason into an easy-to-understand
    explanation in the current language. A reason not in the mapping is
    returned as-is (no information loss).
    """
    for pattern, ko_repl, en_repl in _TOML_REASON_PATTERNS:
        m = re.match(pattern, reason)
        if m:
            repl = en_repl if _LANG == "en" else ko_repl
            return repl(m) if callable(repl) else repl
    return reason


def _format_toml_error(path: Path, e: tomllib.TOMLDecodeError) -> str:
    """
    [ko] 오류 라인 번호, 원인, 원문 코드 프레임을 포함한 사용자 친화적 메시지를 만든다.
    [en] Build a user-friendly message including the error line number, cause, and original source code frame.
    """
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


# [ko] Job Resolve keys: Job 테이블에 정의될 수 있는 예약 Key. 이 목록에 없는 Key는
#      전부 placeholder 기본값(defaults/Custom Key)으로 취급된다 — 검증 로직의
#      오탈자 감지에도 사용.
# [en] Job Resolve keys: reserved keys that may be defined in a job table. Any
#      key not in this list is treated as a placeholder default (defaults/Custom
#      Key) — also used by validation's typo detection.
_JOB_STANDARD_KEYS = {
    "desc", "tool", "plugin", "on_error", "parallel", "max_workers", "output",
    "pre", "commands", "post", "pause", "stderr_quiet", "params",
    "allow_output_overwrite", "input_mode", "recursive", "include",
}

class ConfigLoader:
    """
    [ko]
    config.toml을 로드하고 Job 정의를 ResolvedJob으로 resolve한다.
    저작 실수 진단(undefined placeholder, 오탈자 키 등)은 이 클래스가 하지
    않는다 — 그건 전부 별도의 validate_config.py 도구가 담당하며, 그쪽에서
    ConfigLoader/ResolvedJob을 import해 이 resolve 로직을 중복 없이 재사용한다.
    tcbp.py 자신은 아래 _require_essentials()의 최소 fail-fast 가드만 유지한다
    (완전 무방비 상태로 실행하면 config 오탈자가 알아보기 힘든 실행 오류로
    번질 수 있기 때문 — 자세한 이유는 _require_essentials() docstring 참고).

    [en]
    Loads config.toml and resolves Job definitions into a ResolvedJob.
    This class does no authoring-mistake diagnostics (undefined placeholders,
    typo'd keys, etc.) — that lives entirely in the separate validate_config.py
    tool, which imports ConfigLoader/ResolvedJob to reuse this same resolution
    logic without duplicating it. tcbp.py itself only keeps the minimal
    fail-fast guard in _require_essentials() below, since a completely
    unguarded run can turn a config typo into a confusing runtime failure
    (see _require_essentials' docstring).
    """

    def __init__(self, config_path: str | None):
        self._path   = self._resolve_path(config_path)
        self._config: dict | None = None

    @staticmethod
    def _resolve_path(config_path: str | None) -> Path:
        if config_path is None:
            return _SCRIPT_DIR / "config.toml"
        path = Path(config_path)
        if not path.is_absolute():
            path = _SCRIPT_DIR / path
        return path

    def load(self) -> dict:
        if self._config is None:
            if not self._path.exists():
                sys.exit(f"{_t('err_config_not_found')}: {self._path}")
            with open(self._path, "rb") as f:
                try:
                    self._config = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    sys.exit(_format_toml_error(self._path, e))
        return self._config

    def resolve_job(self, job_name: str) -> ResolvedJob:
        config = self.load()
        g      = config.get("global", {})
        jobs   = config.get("jobs", {})

        if job_name not in jobs:
            available = ", ".join(jobs.keys()) if jobs else _t("none_placeholder")
            sys.exit(f"{_t('err_job_not_found', job=job_name)}\n{_t('label_available_jobs')}: {available}")

        job = jobs[job_name]

        # [ko] tool과 plugin은 상호 배타적이다 (2.1). 병합된 필드가 아니라 원본(raw)
        #      job dict로 검사해야 global.default_tool 상속으로 인한 오탐을 피한다.
        # [en] tool and plugin are mutually exclusive (2.1). Checking the raw job
        #      dict (not the merged field) avoids a false positive from
        #      global.default_tool inheritance.
        if "tool" in job and "plugin" in job:
            sys.exit(_t("err_tool_and_plugin_both", job=job_name))

        tool_name = job.get("tool", g.get("default_tool", ""))
        tools     = g.get("tools", {})

        resolved = ResolvedJob(
            desc         = job.get("desc", ""),
            tool_name    = tool_name,
            tool_path    = tools.get(tool_name, tool_name) if tool_name else "",
            on_error     = job.get("on_error",    g.get("on_error",    "continue")),
            parallel     = job.get("parallel",    g.get("parallel",    False)),
            max_workers  = job.get("max_workers", g.get("max_workers", 4)),
            output       = job.get("output", g.get("output", "{dir}/{base}_out{ext}")),
            pre          = job.get("pre",      []),
            commands     = job.get("commands", []),
            post         = job.get("post",     []),
            log          = g.get("log",      False),
            log_file     = g.get("log_file", "logs/tcbp_{job}_{timestamp}.log"),
            pause        = job.get("pause",  g.get("pause", False)),
            tools        = tools,
            stderr_quiet = job.get("stderr_quiet", g.get("stderr_quiet", False)),
            # [ko] 비표준 키는 placeholder 기본값으로 — CLI 파라미터가 있으면 덮어씀
            # [en] Non-standard keys become placeholder defaults — overridden by CLI params if given
            params       = [JobParam(key=p.get("key", ""), desc=p.get("desc", ""), type=p.get("type", ""))
                             for p in job.get("params", [])],
            defaults     = {k: str(v) for k, v in job.items() if k not in _JOB_STANDARD_KEYS},
            notes_per_file = 0,
            uses_output    = False,
            plugin_name             = job.get("plugin", ""),
            allow_output_overwrite  = job.get("allow_output_overwrite", False),
            input_mode = job.get("input_mode", g.get("input_mode", "list")),
            recursive  = job.get("recursive",  g.get("recursive",  False)),
            include    = job.get("include",    g.get("include",    [])),
        )

        # [ko] commands 배열 내 { msg = "..." } 항목 개수 — 파일당 고정 예약 줄 수 (병렬 출력 블록 크기)
        # [en] Count of { msg = "..." } entries in the commands array — fixed number of
        #      reserved lines per file (parallel output block size)
        resolved.notes_per_file = sum(1 for c in resolved.commands if isinstance(c, dict))

        # [ko] commands가 {output}을 실제로 참조하는 job만 "exit 0인데 출력 파일 미생성"을 실패로 검증한다.
        # [en] Only jobs whose commands actually reference {output} are checked for the
        #      "exit 0 but output file missing" failure case.
        resolved.uses_output = any(
            isinstance(c, str) and "{output}" in c for c in resolved.commands
        )

        return resolved


def _require_essentials(job: ResolvedJob, plugin_info: "PluginInfo | None" = None, job_name: str = "") -> None:
    """
    [ko]
    Job을 resolve한 직후 1회 실행하는 최소 fail-fast 가드. config 저작 실수가
    명확한 오류 대신 알아보기 힘든 실행 오류로 번지는 걸 막는다. 예를 들어
    빈 {tool} placeholder는 아무 일도 안 일어나는 게 아니라, 치환된 명령이
    "convert ..."로 시작하게 되는데 Windows에는 실제로 자체 convert.exe(FAT->NTFS
    변환용)가 있어서 엉뚱하게 그게 실행될 수 있다. 더 깊은 저작 진단(undefined
    placeholder, 오탈자 키, 존재하지 않는 tool 경로, dry-run 샘플 검사 등)은 전부
    validate_config.py에 있다 — 여기서는 tcbp.py가 말이 안 되는 걸 실행하지
    않도록 막는 최소한만 한다.

    [en]
    Minimal fail-fast guard, run once right after resolving a Job, so a
    config authoring mistake doesn't turn into a confusing runtime failure
    instead of a clear one. For example: an empty {tool} placeholder isn't a
    no-op — the substituted command starts with "convert ...", and Windows
    actually ships its own convert.exe (FAT->NTFS conversion), so the tool
    would attempt to run *that* instead of failing cleanly. Deeper authoring
    diagnostics (undefined placeholders, typo'd keys, unreachable tool paths,
    dry-run sample checks, ...) live entirely in validate_config.py — this is
    only the minimum needed for tcbp.py to refuse to run something nonsensical.
    Also refuses a FileSession plugin declared thread_safe=False (5.10) when
    matched with parallel=true + max_workers>1 — running it anyway would
    silently risk a race condition instead of failing cleanly.
    """
    missing = []
    if not job.plugin_name:
        if not job.tool_path:
            missing.append(f"tool ({_t('vc_missing_tool_hint')})")
        if not job.commands:
            missing.append("commands")
    # [ko] BatchSession 플러그인은 output 생략 가능 (8.3.2) — plugin_info를 모르면(=CLI/tool
    #      Job이거나 아직 로드 전) 기존처럼 필수로 취급한다.
    # [en] BatchSession plugins may omit output (8.3.2) — if plugin_info is unknown
    #      (a CLI/tool Job, or not loaded yet), treat it as required as before.
    output_required = not (plugin_info and plugin_info.session_type == "batch")
    if output_required and not str(job.output).strip():
        missing.append("output")
    if missing:
        sys.exit(f"{_t('vc_missing_required_key')}: {', '.join(missing)}")

    # [ko] thread_safe=False 플러그인 + parallel=true(+max_workers>1)는 실행 자체를
    #      거부한다 — max_workers=1이면 ThreadPoolExecutor가 있어도 워커가 하나뿐이라
    #      동시 실행이 일어나지 않으므로 위험하지 않다 (플러그인 가이드 5.10절).
    # [en] Refuse to run a thread_safe=False plugin combined with
    #      parallel=true (+max_workers>1) outright — with max_workers=1, even
    #      though a ThreadPoolExecutor exists, only one worker is ever active,
    #      so no concurrent execution actually happens and there's no risk
    #      (plugin guide, Section 5.10).
    if (plugin_info and plugin_info.session_type == "file" and not plugin_info.thread_safe
            and job.parallel and job.max_workers > 1):
        sys.exit(_t("err_plugin_not_thread_safe_parallel", job=job_name, name=job.plugin_name))


# [ko] 플러그인 로딩 (5.3, 5.5)
# [en] Plugin Loading (5.3, 5.5)
# [ko] ./plugin/<name>.py로의 매핑은 결정론적이다 — 별도 탐색/등록 메커니즘 없음.
#      tcbp.py 런타임과 validate_config.py가 이 두 함수를 그대로 공유해, 플러그인
#      로딩 로직이 두 곳에서 따로 구현되며 어긋나는 일이 없게 한다.
# [en] Mapping to ./plugin/<name>.py is deterministic — there is no separate
#      discovery/registration mechanism. The tcbp.py runtime and
#      validate_config.py share these two functions as-is, so the plugin
#      loading logic is never implemented twice and never drifts apart.

def _plugin_path(name: str) -> Path:
    return _SCRIPT_DIR / "plugin" / f"{name}.py"


def load_plugin(name: str) -> Callable:
    """
    [ko]
    ./plugin/<name>.py를 import하고, @plugin(...)으로 검증된 run() 함수를
    반환한다. run(session)은 절대 호출하지 않는다 — import까지만 한다.
    실패 시 i18n 메시지를 담은 RuntimeError를 던진다 (5.5).

    [en]
    Imports ./plugin/<name>.py and returns its run() function, validated via
    @plugin(...). Never calls run(session) — import only. Raises a
    RuntimeError carrying an i18n message on failure (5.5).
    """
    path = _plugin_path(name)
    if not path.exists():
        raise RuntimeError(_t("err_plugin_not_found", name=name, path=str(path)))
    spec = importlib.util.spec_from_file_location(f"tcbp_plugin_{name}", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(_t("err_plugin_import_failed", name=name, error=str(exc))) from exc
    run_fn = getattr(module, "run", None)
    if run_fn is None or not callable(run_fn):
        raise RuntimeError(_t("err_plugin_no_run", name=name))
    info = getattr(run_fn, "plugin_info", None)
    if not isinstance(info, PluginInfo):
        raise RuntimeError(_t("err_plugin_invalid_metadata", name=name))
    return run_fn


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 5. 파일 목록 로드 & Placeholder Context 빌드
# [en] PART 5. CONTEXT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

# [ko] 파일 목록 로드
# [en] File List Loading

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


# [ko] 폴더 입력 모드 — File Enumerator (12장)
# [en] Directory Input Mode — File Enumerator (Chapter 12)

def _walk_files_depth_first(dir_path: Path, patterns: list) -> list[Path]:
    """
    [ko]
    dir_path 한 폴더의 항목을 이름순으로 나눠, 그 폴더 자신의 대상 파일을 먼저
    담고 그 다음에 하위 폴더를 이름순으로 재귀 처리한다 — 폴더 이름이 숫자
    문자열(예: "001")이면 절대경로 문자열 전체를 정렬할 때 형제 파일명(예:
    "009.bmp")보다 앞뒤로 끼어들 수 있는 문제(12장)를 없애, "현재 폴더 자신의
    파일 → 하위 폴더들(이름순, 각각 재귀 동일 규칙)" 순서를 보장한다.

    [en]
    Splits one folder's entries by name, collecting that folder's own matching
    files first, then recursing into its subfolders in name order. This avoids
    the problem (Chapter 12) where a numeric folder name (e.g. "001") can sort
    before or after a sibling filename (e.g. "009.bmp") when the full absolute
    path string is sorted as one flat string — guaranteeing instead "this
    folder's own files → its subfolders (by name, same rule recursively)".
    """
    entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    matched: set[Path] = set()
    for pattern in patterns:
        matched.update(p for p in entries if p.is_file() and fnmatch.fnmatch(p.name, pattern))
    files = sorted(matched, key=lambda p: p.name)
    for entry in entries:
        if entry.is_dir():
            files.extend(_walk_files_depth_first(entry, patterns))
    return files


def enumerate_directory(dir_path: Path, recursive: bool, include: list) -> list[Path]:
    """
    [ko]
    폴더(dir_path)를 스캔해 대상 파일 목록을 만든다 — input_mode="directory" Job의
    File Enumerator 역할. include가 비어 있으면 모든 파일이 대상이고, recursive=true면
    하위 폴더까지 재귀 탐색한다. 정렬은 실행마다 파일시스템이 반환하는 순서에
    좌우되지 않도록 항상 이름순이며, recursive=true일 때는 "폴더 자신의 파일 먼저,
    그다음 하위 폴더를 이름순으로" 규칙(_walk_files_depth_first)을 적용해
    {index}/병렬 출력 순서가 재현 가능하면서도 디렉토리 구조를 직관적으로 따르게 한다.

    [en]
    Scans a folder (dir_path) to build the target file list — the File
    Enumerator for input_mode="directory" Jobs. If include is empty, every
    file is a candidate; if recursive=true, subfolders are searched too.
    Sorting is always by name so it never depends on whatever order the
    filesystem happens to return; when recursive=true, the "own files first,
    then subfolders by name" rule (_walk_files_depth_first) is applied so
    {index}/parallel output ordering is both reproducible and follows the
    directory structure intuitively.
    """
    patterns = include or ["*"]
    if recursive:
        files = _walk_files_depth_first(dir_path, patterns)
    else:
        found: set[Path] = set()
        for pattern in patterns:
            found.update(p for p in dir_path.glob(pattern) if p.is_file())
        files = sorted(found, key=lambda p: p.name)

    if not files:
        sys.exit(_t("err_no_files"))
    return files


def resolve_input_files(filelist_arg: str, job: ResolvedJob, job_name: str) -> list[Path]:
    """
    [ko]
    CLI의 FileList 인자를 job.input_mode 계약에 따라 해석한다.
    "directory": 인자가 실제 폴더여야 하며, enumerate_directory()로 파일 목록을 만든다.
    "list"(기본값): 인자가 폴더면 안 되며, 기존 load_file_list()로 목록 파일을 읽는다.
    계약과 실제 인자 종류가 어긋나면 그 자리에서 명확한 에러로 즉시 중단한다 (12장).

    [en]
    Interprets the CLI's FileList argument according to job.input_mode's
    contract. "directory": the argument must actually be a directory;
    enumerate_directory() builds the file list. "list" (the default): the
    argument must not be a directory; the existing load_file_list() reads it
    as a list file. If the contract and the actual argument type disagree,
    aborts immediately with a clear error (Chapter 12).
    """
    if job.input_mode == "directory":
        path = Path(filelist_arg).resolve()
        if not path.exists():
            sys.exit(f"{_t('err_directory_not_found')}: {filelist_arg}")
        if not path.is_dir():
            sys.exit(f"{_t('err_input_mode_expects_directory', job=job_name)}: {filelist_arg}")
        return enumerate_directory(path, job.recursive, job.include)

    if Path(filelist_arg).is_dir():
        sys.exit(f"{_t('err_input_mode_expects_list', job=job_name)}: {filelist_arg}")
    return load_file_list(filelist_arg)


# [ko] Placeholder 치환
# [en] Placeholder Substitution

class SafeDict(dict):
    # [ko] SafeDict: 미정의 placeholder는 원문 유지
    # [en] SafeDict: an undefined placeholder is left as-is
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

def substitute(template: str, context: dict) -> str:
    return template.format_map(SafeDict(context))


# [ko] 임시 ID 생성 (UUID 기반, 멀티프로세싱 파일명 충돌 회피용)
# [en] Temp ID Generation (UUID-based, avoids multiprocess filename collisions)

def _gen_tmp_id() -> str:
    return "tmp_" + uuid.uuid4().hex[:12]


class ContextBuilder:
    """
    [ko]
    Job의 {placeholder} 치환 context를 만든다 — 파일 단위(build_file_context)와
    배치 전체 1회(build_global_context, pre/post용). Job/user params/task id를
    생성 시점에 고정된 불변 상태로 갖고 있으므로, 병렬 처리용 워커 스레드들이
    인스턴스 하나를 읽기 전용으로 공유해도 안전하다.

    [en]
    Builds the {placeholder} substitution context for a Job — per-file
    (build_file_context) and once for the whole batch (build_global_context,
    used by pre/post). Holds the Job/user params/task id as immutable state
    set at construction time, so a single instance can be shared read-only
    across the worker threads used for parallel processing.
    """

    def __init__(self, job: ResolvedJob, user_params: dict, task_id: str):
        self._job         = job
        self._user_params = user_params
        self._task_id      = task_id

    def build_file_context(self, file_path: Path, index: int) -> FileContext:
        file_path = file_path.resolve()
        input_dir = file_path.parent
        ctx: dict[str, str] = {
            "input":  str(file_path),
            "dir":    str(input_dir),
            "name":   file_path.name,
            "base":   file_path.stem,
            "ext":    file_path.suffix,
            "index":  str(index),
            "tool":   self._job.tool_path,
            "taskid": self._task_id,
            "itemid": _gen_tmp_id(),
            **self._job.defaults,  # [ko] job 내 비표준 키 (기본값) / [en] non-standard keys in job (defaults)
            **self._user_params,   # [ko] CLI 파라미터가 우선 / [en] CLI param takes priority
        }
        output_path = substitute(self._job.output, ctx)
        output_p = Path(output_path).resolve()
        same_dir = (output_p.parent == input_dir)

        # [ko] { msg = "..." } 메시지 치환용 — 명령 인자용 따옴표를 씌우기 전 원본(raw) 값을 보존한다.
        # [en] For { msg = "..." } message substitution — preserve the original (raw) value
        #      before it gets wrapped in quotes for use as a command argument.
        raw_ctx = dict(ctx)
        raw_ctx["output"] = output_path

        """
        [ko]
        {input}/{output}를 파일명(상대 경로)으로 줄이고 cwd=input_dir 로 실행.
        subprocess.run(cwd=unicode_dir)은 CreateProcessW lpCurrentDirectory로 전달되어
        OS가 내부적으로 Unicode 절대 경로로 해석하므로 ANSI 도구도 정상 동작한다.

        [en]
        Shorten {input}/{output} to just the filename (relative path) and run with
        cwd=input_dir. subprocess.run(cwd=unicode_dir) passes cwd via CreateProcessW's
        lpCurrentDirectory, which the OS resolves internally as a Unicode absolute
        path, so ANSI-only tools also work correctly.
        """
        ctx["input"]  = f'"{file_path.name}"'
        ctx["output"] = f'"{output_p.name}"' if same_dir else f'"{_get_short_path(str(output_p))}"'
        ctx["dir"]    = f'"{_get_short_path(str(input_dir))}"'
        ctx["name"]   = f'"{file_path.name}"'
        ctx["base"]   = f'"{file_path.stem}"'
        ctx["tool"]   = f'"{self._job.tool_path}"' if self._job.tool_path else ""

        return FileContext(ctx=ctx, raw_ctx=raw_ctx, output_path=output_path, cwd=str(input_dir))

    def build_global_context(self) -> GlobalContext:
        tool = self._job.tool_path
        raw_ctx = {
            "tool":        tool,
            "max_workers": str(self._job.max_workers),
            "taskid":      self._task_id,
            **self._job.defaults,  # [ko] job 내 비표준 키 (기본값) / [en] non-standard keys in job (defaults)
            **self._user_params,   # [ko] CLI 파라미터가 우선 / [en] CLI param takes priority
        }
        ctx = dict(raw_ctx)
        ctx["tool"] = f'"{tool}"' if tool else ""
        return GlobalContext(ctx=ctx, raw_ctx=raw_ctx)


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 6. 화면 표시 폭 계산 & 멀티스레드 출력
# [en] PART 6. DISPLAY & OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

# [ko] 화면 표시용 파일명 축약
# [en] Filename Truncation for Screen Display

def _char_width(ch: str) -> int:
    """
    [ko]
    단일 문자의 콘솔 표시 폭. wcwidth 패키지가 설치되어 있으면 이를 사용하고,
    없으면 east_asian_width 기반 근사치로 대체한다.

    [en]
    Console display width of a single character. Uses the wcwidth package if
    installed, otherwise falls back to an east_asian_width-based approximation.
    """
    if _wcwidth_char is not None:
        w = _wcwidth_char(ch)
        if w >= 0:
            return w
        return 0  # [ko] 결합문자 등 wcwidth가 음수를 반환하는 경우 폭 0 취급 / [en] Treat combining characters etc. (wcwidth returns negative) as width 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(s: str) -> int:
    """
    [ko]
    한글/한자/가나 등 전각 문자는 폭 2, 그 외는 폭 1로 콘솔 표시 폭을 계산한다.
    wcwidth 패키지가 설치되어 있으면 wcswidth로 정확한 터미널 표시 폭을 계산하고,
    없으면 east_asian_width 기반 근사치로 대체한다.

    [en]
    Compute console display width, treating fullwidth characters (Hangul,
    Hanja, Kana, etc.) as width 2 and everything else as width 1. Uses wcwidth's
    wcswidth for an accurate terminal display width if the package is installed,
    otherwise falls back to an east_asian_width-based approximation.
    """
    if _wcswidth is not None:
        w = _wcswidth(s)
        if w >= 0:
            return w
    return sum(_char_width(ch) for ch in s)


def _max_name_display_len() -> int:
    """
    [ko]
    "[idx] in → out" 한 줄에 맞도록 파일명 1개당 최대 표시 폭을 계산한다.
    input/output 두 개가 나란히 출력되므로 각각 콘솔 폭의 절반보다 약간 작게 잡는다.

    [en]
    Compute the max display width per filename so that "[idx] in → out" fits on
    one line. Since input/output are printed side by side, each is set to a bit
    less than half the console width.
    """
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    overhead = len("[9999] ") + len(" → ")
    per_name = (cols - overhead) // 2 - 2
    return max(per_name, 10)


def _truncate_filename(name: str, max_width: int) -> str:
    """
    [ko]
    긴 파일명을 표시할 때 확장자는 항상 남기고, 중간을 "..."로 생략한다.
    폭 계산은 전각 문자를 2칸으로 취급하는 _display_width 기준.

    [en]
    When displaying a long filename, always keep the extension and elide the
    middle with "...". Width is computed via _display_width, which treats
    fullwidth characters as 2 columns.
    """
    if _display_width(name) <= max_width:
        return name
    stem = Path(name).stem
    ext = Path(name).suffix
    budget = max_width - _display_width(ext) - 3  # [ko] "..." 폭 3 제외 / [en] subtract the "..." width of 3
    if budget < 10:
        budget = 10  # [ko] 최소 폭 보장 / [en] guarantee a minimum width
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
    """
    [ko]
    { msg = ... } 한 줄 표시에 맞는 최대 폭. 콘솔 줄바꿈이 생기면
    ANSI 커서 계산이 어긋나므로 반드시 한 줄 안에 들어오도록 자른다.

    [en]
    Max width that fits a { msg = ... } line on one line. If the console line
    wraps, the ANSI cursor math breaks, so it must always be truncated to fit on
    a single line.
    """
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    return max(cols - 4, 10)


def _truncate_message(text: str, max_width: int) -> str:
    """
    [ko] 긴 메시지를 한 줄 폭에 맞춰 말미를 "..."로 생략한다.
    [en] Truncate the tail of a long message with "..." to fit a single line's width.
    """
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


# [ko] 멀티스레드 순서 보장 출력 매니저
# [en] Order-Preserving Output Manager for Multithreading

class OutputManager:
    """
    [ko]
    스레드로부터 start/note/finish 이벤트를 받아 출력한다.

    파일 1개는 고정 크기 블록(1 + notes_per_file 줄)을 차지한다.
    on_start()  → 버퍼링 후 순서가 되면 블록 전체(제목줄 + note 예약 빈 줄)를 한 번에 출력
    on_note()   → 블록 내 지정된 예약 줄을 그 자리에서 덮어씀 (ANSI, 도착 순서 무관)
    on_finish() → 블록의 제목줄을 완료 순서대로 즉시 결과로 덮어씀 (ANSI, 번호 순서 무관)

    on_error=stop 등으로 뒤의 note가 아예 발생하지 않으면, 예약된 빈 줄이 그대로 남아
    "중단 시 빈 칸으로 flush"를 별도 코드 없이 자연스럽게 만족한다.

    [en]
    Receives start/note/finish events from threads and prints them.

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
    """

    def __init__(self, logger: logging.Logger, notes_per_file: int = 0) -> None:
        _enable_win_ansi()
        self._logger        = logger
        self._lock          = threading.Lock()
        self._notes_per_file = notes_per_file
        self._block_height   = 1 + notes_per_file
        self._start_buf  : dict[int, str]                        = {}
        self._finish_buf : dict[int, tuple[str, str, bool, str]] = {}
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
                # [ko] 블록이 아직 화면에 안 나왔으면(거의 없는 경우) 대기했다가 start flush 시 반영
                # [en] If the block hasn't appeared on screen yet (rare), wait and apply it
                #      when start is flushed
                self._pending_notes.setdefault(idx, {})[slot] = text
                return
            self._write_note(idx, slot, text)

    def on_finish(self, idx: int, in_name: str, out_name: str, ok: bool, note: str = "") -> None:
        # [ko] note가 있으면 별도 예약 줄이 아니라 제목줄 자체에 줄바꿈 없이 덧붙여 표시한다
        # [en] if note is given, it is appended in place on the title line itself
        #      (no line break) rather than on a separate reserved line
        with self._lock:
            self._finish_buf[idx] = (in_name, out_name, ok, note)
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
        # [ko] start 이벤트를 순서대로 출력 (제목줄 + note용 예약 빈 줄을 블록으로 한 번에 출력)
        # [en] Print start events in order (print the block — title line + reserved
        #      blank lines for notes — all at once)
        while self._next_start in self._start_buf:
            idx      = self._next_start
            filename = self._start_buf.pop(idx)
            self._rows[idx] = self._line_count
            # [ko] on_finish()가 이 줄을 완료 결과로 덮어쓰기 전까지, 대기 중인 파일이
            #      멈춘 것처럼 보이지 않도록 "처리 중..." 표시를 붙여둔다
            # [en] until on_finish() overwrites this line with the result, tag it
            #      "Processing..." so a queued file doesn't look like it has stalled
            sys.stdout.write(f"[{idx:>4}] {filename} {_t('label_processing')}\n")
            sys.stdout.write("\n" * self._notes_per_file)
            self._line_count += self._block_height
            sys.stdout.flush()
            self._next_start += 1
            for slot, text in sorted(self._pending_notes.pop(idx, {}).items()):
                self._write_note(idx, slot, text)

        # [ko] finish 이벤트: start가 출력된 항목은 완료 순서대로 즉시 출력 (번호 순서 무관)
        # [en] finish events: items whose start was printed are shown immediately in
        #      completion order (regardless of index order)
        for idx in sorted(k for k in list(self._finish_buf) if k in self._rows):
            in_name, out_name, ok, note = self._finish_buf.pop(idx)
            row                   = self._rows.pop(idx)
            mark                  = "→" if ok else "✗"
            max_len               = _max_name_display_len()
            line                  = f"[{idx:>4}] {_truncate_filename(in_name, max_len)} {mark} {_truncate_filename(out_name, max_len)}"
            if note:
                line = _truncate_message(f"{line}  {note}", _max_message_display_len())
            up                    = self._line_count - row
            # [ko] \033[{up}A\r : 목표 행으로 이동  \033[K : 행 지우기  \033[{up}B\r : 복귀
            # [en] \033[{up}A\r : move to target row  \033[K : clear the row  \033[{up}B\r : move back
            sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
            sys.stdout.flush()
            # [ko] 콘솔은 ANSI 덮어쓰기, 로그 파일에는 완성된 결과 행만 기록
            # [en] Console is overwritten via ANSI; the log file only records the final result row
            self._logger.debug(line)


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 7. 로깅 설정
# [en] PART 7. LOGGING
# ═══════════════════════════════════════════════════════════════════════════

# [ko] Logging 설정
# [en] Logging Setup

def _resolve_log_path(log_file: str, job_name: str) -> Path:
    """
    [ko]
    log_file 안의 {job}/{timestamp} 자리표시자를 치환하고, 상대경로면
    _SCRIPT_DIR 기준으로 고정한다 — 여러 번 실행해도 한 파일에 계속 쌓이지
    않고 실행마다 별도 파일로 분리되게 한다.

    [en]
    Expand {job}/{timestamp} placeholders in log_file and anchor the result
    to _SCRIPT_DIR if relative, so repeated runs land in their own file instead
    of appending to one shared log.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    expanded  = log_file.format(job=job_name or "job", timestamp=timestamp)
    path      = Path(expanded)
    return path if path.is_absolute() else _SCRIPT_DIR / path


class _FileOnlyFilter(logging.Filter):
    """
    [ko]
    logger.warning(msg, extra={"file_only": True})로 남긴 레코드를 콘솔
    핸들러에서만 걸러낸다 (파일 핸들러는 그대로 통과) — FileSession 플러그인의
    slot 초과 경고가 parallel 모드의 ANSI 블록 렌더링을 깨지 않도록 하기 위함
    (10.3.1.1).

    [en]
    Filters out records logged via logger.warning(msg, extra={"file_only": True})
    from the console handler only (the file handler still passes them through)
    — so a FileSession plugin's slot-overflow warning doesn't corrupt the ANSI
    block rendering in parallel mode (10.3.1.1).
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "file_only", False)


def setup_logging(log: bool, log_file: str, job_name: str = "") -> logging.Logger:
    logger = logging.getLogger("tcbp")
    logger.setLevel(logging.DEBUG)

    # [ko] 콘솔은 레벨 프리픽스 없는 순수 메시지를 유지하고(OutputManager의 ANSI
    #      덮어쓰기가 이를 전제로 함), 파일에는 타임스탬프+레벨을 남겨 별도의
    #      *_failed.log 없이도 실패 건만 필터링(grep "[ERROR]")할 수 있게 한다.
    # [en] Console keeps the bare message (OutputManager's ANSI overwrite relies on
    #      no level prefix); the file gets timestamp+level so failures can be
    #      filtered (grep "[ERROR]") without spinning off a separate *_failed.log.
    console_fmt = logging.Formatter("%(message)s")
    file_fmt    = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(console_fmt)
    ch.addFilter(_FileOnlyFilter())
    logger.addHandler(ch)

    if log and log_file:
        log_path = _resolve_log_path(log_file, job_name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    return logger


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 8. CommandExecutor & JobRunner
# [en] PART 8. EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class CommandExecutor:
    """
    [ko]
    Job의 명령을 실행한다. logger/dry_run/stderr_quiet을 생성 시점에 고정된
    불변 상태로 갖는다(Job 실행 1회 동안 항상 동일한 값이므로), 병렬 파일
    처리용 워커 스레드들이 인스턴스 하나를 안전하게 공유할 수 있다.

    [en]
    Runs shell commands for a Job. Holds logger/dry_run/stderr_quiet as
    immutable state set at construction (all constant for the duration of a
    single Job run), so one instance is shared safely across the worker
    threads used for parallel file processing.
    """

    def __init__(self, logger: logging.Logger, dry_run: bool, stderr_quiet: bool = False):
        self._logger       = logger
        self._dry_run       = dry_run
        self._stderr_quiet = stderr_quiet

    def run(self, cmd: str, cwd: str | None = None, quiet: bool = False) -> ExecResult:
        if self._dry_run:
            self._logger.info(f"  [DRY-RUN] {cmd}")
            return ExecResult(True, "")

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
                    self._logger.info(f"  {line}")
            if result.stderr.strip() and not self._stderr_quiet:
                for line in result.stderr.strip().splitlines():
                    self._logger.warning(f"  STDERR: {line}")

        return ExecResult(result.returncode == 0, result.stderr)

    def run_pre_post(self, commands: list, global_ctx: GlobalContext, label: str) -> None:
        """
        [ko] Pre/Post 실행 (배치 전체 1회).
        [en] Run Pre/Post commands once for the whole batch.
        """
        for cmd_template in commands:
            if isinstance(cmd_template, dict):
                text = substitute(cmd_template.get("msg", ""), global_ctx.raw_ctx)
                self._logger.info(f"[DRY-RUN][{label}] {text}" if self._dry_run else text)
                continue

            cmd = substitute(cmd_template, global_ctx.ctx)
            if self._dry_run:
                self._logger.info(f"[DRY-RUN][{label}] {cmd}")
                continue

            # [ko] commands와 동일한 방식(shell 없이 CommandLineToArgvW로 파싱)으로 실행한다.
            #      echo 등 cmd.exe 내장 명령은 "cmd /c echo ..." 처럼 명시적으로 작성해야 한다.
            # [en] Run the same way as commands (parsed via CommandLineToArgvW, no shell).
            #      cmd.exe builtins like echo must be written explicitly, e.g. "cmd /c echo ...".
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
                    self._logger.info(f"  {line}")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines():
                    self._logger.warning(f"  STDERR: {line}")


def _make_log_fn(manager: "OutputManager | None", index: int, notes_per_file: int,
                  strict: bool, logger: logging.Logger) -> Callable[[str, int], None]:
    """
    [ko]
    FileSession.log()가 실제로 호출하는 콜백을 만든다 (10.3.1/10.3.1.1/10.3.2).
    - 순차 모드(manager=None): slot 제약 없이 logger.info()로 바로 흘려보낸다.
    - 병렬 모드, slot이 범위 내: OutputManager의 ANSI 블록을 갱신한다.
    - 병렬 모드, slot이 범위 밖: --strict면 IndexError로 즉시 중단(Fail-Fast),
      아니면 콘솔에는 안 보이는 파일 전용 WARNING으로 조용히 기록한다.

    [en]
    Builds the callback that FileSession.log() actually calls (10.3.1/10.3.1.1/10.3.2).
    - Sequential mode (manager=None): no slot constraint, passed straight to logger.info().
    - Parallel mode, slot in range: updates OutputManager's ANSI block.
    - Parallel mode, slot out of range: with --strict, aborts immediately with
      IndexError (fail-fast); otherwise, silently logged as a file-only WARNING
      not shown on the console.
    """
    def _log_fn(text: str, slot: int = 0) -> None:
        if manager is None:
            logger.info(f"  {text}")
            return
        if 0 <= slot < notes_per_file:
            manager.on_note(index, slot, text)
            return
        msg = f"log(slot={slot}) out of range (notes_per_file={notes_per_file}) for file [{index}]: {text}"
        if strict:
            raise IndexError(msg)
        logger.warning(msg, extra={"file_only": True})
    return _log_fn


class PluginJobExecutor:
    """
    [ko]
    CommandExecutor와 대등한 위치에서 "플러그인 run() 1회 호출을 실행해
    Result로 정규화"하는 역할을 한다. dry-run 처리, run() 호출, 예외를
    ExecResult/BatchResult로 합성하는 것까지 담당한다 (3.4/8.3.4).

    [en]
    Sits alongside CommandExecutor, responsible for "executing one plugin
    run() call and normalizing it into a Result." Handles dry-run, calling
    run(), and synthesizing exceptions into ExecResult/BatchResult (3.4/8.3.4).
    """

    def __init__(self, logger: logging.Logger, dry_run: bool):
        self._logger  = logger
        self._dry_run = dry_run

    def run_file(self, plugin_name: str, run_fn: Callable, session: "FileSession") -> ExecResult:
        if self._dry_run:
            self._logger.info(f"  [DRY-RUN] plugin={plugin_name} input={session.input} output={session.output} params={session.params}")
            return ExecResult(True, "")
        try:
            result = run_fn(session)
        except Exception as exc:
            return ExecResult(False, str(exc))
        if not isinstance(result, ExecResult):
            return ExecResult(False, f"plugin '{plugin_name}' run() returned {type(result).__name__}, expected ExecResult")
        return result

    def run_batch(self, plugin_name: str, run_fn: Callable, session: "BatchSession") -> BatchResult:
        if self._dry_run:
            self._logger.info(f"  [DRY-RUN] plugin={plugin_name} files={len(session.filelist)} params={session.params}")
            return BatchResult(succeeded=[], failed=[])
        try:
            result = run_fn(session)
        except Exception:
            return BatchResult(succeeded=[], failed=list(session.filelist))
        if not isinstance(result, BatchResult):
            return BatchResult(succeeded=[], failed=list(session.filelist))
        return result


class JobRunner:
    """
    [ko]
    resolve된 Job을 파일 목록에 대해 실행하는 오케스트레이터: 순차/병렬 처리,
    pre/post 훅, 에러 정책, 최종 성공/실패 요약. Placeholder 치환은
    ContextBuilder에, 프로세스 실행은 CommandExecutor에 위임한다.

    [en]
    Orchestrates running a resolved Job over a list of files: sequential or
    parallel, pre/post hooks, error policy, and the final success/fail summary.
    Delegates placeholder substitution to ContextBuilder and process execution
    to CommandExecutor.
    """

    def __init__(self, job: ResolvedJob, logger: logging.Logger, dry_run: bool, strict: bool = False,
                 run_fn: Callable | None = None, plugin_info: "PluginInfo | None" = None):
        self._job      = job
        self._logger   = logger
        self._dry_run  = dry_run
        self._strict   = strict
        self._executor = CommandExecutor(logger, dry_run, job.stderr_quiet)
        self._plugin_executor = PluginJobExecutor(logger, dry_run)
        # [ko] main()이 미리 로드해서 넘겨준 값 — 없으면(=JobRunner를 직접 호출하는 예외적
        #      경우) run()에서 폴백으로 자체 로드한다 (0번 구조적 수정).
        # [en] The value main() pre-loaded and passed in — if absent (the exceptional
        #      case of calling JobRunner directly), run() falls back to loading it
        #      itself (structural fix #0).
        self._run_fn      = run_fn
        self._plugin_info = plugin_info

    def run(self, files: list[Path], user_params: dict) -> None:
        user_params = _coerce_params(user_params, self._job.params)
        self._plugin_params = {**self._job.defaults, **user_params}

        task_id     = _gen_tmp_id()
        ctx_builder = ContextBuilder(self._job, user_params, task_id)
        global_ctx  = ctx_builder.build_global_context()
        total       = len(files)

        # [ko] Plugin은 main()이 미리 로드해서 넘겨준 값을 쓴다 (0번 구조적 수정 — 이중 로드
        #      방지 + _require_essentials()가 session_type을 미리 알 수 있게 함). run_fn이
        #      안 넘어온 채로 plugin_name만 있는 경우(=JobRunner 직접 호출)에만 폴백 로드.
        # [en] For plugins, use the value main() pre-loaded and passed in (structural
        #      fix #0 — avoids a double load and lets _require_essentials() know
        #      session_type ahead of time). Only falls back to loading it when
        #      run_fn wasn't passed in but plugin_name is set (JobRunner called directly).
        run_fn: Callable | None = self._run_fn
        plugin_info: PluginInfo | None = self._plugin_info
        notes_per_file = self._job.notes_per_file
        if self._job.plugin_name and run_fn is None:
            try:
                run_fn = load_plugin(self._job.plugin_name)
            except RuntimeError as exc:
                sys.exit(str(exc))
            plugin_info = run_fn.plugin_info
        if plugin_info:
            notes_per_file = plugin_info.notes_per_file
        elif self._job.tool_path and not self._dry_run:
            tool_p = Path(self._job.tool_path)
            if not tool_p.exists():
                self._logger.warning(f"{_t('warn_tool_not_found')}: {self._job.tool_path}")

        # [ko] Pre / [en] Pre
        self._executor.run_pre_post(self._job.pre, global_ctx, "PRE")

        success_count = 0
        failed_count  = 0

        if plugin_info and plugin_info.session_type == "batch":
            # [ko] BatchSession 플러그인 (8.3.4)
            # [en] BatchSession Plugin (8.3.4)
            # [ko] 이번 단계에서는 실행 경로가 만들어지지만 실제로 exercise되지는
            #      않는다 — RemoveBOM은 session_type="file". parallel은 무시(10.1/10.2).
            # [en] At this stage, the execution path is created but not actually
            #      exercised yet — RemoveBOM is session_type="file". parallel is ignored (10.1/10.2).
            session = BatchSession(
                filelist=[str(f) for f in files],
                output=self._job.output if str(self._job.output).strip() else None,
                taskid=task_id,
                params=dict(self._plugin_params),
            )
            object.__setattr__(session, "_log_fn", _make_log_fn(None, 0, 0, self._strict, self._logger))
            batch_result = self._plugin_executor.run_batch(self._job.plugin_name, run_fn, session)
            success_count = len(batch_result.succeeded)
            failed_count  = len(batch_result.failed)
        elif self._job.parallel and total > 1:
            # [ko] 병렬 처리
            # [en] Parallel Processing
            manager = OutputManager(self._logger, notes_per_file)
            errors: list[tuple[int, str]] = []
            if run_fn:
                process_one = lambda cb, f, i, mgr=None: self._process_file_plugin(cb, run_fn, plugin_info, f, i, mgr)
            else:
                process_one = self._process_file
            with ThreadPoolExecutor(max_workers=self._job.max_workers) as pool:
                future_map = {
                    pool.submit(process_one, ctx_builder, f, i + 1, manager): i + 1
                    for i, f in enumerate(files)
                }
                for future in as_completed(future_map):
                    idx = future_map[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = ExecResult(False, f"[{idx}] {_t('err_exception')}: {exc}")
                    if result.success:
                        success_count += 1
                    else:
                        failed_count += 1
                        if result.message:
                            errors.append((idx, result.message))
                        if self._job.on_error == "stop":
                            self._logger.error(_t("err_on_error_stop_cancel"))
                            for f in future_map:
                                f.cancel()
                            break
            for _, err in sorted(errors):
                self._logger.error(err)
        else:
            # [ko] 순차 처리
            # [en] Sequential Processing
            if run_fn:
                process_one = lambda cb, f, i, mgr=None: self._process_file_plugin(cb, run_fn, plugin_info, f, i, mgr)
            else:
                process_one = self._process_file
            for i, file_path in enumerate(files):
                try:
                    result = process_one(ctx_builder, file_path, i + 1)
                except Exception as exc:
                    result = ExecResult(False, "")
                    self._logger.error(f"[{i + 1}] {_t('err_exception')}: {exc}")
                if result.success:
                    success_count += 1
                else:
                    failed_count += 1
                    if self._job.on_error == "stop":
                        self._logger.error(_t("err_on_error_stop_abort"))
                        break

        # [ko] Post / [en] Post
        self._executor.run_pre_post(self._job.post, global_ctx, "POST")

        self._logger.info(_t("info_job_summary", success=success_count, failed=failed_count, total=total))

    def _process_file(
        self,
        ctx_builder: ContextBuilder,
        file_path: Path,
        index: int,
        manager: "OutputManager | None" = None,
    ) -> ExecResult:
        file_ctx = ctx_builder.build_file_context(file_path, index)
        ctx, raw_ctx, cwd = file_ctx.ctx, file_ctx.raw_ctx, file_ctx.cwd
        output_p = Path(file_ctx.output_path)
        quiet    = manager is not None

        if manager:
            manager.on_start(index, file_path.name)
        else:
            max_len = _max_name_display_len()
            self._logger.info(f"[{index:>4}] {_truncate_filename(file_path.name, max_len)} → {_truncate_filename(output_p.name, max_len)}")

        # [ko] ACP 범위 밖 문자(예: 일본어)가 경로/파일명에 포함된 경우,
        #      ASCII 임시 경로로 복사해 ANSI 도구를 우회한다.
        # [en] When the path/filename contains a character outside the ACP range (e.g.
        #      Japanese), copy it to a temporary ASCII path to work around ANSI-only tools.
        need_temp = not self._dry_run and (_has_non_acp(str(file_path)) or _has_non_acp(cwd))
        tmp_dir: Path | None = None
        result = ExecResult(False, "")

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
            note_slot = 0
            for cmd_template in self._job.commands:
                if isinstance(cmd_template, dict):
                    text = substitute(cmd_template.get("msg", ""), raw_ctx)
                    if self._dry_run:
                        self._logger.info(f"  [DRY-RUN][MSG] {text}")
                    elif manager:
                        manager.on_note(index, note_slot, text)
                    else:
                        self._logger.info(f"  {text}")
                    note_slot += 1
                    continue

                cmd = substitute(cmd_template, ctx)
                exec_result = self._executor.run(cmd, cwd=cwd, quiet=quiet)
                last_stderr = exec_result.message
                if not exec_result.success:
                    msg = f"FAILED [{index}] {file_path.name} | CMD: {cmd} | ERR: {exec_result.message.strip()}"
                    if not quiet:
                        self._logger.error(msg)
                    result = ExecResult(False, msg)
                    return result

            if need_temp:
                if not tmp_out.exists():
                    msg = f"FAILED [{index}] {file_path.name} | {_t('err_output_not_created')} | STDERR: {last_stderr.strip()}"
                    if not quiet:
                        self._logger.error(msg)
                    result = ExecResult(False, msg)
                    return result
                output_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_out), str(output_p))
            elif self._job.uses_output and not self._dry_run and not output_p.exists():
                # [ko] commands가 {output}을 참조하는데도 exit 0 이후 실제 파일이 없으면 조용한 성공을 막는다.
                # [en] Prevent a silent success when commands references {output} but the
                #      file doesn't actually exist after exit 0.
                msg = f"FAILED [{index}] {file_path.name} | {_t('err_output_not_created')} | STDERR: {last_stderr.strip()}"
                if not quiet:
                    self._logger.error(msg)
                result = ExecResult(False, msg)
                return result

            result = ExecResult(True, "")
            return result

        finally:
            if manager:
                manager.on_finish(index, file_path.name, output_p.name, result.success)
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(str(tmp_dir), ignore_errors=True)

    def _process_file_plugin(
        self,
        ctx_builder: ContextBuilder,
        run_fn: Callable,
        plugin_info: PluginInfo,
        file_path: Path,
        index: int,
        manager: "OutputManager | None" = None,
    ) -> ExecResult:
        """
        [ko]
        CLI Job의 _process_file()과 대응되는, FileSession 플러그인 Job용
        파일 1개 처리 함수 (3.4/4.2). _process_file()의 ACP-비인코딩 경로용
        임시복사 로직은 재사용하지 않는다 — 그건 subprocess argv 인코딩 문제
        대응이라 in-process 플러그인 호출에는 해당 없다.

        [en]
        The single-file processing function for FileSession plugin Jobs,
        corresponding to CLI Jobs' _process_file() (3.4/4.2). Does not reuse
        _process_file()'s temp-copy logic for ACP-unencodable paths — that
        addresses subprocess argv encoding issues, which don't apply to an
        in-process plugin call.
        """
        file_ctx = ctx_builder.build_file_context(file_path, index)
        raw_ctx  = file_ctx.raw_ctx
        output_p = Path(file_ctx.output_path)

        if manager:
            manager.on_start(index, file_path.name)
        else:
            max_len = _max_name_display_len()
            self._logger.info(f"[{index:>4}] {_truncate_filename(file_path.name, max_len)} → {_truncate_filename(output_p.name, max_len)}")

        session = FileSession(
            input=raw_ctx["input"], output=raw_ctx["output"],
            itemid=index, taskid=raw_ctx["taskid"],
            params=dict(self._plugin_params),  # [ko] 파일마다 새 복사본 — 병렬 워커들이 하나의 dict를 공유하지 않도록 / [en] a fresh copy per file — so parallel workers never share one dict
        )
        object.__setattr__(
            session, "_log_fn",
            _make_log_fn(manager, index, plugin_info.notes_per_file, self._strict, self._logger),
        )

        result = self._plugin_executor.run_file(self._job.plugin_name, run_fn, session)

        """
        [ko]
        Plugin과 CLI 명령 사이의 "성공인데 output 미생성" 안전장치 격차를 없앤다 —
        CLI Job은 uses_output 검사(_process_file)로 이미 이 문제를 잡아내지만,
        플러그인은 자신이 반환한 success만 신뢰했었다(예: BOM이 없어 output을
        아예 쓰지 않고도 success=True를 반환하는 remove_bom). dry-run은 애초에
        파일을 만들지 않으므로 제외한다.

        [en]
        Closes the safety-net gap between plugins and CLI commands for
        "success but output not created" — CLI Jobs already catch this via
        the uses_output check (_process_file), but plugins used to be trusted
        purely on their own returned success (e.g. remove_bom, which returns
        success=True without ever writing output when no BOM is found).
        Excluded during dry-run, since no file is created in the first place.
        """
        if result.success and not self._dry_run and not output_p.exists():
            result = ExecResult(False, _t("err_output_not_created"))

        """
        [ko]
        실패 메시지에 [index] 파일명 컨텍스트를 항상 미리 박아 넣는다 — CLI Job의
        _process_file()은 이미 그렇게 하지만, 플러그인이 반환하는 ExecResult.message는
        파일 컨텍스트가 없다. manager가 있으면(병렬 모드) 이 메시지가 즉시 출력되지
        않고 JobRunner.run()의 errors 리스트에 그대로 보관됐다가 나중에 출력되므로,
        그 시점에 가서 컨텍스트를 붙이면 이미 늦는다 — 지금 붙여둬야 한다.

        [en]
        Always bake the [index] filename context into the failure message up
        front — CLI Jobs' _process_file() already does this, but a plugin's
        returned ExecResult.message has no file context. When a manager is
        present (parallel mode), this message isn't printed immediately; it's
        held as-is in JobRunner.run()'s errors list and printed later, so
        attaching context at that point would already be too late — it must
        be attached here.
        """
        if not result.success:
            result = ExecResult(False, f"FAILED [{index}] {file_path.name} | {result.message}")

        if manager:
            manager.on_finish(index, file_path.name, output_p.name, result.success,
                               result.message if result.success else "")
        elif not result.success:
            self._logger.error(result.message)
        elif result.message:
            # [ko] 순차 모드는 ANSI 덮어쓰기가 없어 제목줄에 붙일 수 없으므로 별도 줄로 출력
            # [en] sequential mode has no ANSI overwrite, so it can't be appended to the
            #      title line — print it as a separate line instead
            self._logger.info(f"  {result.message}")
        return result


# ═══════════════════════════════════════════════════════════════════════════
# [ko] PART 9. 오류 처리 & 진입점
# [en] PART 9. ERROR HANDLING & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

"""
[ko]
Nuitka --onefile 빌드는 더 이상 하지 않으므로(12.4), sys.argv[0] 기반 경로 해석
(과거 Nuitka의 임시 추출 폴더 문제를 피하기 위한 워크어라운드)은 더 이상 필요 없다.
오히려 sys.argv[0]은 tcbp.py가 "다른 프로그램에 의해 라이브러리로 import"될 때
(예: pytest가 테스트에서 `import tcbp`, validate_config.py, 플러그인의
`from tcbp import ...`) 그 다른 프로그램의 실행 파일 경로를 가리켜버려서 깨진다.
Path(__file__)은 누가 import했든 항상 tcbp.py 자신의 위치를 정확히 가리키므로
이쪽이 맞다.

[en]
Nuitka --onefile builds are no longer produced (12.4), so the sys.argv[0]-based
workaround (for Nuitka's temp-extraction-folder issue) is no longer needed —
and it actively breaks when tcbp.py is imported as a library by something else
(pytest, validate_config.py, a plugin's `from tcbp import ...`), since sys.argv[0]
then points at that other program's path. Path(__file__) always points at
tcbp.py's own location regardless of who imported it.
"""
_SCRIPT_DIR = Path(__file__).resolve().parent

# [ko] 오류 출력 / 긴급 로그 (setup_logging 이전 크래시용)
# [en] Error Output / Emergency Log (for crashes before setup_logging)

def _emergency_log(msg: str) -> None:
    """
    [ko] logger가 초기화되기 전 오류를 스크립트 폴더의 tcbp_error.log에 기록한다.
    [en] Record an error that occurred before the logger was initialized into tcbp_error.log in the script's folder.
    """
    try:
        import datetime
        path = _SCRIPT_DIR / "tcbp_error.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n{msg}\n")
    except Exception:
        pass


def _pause_on_error(msg: str) -> None:
    """
    [ko] 오류 내용을 콘솔에 출력하고 Enter를 기다려 창이 닫히지 않게 한다.
    [en] Print the error to the console and wait for Enter so the window doesn't close immediately.
    """
    print(f"\n{msg}", flush=True)
    input(_t("prompt_error_pause"))


# [ko] 진입점
# [en] Entry Point

def main() -> None:
    _logger: logging.Logger | None = None
    _job:    ResolvedJob | None    = None
    _set_lang(_prescan_lang(sys.argv[1:]))  # [ko] --help 자체도 올바른 언어로 보이도록 / [en] so --help itself shows in the right language
    try:
        args        = parse_args()
        _set_lang(args.lang)
        user_params = parse_params(args.params)
        loader      = ConfigLoader(args.config)
        config      = loader.load()
        if args.lang is None:
            _set_lang(config.get("global", {}).get("lang"))

        _job        = loader.resolve_job(args.job)

        # [ko] 플러그인은 여기서 1회만 로드한다 (0번 구조적 수정) — _require_essentials()가
        #      session_type을 미리 알아야 BatchSession의 output 생략(8.3.2)을 판단할 수 있고,
        #      JobRunner.run() 안에서 다시 로드하는 이중 로드도 피한다.
        # [en] The plugin is loaded exactly once here (structural fix #0) —
        #      _require_essentials() needs to know session_type ahead of time to
        #      decide on BatchSession's output omission (8.3.2), and this also
        #      avoids a double load inside JobRunner.run().
        run_fn: Callable | None = None
        plugin_info: PluginInfo | None = None
        if _job.plugin_name:
            try:
                run_fn = load_plugin(_job.plugin_name)
            except RuntimeError as exc:
                sys.exit(str(exc))
            plugin_info = run_fn.plugin_info

        _require_essentials(_job, plugin_info, job_name=args.job)
        _logger     = setup_logging(_job.log, _job.log_file, args.job)

        # [ko] 로그 파일에 이 줄이 있으면 setup_logging까지는 성공한 것
        # [en] If this line is in the log file, setup_logging succeeded
        if _job.desc:
            _logger.info(f"Job: {args.job} — {_job.desc}")
        if args.dry_run:
            _logger.info(_t("info_dry_run_mode"))

        user_params = prompt_missing_params(_job, user_params)
        files       = resolve_input_files(args.filelist, _job, args.job)

        mode = f"parallel (max_workers={_job.max_workers})" if _job.parallel else "sequential"
        _logger.info(_t("info_file_count", count=len(files), mode=mode))

        runner = JobRunner(_job, _logger, args.dry_run, args.strict, run_fn=run_fn, plugin_info=plugin_info)
        runner.run(files, user_params)

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

    if _job and _job.pause:
        try:
            import keyboard
            print(_t("prompt_press_any_key"), flush=True)
            keyboard.read_event(suppress=True)
        except ImportError:
            input(_t("prompt_press_any_key"))


if __name__ == "__main__":
    main()
