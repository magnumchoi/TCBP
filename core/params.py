"""
[ko] Named params 파싱
[en] Named Params Parsing

[ko] preset 선택 UI (questionary 없이 ANSI + msvcrt 키보드 입력만으로 구현).
     실제 콘솔(stdin/stdout이 tty)에서는 방향키 메뉴 + 프리필 편집 필드를 쓰고,
     TTY/ANSI를 지원하지 않는 환경(파이프/리다이렉트 등)에서는 번호 선택으로
     자동 폴백한다.
[en] The preset selection UI (ANSI + msvcrt keyboard input only — no
     questionary). A real console (stdin/stdout are ttys) gets an arrow-key
     menu and a prefilled editable field; environments without TTY/ANSI
     support (pipes/redirection) automatically fall back to numbered choice.
"""
import msvcrt
import sys

from core.config import _default_preset_index, _value_matches_type
from core.contract import TcbpError
from core.models import JobParam, PresetOption, ResolvedJob
from core.winapi import _enable_win_ansi
from messages import _t


class _PromptCancelled(Exception):
    """[ko] Esc 입력 시 현재 작업 전체를 취소하기 위한 내부 신호. / [en] Internal signal to cancel the whole operation when Esc is pressed."""


_ANSI_REVERSE = "\x1b[7m"
_ANSI_RESET   = "\x1b[0m"


def _interactive_available() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _read_key() -> str:
    """[ko] 키 1개를 읽어 "up"/"down"/"enter"/"esc" 중 하나 또는 빈 문자열로 정규화한다. / [en] Reads a single keypress and normalizes it to "up"/"down"/"enter"/"esc", or "" for anything else."""
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):  # [ko] 방향키/기능키 2바이트 시퀀스의 첫 바이트 / [en] first byte of a 2-byte arrow/function key sequence
        ch2 = msvcrt.getwch()
        return {"H": "up", "P": "down"}.get(ch2, "")
    if ch == "\r":
        return "enter"
    if ch == "\x1b":
        return "esc"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ""


def _select_option_ansi(options: list["PresetOption"], default_idx: int) -> int:
    _enable_win_ansi()
    idx = default_idx
    n = len(options)

    def draw(first: bool) -> None:
        if not first:
            sys.stdout.write(f"\x1b[{n}A")
        for i, opt in enumerate(options):
            if i == idx:
                line = f"  >> {_ANSI_REVERSE}{opt.label}{_ANSI_RESET}"
            else:
                line = f"     {opt.label}"
            sys.stdout.write("\x1b[2K" + line + "\n")
        sys.stdout.flush()

    draw(first=True)
    while True:
        key = _read_key()
        if key == "up":
            idx = (idx - 1) % n
            draw(first=False)
        elif key == "down":
            idx = (idx + 1) % n
            draw(first=False)
        elif key == "enter":
            return idx
        elif key == "esc":
            raise _PromptCancelled()


def _select_option_fallback(options: list["PresetOption"], default_idx: int) -> int:
    for i, opt in enumerate(options):
        marker = ">>" if i == default_idx else "  "
        print(f"    {marker} [{i + 1}] {opt.label}")
    while True:
        raw = input(f"  {_t('hint_select_fallback', default=default_idx + 1)}").strip()
        if raw == "":
            return default_idx
        if raw.lower() in ("c", "cancel"):
            raise _PromptCancelled()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(_t("err_invalid_choice"))


def _select_option(options: list["PresetOption"], default_idx: int) -> int:
    if _interactive_available():
        return _select_option_ansi(options, default_idx)
    return _select_option_fallback(options, default_idx)


def _prompt_preset(meta: "JobParam") -> str:
    print(f"  {meta.desc or meta.key}:")
    idx = _select_option(meta.preset, _default_preset_index(meta))
    return str(meta.preset[idx].value)


def _read_line_prefilled(prompt: str, default: str) -> str:
    """
    [ko]
    default 문자열이 미리 입력된 상태로 시작하는 편집 가능한 입력 필드.
    Enter만 누르면 default가 그대로 확정되고, Backspace로 지운 뒤 새로
    입력할 수도 있다. 좌우 화살표로 중간 커서를 이동하는 것은 지원하지
    않는다 — 끝에서 추가/삭제만 가능한 의도된 단순화.

    [en]
    An editable input field that starts pre-filled with `default`. Pressing
    Enter alone confirms the default as-is; Backspace can erase it to type a
    replacement. Left/right cursor movement mid-string is not supported —
    append/delete at the end only, a deliberate simplification.
    """
    buf = list(default)
    sys.stdout.write(prompt + default)
    sys.stdout.flush()
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # [ko] 방향키 등은 여기서 지원하지 않으므로 두 번째 바이트를 버림 / [en] arrow keys aren't supported here; discard the second byte
            continue
        if ch == "\r":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(buf)
        if ch == "\x1b":
            sys.stdout.write("\n")
            sys.stdout.flush()
            raise _PromptCancelled()
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch in ("\x08", "\x7f"):
            if buf:
                buf.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if ch.isprintable():
            buf.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()


def _prompt_free_text(meta: "JobParam") -> str:
    default_str = "" if meta.default is None else str(meta.default)
    label = meta.desc or meta.key
    interactive = _interactive_available()
    while True:
        if interactive:
            raw = _read_line_prefilled(f"  {label}: ", default_str)
        else:
            suffix = f" [{default_str}]" if default_str else ""
            typed = input(f"  {label}{suffix}: ").strip()
            raw = typed if typed else default_str
        if meta.type == "int":
            if raw.lstrip("-").isdigit():
                return raw
            print(_t("err_need_integer"))
        elif meta.type == "bool":
            if raw.strip().lower() in (_BOOL_TRUE | _BOOL_FALSE):
                return raw
            print(_t("err_need_bool"))
        else:
            return raw


def prompt_missing_params(job: ResolvedJob, user_params: dict) -> dict:
    declared = job.params
    if not declared:
        return user_params
    _validate_cli_preset_values(user_params, declared)
    result = dict(user_params)
    try:
        for meta in declared:
            key = meta.key
            if not key or key in result:
                continue
            if meta.preset:
                result[key] = _prompt_preset(meta)
            else:
                result[key] = _prompt_free_text(meta)
    except _PromptCancelled:
        raise TcbpError(_t("info_cancelled_by_user"))
    return result


def _confirm_final_params(job: ResolvedJob, user_params: dict) -> bool:
    print(_t("label_final_param_summary"))
    for p in job.params:
        if not p.key:
            continue
        value = user_params.get(p.key)
        line = f"    {p.key} = {value}"
        if p.preset:
            label = _preset_label_for(p, _coerce_single(str(value), p.type))
            if label is not None:
                line += f"  ({_t('label_selected_as', label=label)})"
        print(line)
    print(f"  {_t('label_confirm_prompt')}")
    options = [PresetOption(label=_t("label_proceed"), value=True),
               PresetOption(label=_t("label_cancel"), value=False)]
    try:
        idx = _select_option(options, 0)
    except _PromptCancelled:
        return False
    return options[idx].value


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


def _coerce_single(raw: str, ptype: str):
    """[ko] ptype="" 이면 raw를 그대로 반환. int/bool 변환 실패 시 None. / [en] Returns raw unchanged when ptype="". Returns None on int/bool conversion failure."""
    if not ptype:
        return raw
    try:
        if ptype == "int":
            return int(raw)
        if ptype == "bool":
            return _to_bool(raw)
    except (ValueError, TypeError):
        return None
    return raw


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
        coerced = _coerce_single(raw, meta.type)
        if coerced is None:
            raise TcbpError(_t("err_param_type_mismatch", param=meta.key, type=meta.type, value=raw))
        result[meta.key] = coerced
    return result


def _validate_cli_preset_values(user_params: dict, declared: list["JobParam"]) -> None:
    """[ko] preset이 선언된 파라미터에 CLI 값이 이미 들어오면 preset 범위를 검증한다 (interactive 질문은 건너뛰어도 범위 검증은 수행). / [en] For a param declared with preset, a CLI-supplied value still has its range validated even though the interactive question is skipped."""
    for meta in declared:
        if not meta.preset or meta.key not in user_params:
            continue
        raw = user_params[meta.key]
        coerced = _coerce_single(raw, meta.type)
        if coerced is None:
            raise TcbpError(_t("err_param_type_mismatch", param=meta.key, type=meta.type, value=raw))
        if not any(_value_matches_type(opt.value, meta.type) and opt.value == coerced for opt in meta.preset):
            allowed = ", ".join(str(opt.value) for opt in meta.preset)
            raise TcbpError(_t("err_preset_value_not_allowed", param=meta.key, value=raw, allowed=allowed))


def _preset_label_for(meta: "JobParam", value) -> "str | None":
    """[ko] preset 값 목록에서 (타입까지 일치하는) value에 대응하는 label을 찾는다 — 확인 화면/{key}_label placeholder가 "값과 고른 라벨이 달라 헛갈리는" 문제를 완화하는 데 쓴다. / [en] Finds the label matching value (type-checked) among preset entries — used to mitigate the "the value shown doesn't match the label I picked" confusion in the confirmation screen and the {key}_label placeholder."""
    for opt in meta.preset:
        if _value_matches_type(opt.value, meta.type) and opt.value == value:
            return opt.label
    return None


def _derive_preset_labels(user_params: dict, declared: list["JobParam"]) -> dict:
    """[ko] 이미 타입 변환된(coerced) user_params를 기준으로 {key}_label placeholder를 만든다 — pre/post {msg}에서 실제 값과 함께 사용자가 고른 라벨을 보여줄 수 있게 한다. / [en] Builds {key}_label placeholders from already-coerced user_params, so pre/post {msg} text can show the label the user picked alongside the actual value."""
    labels = {}
    for meta in declared:
        if not meta.preset or meta.key not in user_params:
            continue
        label = _preset_label_for(meta, user_params[meta.key])
        if label is not None:
            labels[f"{meta.key}_label"] = label
    return labels
