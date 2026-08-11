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
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

from core.contract import PluginInfo, TcbpError
from core.models import JobParam, PresetOption, ResolvedJob
from messages import _t

_SCRIPT_DIR = Path(__file__).resolve().parent.parent


# [ko] TOML 문법 오류 메시지 개선
# [en] TOML Syntax Error Message Improvement
# [ko] tomllib은 라인/컬럼 속성을 따로 노출하지 않고 "(at line N, column M)" 형태로
#      메시지에 포함시키므로, 이를 파싱해 원문 코드 프레임과 함께 보여준다.
# [en] tomllib does not expose line/column as separate attributes; it embeds them in
#      the message as "(at line N, column M)", so we parse that and show it together
#      with the original source code frame.

_TOML_ERR_RE     = re.compile(r"^(.*?)\s*\(at line (\d+), column (\d+)\)\s*$")
_TOML_ERR_EOF_RE = re.compile(r"^(.*?)\s*\(at end of document\)\s*$")

# [ko] (정규식, 메시지 키) — 실제 번역 텍스트는 messages/ko.py·en.py의 같은 키에
#      있다. 이름 있는 캡처 그룹(예: (?P<name>...))을 쓰면 m.groupdict()를 그대로
#      _t(key, **kwargs)에 넘길 수 있어, 다른 모든 메시지와 동일하게 완전성
#      검증(messages/__init__.py, test_i18n.py) 대상이 된다.
# [en] (regex, message key) — the actual translated text lives under the same
#      key in messages/ko.py·en.py. Named capture groups (e.g. (?P<name>...))
#      let m.groupdict() feed straight into _t(key, **kwargs), so these get the
#      same completeness check (messages/__init__.py, test_i18n.py) as every
#      other message.
_TOML_REASON_PATTERNS: list[tuple[str, str]] = [
    (r"^Cannot overwrite a value$", "toml_reason_overwrite_value"),
    (r"^Cannot declare (?P<name>.+) twice$", "toml_reason_declare_twice"),
    (r"^Cannot mutate immutable namespace (?P<name>.+)$", "toml_reason_immutable_namespace"),
    (r"^Cannot redefine namespace (?P<name>.+)$", "toml_reason_redefine_namespace"),
    (r"^Expected '=' after a key in a key/value pair$", "toml_reason_expected_equals"),
    (r"^Expected '\]' at the end of a table declaration$", "toml_reason_expected_close_table"),
    (r"^Expected '\]\]' at the end of an array declaration$", "toml_reason_expected_close_array_table"),
    (r"^Expected '(?P<token>.+)'$", "toml_reason_expected_token"),
    (r"^Invalid initial character for a key part$", "toml_reason_invalid_key_start"),
    (r"^Invalid statement$", "toml_reason_invalid_statement"),
    (r"^Invalid value$", "toml_reason_invalid_value"),
    (r"^Invalid date or datetime$", "toml_reason_invalid_datetime"),
    (r"^Invalid hex value$", "toml_reason_invalid_hex"),
    (r"^Unclosed array$", "toml_reason_unclosed_array"),
    (r"^Unclosed inline table$", "toml_reason_unclosed_inline_table"),
    (r"^Unterminated string$", "toml_reason_unterminated_string"),
    (r"^Unescaped '\\' in a string$", "toml_reason_unescaped_backslash"),
    (r"^Escaped character is not a Unicode scalar value$", "toml_reason_invalid_unicode_escape"),
    (r"^Duplicate inline table key '(?P<table_key>.+)'$", "toml_reason_duplicate_inline_key"),
    (r"^Found invalid character '(?P<char>.+)'$", "toml_reason_invalid_character"),
    (r"^Illegal character '(?P<char>.+)'$", "toml_reason_illegal_character"),
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
    for pattern, key in _TOML_REASON_PATTERNS:
        m = re.match(pattern, reason)
        if m:
            return _t(key, **m.groupdict())
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
                raise TcbpError(f"{_t('err_config_not_found')}: {self._path}")
            with open(self._path, "rb") as f:
                try:
                    self._config = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    raise TcbpError(_format_toml_error(self._path, e))
        return self._config

    def resolve_job(self, job_name: str) -> ResolvedJob:
        config = self.load()
        g      = config.get("global", {})
        jobs   = config.get("jobs", {})

        if job_name not in jobs:
            available = ", ".join(jobs.keys()) if jobs else _t("none_placeholder")
            raise TcbpError(f"{_t('err_job_not_found', job=job_name)}\n{_t('label_available_jobs')}: {available}")

        job = jobs[job_name]

        # [ko] tool과 plugin은 상호 배타적이다 (2.1). 병합된 필드가 아니라 원본(raw)
        #      job dict로 검사해야 global.default_tool 상속으로 인한 오탐을 피한다.
        # [en] tool and plugin are mutually exclusive (2.1). Checking the raw job
        #      dict (not the merged field) avoids a false positive from
        #      global.default_tool inheritance.
        if "tool" in job and "plugin" in job:
            raise TcbpError(_t("err_tool_and_plugin_both", job=job_name))

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
            params       = [JobParam(
                                key=p.get("key", ""), desc=p.get("desc", ""), type=p.get("type", ""),
                                default=p.get("default", None),
                                preset=[PresetOption(label=o.get("label", ""), value=o.get("value"))
                                        for o in p.get("preset", [])],
                            ) for p in job.get("params", [])],
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


# [ko] params[].preset 검증 (tcbp.py 런타임 fail-fast와 validate_config.py 사전
#      진단이 이 함수를 그대로 공유한다 — load_plugin()/_JOB_STANDARD_KEYS와 동일한
#      "계약을 한 곳에만 정의" 패턴).
# [en] Validates params[].preset. Shared as-is between tcbp.py's runtime
#      fail-fast and validate_config.py's authoring-time diagnostics — the
#      same "define the contract once" pattern as load_plugin()/_JOB_STANDARD_KEYS.

def _value_matches_type(value: Any, ptype: str) -> bool:
    if ptype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if ptype == "bool":
        return isinstance(value, bool)
    return isinstance(value, str)


def _validate_param_presets(declared: list["JobParam"], job_name: str = "") -> list[str]:
    errors = []
    for p in declared:
        if not p.preset:
            continue
        for opt in p.preset:
            if not _value_matches_type(opt.value, p.type):
                errors.append(_t("err_preset_value_type_mismatch", job=job_name, param=p.key,
                                  label=opt.label, value=opt.value, type=p.type or "string"))
        if p.default is not None and not any(
            _value_matches_type(opt.value, p.type) and opt.value == p.default for opt in p.preset
        ):
            errors.append(_t("err_preset_default_not_in_preset", job=job_name, param=p.key, default=p.default))
    return errors


def _default_preset_index(meta: "JobParam") -> int:
    """[ko] default 미지정 시 첫 번째 preset 항목을 초기 선택으로 사용한다. / [en] With no default declared, the first preset entry is the initial selection."""
    if meta.default is not None:
        for i, opt in enumerate(meta.preset):
            if _value_matches_type(opt.value, meta.type) and opt.value == meta.default:
                return i
    return 0


def _require_essentials(job: ResolvedJob, plugin_info: "PluginInfo | None" = None, job_name: str = "") -> None:
    """
    [ko]
    Job을 resolve한 직후 1회 실행하는 최소 fail-fast 가드.
    config 저작 실수가 명확한 오류 대신 알아보기 힘든 실행 오류로 번지는 걸 막는다.
    예를 들어 빈 {tool} placeholder는 아무 일도 안 일어나는 게 아니라,
    치환된 명령이 "convert ..."로 시작하게 되는데 Windows에는 실제로 자체
    convert.exe(FAT->NTFS 변환용)가 있어서 엉뚱하게 그게 실행될 수 있다.
    더 깊은 저작 진단(undefined placeholder, 오탈자 키, 존재하지 않는 tool 경로,
    dry-run 샘플 검사 등)은 전부 validate_config.py에 있다 —
    여기서는 tcbp.py가 말이 안 되는 걸 실행하지 않도록 막는 최소한만 한다.

    [en]
    Minimal fail-fast guard, run once right after resolving a Job,
    so a config authoring mistake doesn't turn into a confusing runtime failure
    instead of a clear one.
    For example: an empty {tool} placeholder isn't a no-op — the substituted command
    starts with "convert ...", and Windows actually ships its own convert.exe
    (FAT->NTFS conversion), so the tool would attempt to run *that* instead of failing cleanly.
    Deeper authoring diagnostics (undefined placeholders, typo'd keys, unreachable tool paths,
    dry-run sample checks, ...) live entirely in validate_config.py
    — this is only the minimum needed for tcbp.py to refuse to run something nonsensical.
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
        raise TcbpError(f"{_t('vc_missing_required_key')}: {', '.join(missing)}")

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
        raise TcbpError(_t("err_plugin_not_thread_safe_parallel", job=job_name, name=job.plugin_name))

    preset_errors = _validate_param_presets(job.params, job_name)
    if preset_errors:
        raise TcbpError("\n".join(preset_errors))
