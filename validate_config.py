#!/usr/bin/env python3
"""
[ko]
validate_config.py - TCBP(Total Commander Batch Python)용 config.toml 검증 도구
tcbp.py를 실행하기 전에 config.toml의 작성 실수를 미리 진단하는 독립 도구.

tcbp.py 자신은 최소한의 fail-fast 가드(_require_essentials)만 갖고 있고,
이 파일이 authoring-time 진단(오탈자, undefined placeholder, tool 경로,
sample dry-run, output/input 덮어쓰기 위험 등)을 전담한다. tcbp.py가 실행 중에
자동으로 호출하지 않으므로, config를 고친 뒤 수동으로(또는 CI에서) 돌려야 한다.

Usage:
    python validate_config.py <config.toml> [--job JOB] [--sample <filelist>] [--lang ko|en]

[en]
validate_config.py - config.toml validator for TCBP (Total Commander Batch Python)
A standalone tool that diagnoses config.toml authoring mistakes before running tcbp.py.

tcbp.py itself only carries a minimal fail-fast guard (_require_essentials); this file
owns all authoring-time diagnostics (typos, undefined placeholders, tool paths, sample
dry-run checks, output/input overwrite risk, etc.). tcbp.py never calls it automatically
at runtime, so run it manually (or from CI) after editing config.toml.

Usage:
    python validate_config.py <config.toml> [--job JOB] [--sample <filelist>] [--lang ko|en]
"""

import argparse
import difflib
import string
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tcbp import (
    ConfigLoader,
    ResolvedJob,
    ContextBuilder,
    substitute,
    load_file_list,
    _JOB_STANDARD_KEYS,
    load_plugin,
    PluginInfo,
    _validate_param_presets,
)
from tcbp import _set_lang as _set_tcbp_lang

# [ko] tcbp.py의 _SCRIPT_DIR 주석 참고 — Nuitka --onefile 빌드에서는 Path(__file__)을 믿을 수 없고, sys.argv[0]은 믿을 수 있다.
# [en] See tcbp.py's _SCRIPT_DIR comment — Path(__file__) is unreliable under a Nuitka --onefile build, sys.argv[0] is not.
_SCRIPT_DIR = Path(sys.argv[0]).resolve().parent


# ═══════════════════════════════════════════════════════════════════════════
"""
[ko]
I18N — 자체 메시지 카탈로그 (이 도구 자신이 출력하는 문구만). import한 tcbp 함수가
내는 메시지(TOML 문법 오류, "job 없음")는 tcbp 자신의 카탈로그를 쓰므로,
아래 _set_tcbp_lang()으로 언어를 동기화한다.

[en]
I18N — own message catalog (this tool's own output only; messages coming
from imported tcbp functions — TOML syntax errors, "job not found" — use
tcbp's own catalog, kept in sync via _set_tcbp_lang() below).
"""
# ═══════════════════════════════════════════════════════════════════════════

_LANG = "ko"

_MESSAGES: dict[str, dict[str, str]] = {
    "ko": {
        "cli_description":   "config.toml 검증 도구 (tcbp.py 실행 전 사전 점검용)",
        "cli_epilog_header": "예시:",
        "help_config":       "검증할 config.toml 경로",
        "help_job":          "검증할 Job 이름 (생략 시 전체 Job 검증)",
        "help_sample":       "dry-run 검증에 사용할 샘플 파일 목록 텍스트 파일",
        "help_lang":         "출력 언어 (ko/en)",
        "err_no_jobs":       "[ERROR] config에 정의된 Job이 없습니다.",
        "vc_missing_required_key": "필수 Key 누락",
        "vc_missing_tool_hint":    "또는 global.tools 에 등록된 tool 이름이 필요합니다",
        "vc_undefined_placeholder": "정의되지 않은 Placeholder",
        "vc_suggestion_maybe":     "혹시",
        "vc_unknown_key":          "알 수 없는 Key",
        "vc_did_you_mean":         "혹시 다음을 의미하셨습니까?",
        "vc_unused_key":           "사용되지 않는 Key",
        "vc_no_tools_registered":  "global.tools 에 등록된 tool이 없습니다",
        "vc_tool_path_empty":      "Tool 경로가 비어 있습니다",
        "vc_tool_path_missing":    "Tool 경로를 찾을 수 없습니다",
        "vc_unknown_param_type":   "알 수 없는 param type (\"int\"/\"bool\" 또는 생략만 허용)",
        "vc_type_mismatch":        "타입 불일치: {label} ({expected} 기대, {got} 발견)",
        "vc_bad_enum_value":       "허용되지 않는 값",
        "vc_output_overwrites_input": "output이 input과 같은 파일을 가리킬 수 있습니다 (덮어쓰기 위험)",
        "vc_output_overwrites_input_ext": "output이 input과 같은 파일을 가리킬 수 있습니다 (입력 확장자가 \"{ext}\"인 경우 덮어쓰기 위험 — output이 그 확장자를 고정으로 강제함)",
        "vc_sample_error":         "Sample dry-run 오류",
        "vc_tool_and_plugin_both": "tool과 plugin을 동시에 지정할 수 없습니다",
        "vc_batch_parallel_ignored": "BatchSession 플러그인은 parallel 처리를 지원하지 않습니다 (parallel=true는 무시됨)",
        "vc_recursive_include_ignored": "recursive/include는 input_mode=\"directory\"인 Job에서만 적용됩니다 (무시됨)",
        "vc_plugin_not_thread_safe_parallel": "플러그인 '{name}'은(는) thread_safe=False로 선언되어 있어 parallel=true(+max_workers>1)와 함께 쓸 수 없습니다",
        "vc_summary_line":  "Job {jobs}개 검증 — 총 오류 {errors}개  총 경고 {warnings}개  총 정보 {infos}개",
    },
    "en": {
        "cli_description":   "config.toml validator (pre-flight check before running tcbp.py)",
        "cli_epilog_header": "Examples:",
        "help_config":       "Path to the config.toml to validate",
        "help_job":          "Job to validate (validates all Jobs if omitted)",
        "help_sample":       "Sample file-list text file to use for dry-run checks",
        "help_lang":         "Output language (ko/en)",
        "err_no_jobs":       "[ERROR] No Jobs defined in this config.",
        "vc_missing_required_key": "Missing required key",
        "vc_missing_tool_hint":    "or a tool name registered in global.tools is required",
        "vc_undefined_placeholder": "Undefined placeholder",
        "vc_suggestion_maybe":     "Did you mean",
        "vc_unknown_key":          "Unknown key",
        "vc_did_you_mean":         "Did you mean:",
        "vc_unused_key":           "Unused key",
        "vc_no_tools_registered":  "No tools registered in global.tools",
        "vc_tool_path_empty":      "Tool path is empty",
        "vc_tool_path_missing":    "Tool path not found",
        "vc_unknown_param_type":   "Unknown param type (only \"int\"/\"bool\" or omitted is recognized)",
        "vc_type_mismatch":        "Type mismatch: {label} (expected {expected}, got {got})",
        "vc_bad_enum_value":       "Disallowed value",
        "vc_output_overwrites_input": "output may resolve to the same file as input (overwrite risk)",
        "vc_output_overwrites_input_ext": "output may resolve to the same file as input (overwrite risk when the input extension is \"{ext}\" — output forces that fixed extension)",
        "vc_sample_error":         "Sample dry-run error",
        "vc_tool_and_plugin_both": "tool and plugin cannot both be set",
        "vc_batch_parallel_ignored": "BatchSession plugins do not support parallel processing (parallel=true is ignored)",
        "vc_recursive_include_ignored": "recursive/include only apply to Jobs with input_mode=\"directory\" (ignored)",
        "vc_plugin_not_thread_safe_parallel": "Plugin '{name}' is declared thread_safe=False and cannot be used with parallel=true (+max_workers>1)",
        "vc_summary_line":  "Validated {jobs} job(s) — {errors} error(s), {warnings} warning(s), {infos} info",
    },
}


def _t(key: str, **kwargs) -> str:
    template = _MESSAGES.get(_LANG, _MESSAGES["ko"]).get(key) or _MESSAGES["ko"].get(key, key)
    return template.format(**kwargs) if kwargs else template


def _set_lang(lang: str | None) -> None:
    global _LANG
    if lang in _MESSAGES:
        _LANG = lang
    _set_tcbp_lang(lang)  # [ko] tcbp 자신의 카탈로그(TOML 오류, job 없음)도 함께 동기화 / [en] keep tcbp's own catalog (TOML errors, job-not-found) in sync


def _prescan_lang(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════════════════
"""
[ko]
CONTRACT CONSTANTS — 계약 상수. tcbp.py와 수동으로 동기화 유지. tcbp.py의
ConfigLoader.resolve_job() / ContextBuilder가 실제로 읽는 key 집합을 나타낸다.
그쪽이 바뀌면 여기도 갱신할 것.

[en]
CONTRACT CONSTANTS — kept manually in sync with tcbp.py. These describe sets
of keys tcbp.py's ConfigLoader.resolve_job() / ContextBuilder actually read;
if those change, update here too.
"""
# ═══════════════════════════════════════════════════════════════════════════

_GLOBAL_STANDARD_KEYS = {
    "on_error", "parallel", "max_workers", "output", "log", "log_file",
    "pause", "stderr_quiet", "tools", "default_tool", "lang",
    "input_mode", "recursive", "include",
}
_FILE_CTX_BUILTIN_KEYS   = {"input", "dir", "name", "base", "ext", "index", "tool", "taskid", "itemid"}
_GLOBAL_CTX_BUILTIN_KEYS = {"tool", "max_workers", "taskid"}

_KNOWN_PARAM_TYPES = {"", "int", "bool"}
_BOOL_KEYS = {"parallel", "log", "pause", "stderr_quiet", "allow_output_overwrite", "recursive"}
_INT_KEYS  = {"max_workers"}
_ON_ERROR_VALUES   = {"continue", "stop"}
_INPUT_MODE_VALUES = {"list", "directory"}


@dataclass
class ValidationReport:
    job_name: str  # [ko] 전역(global) 섹션 리포트는 "" / [en] "" for the global-section report
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos:    list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.errors or self.warnings or self.infos)

    def format(self) -> str:
        label = self.job_name or "global"
        lines = [f"--- {label} ---"]
        for tag, items in (("ERROR", self.errors), ("WARNING", self.warnings), ("INFO", self.infos)):
            for item in items:
                sub_lines = item.split("\n")
                lines.append(f"[{tag}] {sub_lines[0]}")
                lines.extend(f"        {s}" for s in sub_lines[1:])
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# [ko] CHECKS — 검사 로직
# [en] CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_placeholders(template: str) -> set[str]:
    names: set[str] = set()
    try:
        for _, field_name, _, _ in string.Formatter().parse(template):
            if not field_name:
                continue
            base = field_name.split(".")[0].split("[")[0]
            if base:
                names.add(base)
    except ValueError:
        pass
    return names


def _job_command_text(entry) -> str:
    return entry.get("msg", "") if isinstance(entry, dict) else entry


def _check_required(resolved: ResolvedJob, plugin_info: PluginInfo | None = None) -> list[str]:
    errors = []
    if not resolved.plugin_name:
        if not resolved.tool_path:
            errors.append(f"{_t('vc_missing_required_key')}: tool ({_t('vc_missing_tool_hint')})")
        if not resolved.commands:
            errors.append(f"{_t('vc_missing_required_key')}: commands")
    # [ko] BatchSession 플러그인은 output 생략 가능 (8.3.2)
    # [en] BatchSession plugins may omit output (8.3.2)
    output_required = not (plugin_info and plugin_info.session_type == "batch")
    if output_required and not str(resolved.output).strip():
        errors.append(f"{_t('vc_missing_required_key')}: output")
    return errors


def _check_input_mode_usage(resolved: ResolvedJob) -> list[str]:
    """
    [ko]
    recursive/include는 input_mode="directory"인 Job에서만 의미가 있다.
    병합된 ResolvedJob을 검사해, job 자체가 아니라 [global]에서 물려받은
    recursive/include라도 놓치지 않는다 (12장).

    [en]
    recursive/include only make sense for a Job with input_mode="directory".
    Checks the merged ResolvedJob so that recursive/include inherited from
    [global] (rather than set on the job itself) aren't missed (Chapter 12).
    """
    if resolved.input_mode != "directory" and (resolved.recursive or resolved.include):
        return [_t("vc_recursive_include_ignored")]
    return []


def _check_plugin(raw_job: dict, resolved: ResolvedJob) -> tuple[list[str], list[str], PluginInfo | None]:
    """
    [ko]
    tool+plugin 동시 지정, plugin Job의 불필요한 commands, BatchSession+parallel,
    그리고 plugin 존재/메타데이터 유효성을 검사한다 — load_plugin()으로 import만
    하고 run(session)은 절대 호출하지 않는다 (5.5, 기존 validate_config.py의
    "실행 없이 진단" 철학 그대로). 로드에 성공하면 plugin_info를 반환해 호출부가
    (_check_required/_check_output_overwrite_risk에) 재사용할 수 있게 한다 —
    plugin을 두 번 로드하지 않기 위함.

    [en]
    Checks tool+plugin both being set, unused commands in a plugin Job,
    BatchSession+parallel, and plugin existence/metadata validity — only
    imports via load_plugin() and never calls run(session) (5.5, in keeping
    with validate_config.py's "diagnose without executing" philosophy). On a
    successful load, returns plugin_info so the caller can reuse it in
    _check_required/_check_output_overwrite_risk — avoiding loading the
    plugin twice.
    """
    errors, warnings = [], []
    if "tool" in raw_job and "plugin" in raw_job:
        errors.append(f"{_t('vc_tool_and_plugin_both')}: tool={raw_job['tool']!r}, plugin={raw_job['plugin']!r}")
    if not resolved.plugin_name:
        return errors, warnings, None
    if resolved.commands:
        warnings.append(f"{_t('vc_unused_key')}: commands")
    try:
        run_fn = load_plugin(resolved.plugin_name)
    except RuntimeError as exc:
        errors.append(str(exc))
        return errors, warnings, None
    plugin_info = run_fn.plugin_info
    if plugin_info.session_type == "batch" and resolved.parallel:
        warnings.append(_t("vc_batch_parallel_ignored"))
    # [ko] thread_safe=False로 선언된 FileSession 플러그인 + parallel=true(+max_workers>1)는
    #      tcbp.py 런타임(_require_essentials, 5.10)과 동일한 기준으로 여기서도 오류 처리한다 —
    #      실행 전에 미리 잡아내는 것이 이 도구의 목적이므로 경고가 아니라 오류로 취급한다.
    # [en] A FileSession plugin declared thread_safe=False + parallel=true (+max_workers>1)
    #      is flagged as an error here too, by the same rule as the tcbp.py runtime
    #      (_require_essentials, Section 5.10) — since this tool exists to catch it
    #      before the run, it's an error, not a warning.
    if (plugin_info.session_type == "file" and not plugin_info.thread_safe
            and resolved.parallel and resolved.max_workers > 1):
        errors.append(_t("vc_plugin_not_thread_safe_parallel", name=resolved.plugin_name))
    return errors, warnings, plugin_info


def _check_placeholders(resolved: ResolvedJob) -> tuple[list[str], set[str]]:
    # [ko] {key}_label은 preset이 선언된 파라미터마다 JobRunner.run()이 런타임에
    #      생성하는 파생 placeholder (_derive_preset_labels) — 정적 진단에서도 알려진 것으로 취급한다.
    # [en] {key}_label is a derived placeholder JobRunner.run() generates at
    #      runtime for every preset-declared param (_derive_preset_labels) —
    #      treat it as known here too, for static diagnostics.
    dynamic_keys = (set(resolved.defaults) | {p.key for p in resolved.params if p.key}
                     | {f"{p.key}_label" for p in resolved.params if p.key and p.preset})
    file_known   = _FILE_CTX_BUILTIN_KEYS | {"output"} | dynamic_keys
    output_known = _FILE_CTX_BUILTIN_KEYS | dynamic_keys
    global_known = _GLOBAL_CTX_BUILTIN_KEYS | dynamic_keys
    all_known    = file_known | global_known

    used_names: set[str] = set()
    undefined: dict[str, None] = {}

    def scan(template: str, known: set[str]) -> None:
        for name in _extract_placeholders(template):
            used_names.add(name)
            if name not in known and name not in undefined:
                undefined[name] = None

    scan(resolved.output, output_known)
    for entry in resolved.commands:
        scan(_job_command_text(entry), file_known)
    for entry in resolved.pre + resolved.post:
        scan(_job_command_text(entry), global_known)

    warnings = []
    for name in undefined:
        line = f"{_t('vc_undefined_placeholder')}: {{{name}}}"
        suggestion = difflib.get_close_matches(name, all_known, n=1, cutoff=0.6)
        if suggestion:
            line += f"\n{_t('vc_suggestion_maybe')}: {{{suggestion[0]}}}"
        warnings.append(line)

    return warnings, used_names


def _check_custom_keys(resolved: ResolvedJob, used_names: set[str]) -> tuple[list[str], list[str]]:
    warnings, infos = [], []
    for key in resolved.defaults:
        match = difflib.get_close_matches(key, _JOB_STANDARD_KEYS, n=1, cutoff=0.6)
        if match:
            warnings.append(f"{_t('vc_unknown_key')}: {key}\n{_t('vc_did_you_mean')} {match[0]}")
        elif key not in used_names:
            infos.append(f"{_t('vc_unused_key')}: {key}")
    return warnings, infos


def _check_global_keys(config: dict) -> tuple[list[str], list[str]]:
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


def _check_tool_paths(config: dict) -> list[str]:
    warnings = []
    tools = config.get("global", {}).get("tools", {})
    if not tools:
        return [_t("vc_no_tools_registered")]
    for name, path in tools.items():
        if not isinstance(path, str) or not path.strip():
            warnings.append(f"{_t('vc_tool_path_empty')}: {name}")
            continue
        if not Path(path).exists():
            warnings.append(f"{_t('vc_tool_path_missing')}: {name} -> {path}")
    return warnings


def _check_param_types(resolved: ResolvedJob) -> list[str]:
    warnings = []
    for p in resolved.params:
        if p.type not in _KNOWN_PARAM_TYPES:
            warnings.append(f"{_t('vc_unknown_param_type')}: {p.key} (type=\"{p.type}\")")
    return warnings


def _check_scalar_types(table: dict, label: str) -> list[str]:
    """
    [ko]
    병합된 ResolvedJob이 아니라 원본 TOML 테이블을 직접 검사한다 — global의
    잘못된 기본값을 물려받은 job마다 중복 보고되지 않도록, 이 레벨에서 명시적으로
    덮어쓴 값만 여기서 지적한다.

    [en]
    Type-checks the *raw* TOML table (not the merged ResolvedJob), so a job
    inheriting a bad global default isn't reported again on every job — only
    an explicit override at this level is flagged here.
    """
    warnings = []
    for key in _BOOL_KEYS:
        if key in table and not isinstance(table[key], bool):
            warnings.append(_t("vc_type_mismatch", label=f"{label}.{key}", expected="bool", got=type(table[key]).__name__))
    for key in _INT_KEYS:
        if key in table and (isinstance(table[key], bool) or not isinstance(table[key], int)):
            warnings.append(_t("vc_type_mismatch", label=f"{label}.{key}", expected="int", got=type(table[key]).__name__))
    if "on_error" in table and table["on_error"] not in _ON_ERROR_VALUES:
        warnings.append(f"{_t('vc_bad_enum_value')}: {label}.on_error = {table['on_error']!r} "
                         f"({'/'.join(sorted(_ON_ERROR_VALUES))})")
    if "input_mode" in table and table["input_mode"] not in _INPUT_MODE_VALUES:
        warnings.append(f"{_t('vc_bad_enum_value')}: {label}.input_mode = {table['input_mode']!r} "
                         f"({'/'.join(sorted(_INPUT_MODE_VALUES))})")
    if "include" in table and (
        not isinstance(table["include"], list)
        or not all(isinstance(v, str) for v in table["include"])
    ):
        warnings.append(_t("vc_type_mismatch", label=f"{label}.include", expected="list[str]", got=type(table["include"]).__name__))
    return warnings


def _resolve_fake_output(resolved: ResolvedJob, ext: str) -> tuple[Path, Path] | None:
    """
    [ko]
    가짜 입력 파일 "sample_file<ext>"에 대해 output이 실제로 어디로
    resolve되는지 계산한다. placeholder 치환이 실패하면(다른 체크가 별도로
    잡아냄) None을 반환한다.

    [en]
    Computes where output actually resolves to for a fake input file
    "sample_file<ext>". Returns None if placeholder substitution fails
    (caught separately by another check).
    """
    fake_input = _SCRIPT_DIR / "__validate_sample__" / f"sample_file{ext}"
    ctx_builder = ContextBuilder(resolved, {}, "validate")
    try:
        file_ctx = ctx_builder.build_file_context(fake_input, 1)
    except Exception:
        return None  # [ko] sample dry-run / placeholder 체크 쪽에서 별도로 잡힘 / [en] reported separately by the sample dry-run / placeholder checks
    return fake_input.resolve(), Path(file_ctx.output_path).resolve()


def _check_output_overwrite_risk(resolved: ResolvedJob, plugin_info: PluginInfo | None = None) -> list[str]:
    """
    [ko]
    output이 input을 덮어쓸 위험을 두 단계로 검사한다.

    1) 원래 방식: 확장자를 보존하는 output(예: "{dir}/{base}{ext}")이 input과
       완전히 같은 경로로 resolve되는 경우.
    2) 확장자 고정 케이스: output이 input의 실제 확장자와 무관하게 특정
       확장자를 강제하는 경우(예: "{dir}/{base}.png"), 1)에서 쓴 가짜 확장자
       ".ext"는 그 무엇과도 우연히 일치하지 않으므로 실제 위험(입력이 하필
       그 확장자일 때 덮어써짐)을 놓친다. 이를 감지하기 위해, output이
       강제하는 확장자를 그대로 가짜 입력의 확장자로 삼아 다시 한번 확인한다.

    [en]
    Checks the risk of output overwriting input, in two stages.

    1) The original approach: output that preserves the extension (e.g.
       "{dir}/{base}{ext}") resolves to exactly the same path as input.
    2) The fixed-extension case: when output forces a specific extension
       regardless of input's real extension (e.g. "{dir}/{base}.png"), the
       fake extension ".ext" used in (1) never coincidentally matches
       anything, so it misses the real risk (overwriting when input happens
       to have that extension). To catch this, output's forced extension is
       reused as the fake input's extension for a second check.
    """
    if resolved.allow_output_overwrite:
        return []  # [ko] 의도적으로 input을 덮어쓰는 Job (예: RemoveBOM) — 범용 opt-out / [en] a Job that intentionally overwrites input (e.g. RemoveBOM) — a general opt-out
    if plugin_info and plugin_info.session_type == "batch":
        return []  # [ko] BatchSession은 1:1 input/output 개념이 없음 (8.3.3) / [en] BatchSession has no 1:1 input/output concept (8.3.3)

    generic = _resolve_fake_output(resolved, ".ext")
    if generic is None:
        return []
    fake_input, output_path = generic
    if output_path == fake_input:
        return [f"{_t('vc_output_overwrites_input')}: output=\"{resolved.output}\""]

    forced_ext = output_path.suffix
    if not forced_ext or forced_ext == ".ext":
        return []  # [ko] output이 {ext}를 그대로 보존함 — 위 generic 체크로 이미 충분 / [en] output preserves {ext} as-is — already covered by the generic check above
    same_ext = _resolve_fake_output(resolved, forced_ext)
    if same_ext is not None and same_ext[1] == same_ext[0]:
        return [f"{_t('vc_output_overwrites_input_ext', ext=forced_ext)}: output=\"{resolved.output}\""]
    return []


def _check_sample_dry_run(resolved: ResolvedJob, sample_files: list[Path]) -> list[str]:
    errors = []
    ctx_builder = ContextBuilder(resolved, {}, "validate")
    for i, f in enumerate(sample_files, start=1):
        try:
            file_ctx = ctx_builder.build_file_context(f, i)
        except Exception as exc:
            errors.append(f"{_t('vc_sample_error')}: {f} -> {exc}")
            continue
        for entry in resolved.commands:
            text    = _job_command_text(entry)
            context = file_ctx.raw_ctx if isinstance(entry, dict) else file_ctx.ctx
            try:
                substitute(text, context)
            except Exception as exc:
                errors.append(f"{_t('vc_sample_error')}: {f.name} | {text} -> {exc}")
    return errors


def validate_global(config: dict) -> ValidationReport:
    report = ValidationReport("")
    warnings, infos = _check_global_keys(config)
    report.warnings.extend(warnings)
    report.infos.extend(infos)
    report.warnings.extend(_check_scalar_types(config.get("global", {}), "global"))
    report.warnings.extend(_check_tool_paths(config))
    return report


def validate_job(job_name: str, raw_job: dict, resolved: ResolvedJob, sample_files: list[Path] | None) -> ValidationReport:
    report = ValidationReport(job_name)

    # [ko] plugin은 먼저 1회만 로드한다 — 얻은 plugin_info를 아래 _check_required /
    #      _check_output_overwrite_risk에 재사용해 이중 로드를 피한다 (0번 구조적 수정).
    # [en] The plugin is loaded exactly once here — the resulting plugin_info is
    #      reused below in _check_required / _check_output_overwrite_risk to
    #      avoid loading it twice (structural fix #0).
    plugin_errors, plugin_warnings, plugin_info = _check_plugin(raw_job, resolved)

    report.errors.extend(_check_required(resolved, plugin_info))
    report.warnings.extend(_check_input_mode_usage(resolved))

    placeholder_warnings, used_names = _check_placeholders(resolved)
    report.warnings.extend(placeholder_warnings)

    key_warnings, key_infos = _check_custom_keys(resolved, used_names)
    report.warnings.extend(key_warnings)
    report.infos.extend(key_infos)

    report.warnings.extend(_check_param_types(resolved))
    report.errors.extend(_validate_param_presets(resolved.params, job_name))
    report.warnings.extend(_check_scalar_types(raw_job, f"jobs.{job_name}"))

    report.errors.extend(plugin_errors)
    report.warnings.extend(plugin_warnings)

    # [ko] 구조적으로 실행 가능한 job에 대해서만 심화 체크를 수행
    # [en] Deeper checks only make sense once the job is structurally runnable
    if (resolved.tool_path and resolved.commands) or resolved.plugin_name:
        report.warnings.extend(_check_output_overwrite_risk(resolved, plugin_info))
        if sample_files:
            report.errors.extend(_check_sample_dry_run(resolved, sample_files))

    return report


# ═══════════════════════════════════════════════════════════════════════════
# [ko] CLI & ENTRY POINT — CLI 및 진입점
# [en] CLI & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_config",
        description=_t("cli_description"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{_t("cli_epilog_header")}
  python validate_config.py config.toml
  python validate_config.py config.toml --job ResizeImages
  python validate_config.py config.toml --sample list.txt
  python validate_config.py config.toml --job Conv2PNG --sample list.txt --lang en
        """,
    )
    parser.add_argument("config", help=_t("help_config"))
    parser.add_argument("--job", default=None, help=_t("help_job"))
    parser.add_argument("--sample", default=None, metavar="filelist", help=_t("help_sample"))
    parser.add_argument("--lang", choices=["ko", "en"], default=None, help=_t("help_lang"))
    return parser.parse_args()


def main() -> None:
    _set_lang(_prescan_lang(sys.argv[1:]))
    args = parse_args()
    _set_lang(args.lang)

    loader = ConfigLoader(args.config)
    config = loader.load()  # [ko] TOML 문법 오류는 여기서 이미 사용자 친화적으로 sys.exit됨 / [en] a TOML syntax error already exits here with a user-friendly message
    if args.lang is None:
        _set_lang(config.get("global", {}).get("lang"))

    jobs = config.get("jobs", {})
    job_names = [args.job] if args.job else list(jobs.keys())
    if not job_names:
        sys.exit(_t("err_no_jobs"))

    sample_files = load_file_list(args.sample) if args.sample else None

    reports = [validate_global(config)]
    for name in job_names:
        resolved = loader.resolve_job(name)  # [ko] job 없으면 여기서 사용자 친화적으로 sys.exit됨 / [en] a missing job already exits here with a user-friendly message
        reports.append(validate_job(name, jobs[name], resolved, sample_files))

    total_errors   = sum(len(r.errors) for r in reports)
    total_warnings = sum(len(r.warnings) for r in reports)
    total_infos    = sum(len(r.infos) for r in reports)

    for r in reports:
        if not r.is_empty:
            print(r.format())
            print()

    print(_t("vc_summary_line", jobs=len(job_names), errors=total_errors, warnings=total_warnings, infos=total_infos))
    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
