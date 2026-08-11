"""
[ko]
tcbp.py 코어 로직 단위 테스트 — subprocess 없이 빠르게 도는 계층.
Stage 1~2에서 가장 까다로웠던 부분(bool/int 변환, slot 초과 처리,
frozen dataclass + pydantic 폴백)을 자동화한다.

[en]
Unit tests for tcbp.py's core logic — a layer that runs fast, without any
subprocess. Automates the trickiest parts from Stage 1-2 (bool/int
coercion, slot-overflow handling, frozen dataclass + pydantic fallback).
"""
import logging
from unittest.mock import MagicMock

import pytest

import tcbp
from tcbp import TcbpError


# [ko] _to_bool / _coerce_params (14.1)
# [en] _to_bool / _coerce_params (14.1)

@pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "YES", "on", "On"])
def test_to_bool_true_variants(raw):
    assert tcbp._to_bool(raw) is True


@pytest.mark.parametrize("raw", ["false", "FALSE", "0", "no", "NO", "off", "Off"])
def test_to_bool_false_variants(raw):
    assert tcbp._to_bool(raw) is False


def test_to_bool_invalid_raises():
    with pytest.raises(ValueError):
        tcbp._to_bool("maybe")


def test_coerce_params_only_declared_keys_converted():
    declared = [
        tcbp.JobParam(key="backup", type="bool"),
        tcbp.JobParam(key="size", type="int"),
    ]
    user_params = {"backup": "true", "size": "1024", "watermark": "logo.png"}
    result = tcbp._coerce_params(user_params, declared)
    assert result["backup"] is True
    assert result["size"] == 1024
    assert result["watermark"] == "logo.png"  # [ko] 선언 안 된 키는 문자열 그대로 / [en] an undeclared key stays a plain string


def test_coerce_params_invalid_bool_exits():
    declared = [tcbp.JobParam(key="backup", type="bool")]
    with pytest.raises(TcbpError):
        tcbp._coerce_params({"backup": "maybe"}, declared)


def test_coerce_params_invalid_int_exits():
    declared = [tcbp.JobParam(key="size", type="int")]
    with pytest.raises(TcbpError):
        tcbp._coerce_params({"size": "not_a_number"}, declared)


# [ko] _make_log_fn / --strict (10.3.1.1)
# [en] _make_log_fn / --strict (10.3.1.1)

def test_make_log_fn_sequential_mode_no_slot_limit():
    logger = MagicMock(spec=logging.Logger)
    log_fn = tcbp._make_log_fn(manager=None, index=1, notes_per_file=0, strict=False, logger=logger)
    log_fn("hello", slot=99)  # [ko] manager=None이면 slot 제약이 아예 없다 (10.3.2) / [en] with manager=None there is no slot constraint at all (10.3.2)
    logger.info.assert_called_once()
    assert "hello" in logger.info.call_args[0][0]


def test_make_log_fn_in_range_calls_manager_on_note():
    manager = MagicMock()
    logger = MagicMock(spec=logging.Logger)
    log_fn = tcbp._make_log_fn(manager=manager, index=3, notes_per_file=2, strict=False, logger=logger)
    log_fn("progress", slot=1)
    manager.on_note.assert_called_once_with(3, 1, "progress")
    logger.warning.assert_not_called()


def test_make_log_fn_out_of_range_default_warns_file_only():
    manager = MagicMock()
    logger = MagicMock(spec=logging.Logger)
    log_fn = tcbp._make_log_fn(manager=manager, index=1, notes_per_file=1, strict=False, logger=logger)
    log_fn("oops", slot=5)
    manager.on_note.assert_not_called()
    logger.warning.assert_called_once()
    _, kwargs = logger.warning.call_args
    assert kwargs.get("extra", {}).get("file_only") is True


def test_make_log_fn_out_of_range_strict_raises():
    manager = MagicMock()
    logger = MagicMock(spec=logging.Logger)
    log_fn = tcbp._make_log_fn(manager=manager, index=1, notes_per_file=1, strict=True, logger=logger)
    with pytest.raises(IndexError):
        log_fn("oops", slot=5)


def test_make_log_fn_negative_slot_is_out_of_range():
    manager = MagicMock()
    logger = MagicMock(spec=logging.Logger)
    log_fn = tcbp._make_log_fn(manager=manager, index=1, notes_per_file=2, strict=True, logger=logger)
    with pytest.raises(IndexError):
        log_fn("oops", slot=-1)


# [ko] strict_dataclass / frozen + 타입 검증 (3.5/3.8.1)
# [en] strict_dataclass / frozen + type validation (3.5/3.8.1)

def test_file_session_frozen():
    session = tcbp.FileSession(input="a", output="b", itemid=1, taskid="t", params={})
    with pytest.raises(Exception):
        session.input = "changed"


def test_file_session_type_validation_rejects_wrong_type():
    with pytest.raises(Exception):
        tcbp.FileSession(input=123, output="b", itemid=1, taskid="t", params={})  # [ko] input은 str이어야 함 / [en] input must be a str


def test_file_session_log_fn_wiring_via_object_setattr():
    """
    [ko]
    object.__setattr__로 주입한 _log_fn이 frozen을 우회해 정상 동작하는지
    (Session.log()가 실제로 그 콜백을 호출하는지) 확인 — Stage 1의 핵심 트릭.

    [en]
    Confirms that _log_fn injected via object.__setattr__ works correctly by
    bypassing frozen (i.e. that Session.log() actually calls that callback) —
    the key trick from Stage 1.
    """
    session = tcbp.FileSession(input="a", output="b", itemid=1, taskid="t", params={})
    calls = []
    object.__setattr__(session, "_log_fn", lambda text, slot: calls.append((text, slot)))
    session.log("hi", slot=2)
    assert calls == [("hi", 2)]


def test_batch_result_defaults_are_independent_lists():
    """
    [ko]
    PluginInfo.requirements와 동일 패턴 — dataclasses.field(default_factory=list)를
    안 쓰면 두 인스턴스가 default list를 공유하는 뮤터블 디폴트 함정에 빠진다.

    [en]
    Same pattern as PluginInfo.requirements — without
    dataclasses.field(default_factory=list), two instances would fall into
    the mutable-default trap of sharing the same default list.
    """
    r1 = tcbp.BatchResult(succeeded=["a"])
    r2 = tcbp.BatchResult()
    assert r1.succeeded == ["a"]
    assert r2.succeeded == []  # [ko] r1의 값이 r2 기본값에 새어들지 않아야 함 / [en] r1's value must not leak into r2's default


# [ko] _check_contract_version — 플러그인 계약 버전 호환성 정책
# [en] _check_contract_version — plugin contract-version compatibility policy

def test_check_contract_version_same_as_current_ok():
    tcbp._check_contract_version("dummy", tcbp.CONTRACT_VERSION)  # [ko] 예외 없이 통과해야 함 / [en] must pass without raising


def test_check_contract_version_major_mismatch_raises():
    with pytest.raises(TcbpError):
        tcbp._check_contract_version("dummy", "2.0")


def test_check_contract_version_minor_ahead_raises():
    with pytest.raises(TcbpError):
        tcbp._check_contract_version("dummy", "1.99")


def test_check_contract_version_invalid_format_raises():
    with pytest.raises(TcbpError):
        tcbp._check_contract_version("dummy", "not-a-version")


def test_check_contract_version_missing_minor_raises():
    with pytest.raises(TcbpError):
        tcbp._check_contract_version("dummy", "1")


# [ko] 모듈 자기-별칭 (플러그인 로딩용)
# [en] Module self-aliasing (for plugin loading)

def test_tcbp_self_aliased_in_sys_modules():
    import sys
    assert sys.modules.get("tcbp") is tcbp


# [ko] enumerate_directory / resolve_input_files — 폴더 입력 모드 (12장)
# [en] enumerate_directory / resolve_input_files — directory input mode (Chapter 12)

def _make_resolved_job(**overrides) -> "tcbp.ResolvedJob":
    """
    [ko] input_mode 계약 테스트 전용의 최소 ResolvedJob을 만든다.
    [en] Build a minimal ResolvedJob, only for input_mode contract tests.
    """
    base = dict(
        desc="", tool_name="", tool_path="dummy", on_error="continue",
        parallel=False, max_workers=4, output="{dir}/{base}_out{ext}",
        pre=[], commands=[{"msg": "x"}], post=[], log=False, log_file="",
        pause=False, tools={}, stderr_quiet=False, params=[], defaults={},
        notes_per_file=0, uses_output=False,
    )
    base.update(overrides)
    return tcbp.ResolvedJob(**base)


def test_enumerate_directory_recursive_finds_nested_files(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bmp").write_text("x")
    (tmp_path / "b.bmp").write_text("x")
    (tmp_path / "sub" / "c.bmp").write_text("x")
    (tmp_path / "note.txt").write_text("x")

    files = tcbp.enumerate_directory(tmp_path, recursive=True, include=["*.bmp"])

    assert [p.name for p in files] == ["a.bmp", "b.bmp", "c.bmp"]


def test_enumerate_directory_recursive_own_files_before_subfolders(tmp_path):
    # [ko] 폴더명이 숫자 문자열("001")이면 절대경로 문자열 전체 정렬 시 형제
    #      파일명("009.bmp")과 뒤섞일 수 있다 — "폴더 자신의 파일 먼저" 규칙 검증
    # [en] a numeric folder name ("001") can interleave with a sibling filename
    #      ("009.bmp") under a flat full-path string sort — verify the
    #      "this folder's own files first" rule instead
    (tmp_path / "001").mkdir()
    (tmp_path / "test A").mkdir()
    (tmp_path / "009.bmp").write_text("x")
    (tmp_path / "010.bmp").write_text("x")
    (tmp_path / "001" / "013.bmp").write_text("x")
    (tmp_path / "test A" / "040.bmp").write_text("x")

    files = tcbp.enumerate_directory(tmp_path, recursive=True, include=["*.bmp"])

    assert [p.name for p in files] == ["009.bmp", "010.bmp", "013.bmp", "040.bmp"]


def test_enumerate_directory_non_recursive_excludes_subfolders(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bmp").write_text("x")
    (tmp_path / "sub" / "c.bmp").write_text("x")

    files = tcbp.enumerate_directory(tmp_path, recursive=False, include=["*.bmp"])

    assert [p.name for p in files] == ["a.bmp"]


def test_enumerate_directory_multiple_include_patterns(tmp_path):
    (tmp_path / "a.jpg").write_text("x")
    (tmp_path / "b.jpeg").write_text("x")
    (tmp_path / "c.png").write_text("x")

    files = tcbp.enumerate_directory(tmp_path, recursive=False, include=["*.jpg", "*.jpeg"])

    assert sorted(p.name for p in files) == ["a.jpg", "b.jpeg"]


def test_enumerate_directory_empty_include_matches_everything(tmp_path):
    (tmp_path / "a.bmp").write_text("x")
    (tmp_path / "note.txt").write_text("x")

    files = tcbp.enumerate_directory(tmp_path, recursive=False, include=[])

    assert sorted(p.name for p in files) == ["a.bmp", "note.txt"]


def test_enumerate_directory_no_matches_exits(tmp_path):
    (tmp_path / "note.txt").write_text("x")
    with pytest.raises(TcbpError):
        tcbp.enumerate_directory(tmp_path, recursive=False, include=["*.bmp"])


def test_resolve_input_files_directory_mode_returns_sorted_files(tmp_path):
    (tmp_path / "b.bmp").write_text("x")
    (tmp_path / "a.bmp").write_text("x")
    job = _make_resolved_job(input_mode="directory", recursive=False, include=["*.bmp"])

    files = tcbp.resolve_input_files(str(tmp_path), job, "TestJob")

    assert [p.name for p in files] == ["a.bmp", "b.bmp"]


def test_resolve_input_files_directory_mode_rejects_file_argument(tmp_path):
    f = tmp_path / "list.txt"
    f.write_text(str(tmp_path / "a.bmp"))
    job = _make_resolved_job(input_mode="directory")

    with pytest.raises(TcbpError):
        tcbp.resolve_input_files(str(f), job, "TestJob")


def test_resolve_input_files_directory_mode_rejects_missing_path(tmp_path):
    job = _make_resolved_job(input_mode="directory")
    with pytest.raises(TcbpError):
        tcbp.resolve_input_files(str(tmp_path / "does_not_exist"), job, "TestJob")


def test_resolve_input_files_list_mode_rejects_directory_argument(tmp_path):
    job = _make_resolved_job()  # [ko] input_mode 기본값 "list" / [en] default input_mode is "list"
    with pytest.raises(TcbpError):
        tcbp.resolve_input_files(str(tmp_path), job, "TestJob")


def test_resolve_input_files_list_mode_reads_list_file(tmp_path):
    target = tmp_path / "a.bmp"
    target.write_text("x")
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(target), encoding="utf-8")
    job = _make_resolved_job()

    files = tcbp.resolve_input_files(str(listfile), job, "TestJob")

    assert files == [target]


# [ko] params[].preset — 값 타입/타입 매칭 (신규)
# [en] params[].preset — value type matching (new)

@pytest.mark.parametrize("value,ptype,expected", [
    (64, "int", True),
    (True, "int", False),   # [ko] bool은 int의 서브클래스지만 int로 인정하지 않는다 / [en] bool is an int subclass but must not count as int
    ("64", "int", False),
    (True, "bool", True),
    (1, "bool", False),
    ("abc", "", True),
    (1, "", False),
])
def test_value_matches_type(value, ptype, expected):
    assert tcbp._value_matches_type(value, ptype) is expected


def _preset_param(**overrides):
    base = dict(
        key="ch_bitrate", desc="", type="int", default=128,
        preset=[
            tcbp.PresetOption(label="128kbps", value=64),
            tcbp.PresetOption(label="192kbps", value=96),
            tcbp.PresetOption(label="256kbps", value=128),
            tcbp.PresetOption(label="320kbps", value=160),
        ],
    )
    base.update(overrides)
    return tcbp.JobParam(**base)


def test_validate_param_presets_ok_returns_no_errors():
    assert tcbp._validate_param_presets([_preset_param()]) == []


def test_validate_param_presets_type_mismatch_reported():
    p = _preset_param(default=None, preset=[tcbp.PresetOption(label="bad", value="64")])  # [ko] type="int"인데 preset 값이 문자열 / [en] type="int" but the preset value is a string
    errors = tcbp._validate_param_presets([p], job_name="MyJob")
    assert len(errors) == 1
    assert "ch_bitrate" in errors[0] and "MyJob" in errors[0]


def test_validate_param_presets_default_not_in_preset_reported():
    p = _preset_param(default=999)
    errors = tcbp._validate_param_presets([p])
    assert len(errors) == 1
    assert "999" in errors[0]


def test_validate_param_presets_missing_default_is_not_an_error():
    p = _preset_param(default=None)
    assert tcbp._validate_param_presets([p]) == []


def test_validate_param_presets_ignores_params_without_preset():
    p = tcbp.JobParam(key="size", type="int", default=999)  # default 999 without preset must not be flagged
    assert tcbp._validate_param_presets([p]) == []


def test_default_preset_index_finds_matching_default():
    p = _preset_param(default=96)
    assert tcbp._default_preset_index(p) == 1


def test_default_preset_index_falls_back_to_first_when_default_missing():
    p = _preset_param(default=None)
    assert tcbp._default_preset_index(p) == 0


def test_default_preset_index_falls_back_to_first_when_default_not_found():
    p = _preset_param(default=999)
    assert tcbp._default_preset_index(p) == 0


# [ko] _coerce_single (14.1 _coerce_params 리팩터)
# [en] _coerce_single (refactored out of _coerce_params, 14.1)

def test_coerce_single_untyped_returns_raw_unchanged():
    assert tcbp._coerce_single("hello", "") == "hello"


def test_coerce_single_int_success():
    assert tcbp._coerce_single("128", "int") == 128


def test_coerce_single_int_failure_returns_none():
    assert tcbp._coerce_single("nope", "int") is None


def test_coerce_single_bool_success():
    assert tcbp._coerce_single("true", "bool") is True


def test_coerce_single_bool_failure_returns_none():
    assert tcbp._coerce_single("maybe", "bool") is None


# [ko] CLI 값 우선 + preset 범위 검증 (검증 및 테스트 요구 4, 3)
# [en] CLI value priority + preset range validation (test requirements 3, 4)

def test_validate_cli_preset_values_accepts_in_range_value():
    p = _preset_param()
    tcbp._validate_cli_preset_values({"ch_bitrate": "96"}, [p])  # [ko] 예외 없이 통과해야 함 / [en] must pass without raising


def test_validate_cli_preset_values_rejects_out_of_range_value():
    p = _preset_param()
    with pytest.raises(TcbpError):
        tcbp._validate_cli_preset_values({"ch_bitrate": "999"}, [p])


def test_validate_cli_preset_values_rejects_type_mismatch():
    p = _preset_param()
    with pytest.raises(TcbpError):
        tcbp._validate_cli_preset_values({"ch_bitrate": "not_a_number"}, [p])


def test_validate_cli_preset_values_ignores_params_without_preset():
    p = tcbp.JobParam(key="size", type="int")
    tcbp._validate_cli_preset_values({"size": "anything_goes_here"}, [p])  # [ko] preset 없으면 검사 안 함 / [en] no preset means no check


# [ko] 폴백(번호 선택) UI — TTY/ANSI 미지원 환경 (요구사항 6, 7, 취소 흐름)
# [en] Fallback (numbered) UI — TTY/ANSI-unsupported environments (requirements 6, 7, cancel flow)

def test_select_option_fallback_enter_accepts_default(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    options = [tcbp.PresetOption(label="A", value="a"), tcbp.PresetOption(label="B", value="b")]
    assert tcbp._select_option_fallback(options, default_idx=1) == 1


def test_select_option_fallback_picks_numbered_choice(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")
    options = [tcbp.PresetOption(label="A", value="a"), tcbp.PresetOption(label="B", value="b")]
    assert tcbp._select_option_fallback(options, default_idx=0) == 1


def test_select_option_fallback_cancel_token_raises(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "c")
    options = [tcbp.PresetOption(label="A", value="a")]
    with pytest.raises(tcbp._PromptCancelled):
        tcbp._select_option_fallback(options, default_idx=0)


def test_select_option_fallback_invalid_then_valid_reprompts(monkeypatch):
    responses = iter(["9", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    options = [tcbp.PresetOption(label="A", value="a")]
    assert tcbp._select_option_fallback(options, default_idx=0) == 0


def test_prompt_missing_params_skips_cli_supplied_keys(monkeypatch):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(AssertionError("should not prompt")))
    job = _make_resolved_job(params=[tcbp.JobParam(key="size", type="int")])
    result = tcbp.prompt_missing_params(job, {"size": "1024"})
    assert result == {"size": "1024"}


def test_prompt_missing_params_sequential_multi_param(monkeypatch):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    responses = iter(["", "custom"])  # [ko] preset은 Enter=default, free-text는 직접 입력 / [en] preset: Enter=default; free-text: typed value
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    job = _make_resolved_job(params=[_preset_param(), tcbp.JobParam(key="label", type="")])

    result = tcbp.prompt_missing_params(job, {})

    assert result["ch_bitrate"] == "128"  # [ko] default(128kbps 항목의 value) / [en] the default (the 128kbps entry's value)
    assert result["label"] == "custom"


def test_prompt_missing_params_cancel_exits(monkeypatch):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "c")
    job = _make_resolved_job(params=[_preset_param()])
    with pytest.raises(TcbpError):
        tcbp.prompt_missing_params(job, {})


def test_prompt_free_text_non_interactive_enter_accepts_default(monkeypatch):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    meta = tcbp.JobParam(key="size", type="int", default=1024)
    assert tcbp._prompt_free_text(meta) == "1024"


# [ko] preset label 병기 — 값(64)과 사용자가 고른 라벨("128kbps")이 달라서 헛갈리는 문제 완화
# [en] Preset label pairing — mitigates the confusion where the stored value (64)
#      differs from the label the user picked ("128kbps")

def test_preset_label_for_finds_matching_label():
    p = _preset_param()
    assert tcbp._preset_label_for(p, 96) == "192kbps"


def test_preset_label_for_returns_none_when_not_found():
    p = _preset_param()
    assert tcbp._preset_label_for(p, 999) is None


def test_derive_preset_labels_adds_key_label_for_coerced_value():
    p = _preset_param()  # [ko] preset 값들이 int로 선언됨 — 이미 _coerce_params를 거친 것으로 간주 / [en] preset values are declared as int — assumes user_params already went through _coerce_params
    labels = tcbp._derive_preset_labels({"ch_bitrate": 96}, [p])
    assert labels == {"ch_bitrate_label": "192kbps"}


def test_derive_preset_labels_ignores_params_without_preset():
    p = tcbp.JobParam(key="size", type="int")
    assert tcbp._derive_preset_labels({"size": 1024}, [p]) == {}


# [ko] {key.label} / {key.value} dot 표기 문법 설탕 — 실제 getattr이 아니라
#      format_map() 이전의 텍스트 치환 계층이라는 점을 검증한다.
# [en] {key.label} / {key.value} dot-notation syntactic sugar — verifies this
#      is a text-preprocessing layer before format_map(), not real getattr.

def test_substitute_dot_label_resolves_to_derived_label():
    ctx = {"ch_bitrate": 64, "ch_bitrate_label": "128kbps (64kbps/ch)"}
    assert tcbp.substitute("Bitrate: {ch_bitrate.label}", ctx) == "Bitrate: 128kbps (64kbps/ch)"


def test_substitute_dot_value_matches_plain_placeholder():
    ctx = {"ch_bitrate": 64, "ch_bitrate_label": "128kbps (64kbps/ch)"}
    assert tcbp.substitute("{ch_bitrate.value}", ctx) == tcbp.substitute("{ch_bitrate}", ctx) == "64"


def test_substitute_dot_label_left_literal_when_no_preset_label():
    ctx = {"size": 1024}  # [ko] preset이 없으므로 size_label이 애초에 존재하지 않음 / [en] no preset, so size_label was never derived
    assert tcbp.substitute("{size.label}", ctx) == "{size.label}"


def test_substitute_dot_sugar_does_not_affect_unrelated_placeholders():
    ctx = {"ch_bitrate": 64, "ch_bitrate_label": "128kbps (64kbps/ch)", "name": "a.mp3"}
    result = tcbp.substitute("{name}: {ch_bitrate.label} ({ch_bitrate.value}kbps/ch)", ctx)
    assert result == "a.mp3: 128kbps (64kbps/ch) (64kbps/ch)"


def test_substitute_flat_label_placeholder_still_works_directly():
    # [ko] 하위호환 — dot 표기 도입 이전에 문서화된 flat 이름도 그대로 유효해야 함
    # [en] backward compatibility — the flat name documented before dot notation was added must still work
    ctx = {"ch_bitrate": 64, "ch_bitrate_label": "128kbps (64kbps/ch)"}
    assert tcbp.substitute("{ch_bitrate_label}", ctx) == "128kbps (64kbps/ch)"


def test_confirm_final_params_shows_selected_label_alongside_value(monkeypatch, capsys):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    job = _make_resolved_job(params=[_preset_param()])
    tcbp._confirm_final_params(job, {"ch_bitrate": "96"})  # [ko] raw string — CLI/프롬프트에서 온 값과 동일한 형태 / [en] raw string — matches the shape of a value coming from CLI/prompt
    out = capsys.readouterr().out
    assert "ch_bitrate = 96" in out
    assert "192kbps" in out


def test_confirm_final_params_cancel_selection_returns_false(monkeypatch, capsys):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")  # [ko] [1] 진행 [2] 취소 중 2번 선택 / [en] pick option [2] (Cancel) out of [1] Proceed / [2] Cancel
    job = _make_resolved_job(params=[tcbp.JobParam(key="size", type="int")])
    assert tcbp._confirm_final_params(job, {"size": "1024"}) is False


def test_confirm_final_params_proceed_default_returns_true(monkeypatch):
    monkeypatch.setattr(tcbp, "_interactive_available", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")  # [ko] Enter = 기본값(Proceed) / [en] Enter = default (Proceed)
    job = _make_resolved_job(params=[tcbp.JobParam(key="size", type="int")])
    assert tcbp._confirm_final_params(job, {"size": "1024"}) is True


# [ko] ANSI(방향키) UI — msvcrt.getwch()를 모킹해 실제 콘솔 없이 검증
# [en] ANSI (arrow-key) UI — verified without a real console by mocking msvcrt.getwch()

def _fake_getwch(keys):
    it = iter(keys)
    return lambda: next(it)


def test_select_option_ansi_navigates_down_and_confirms(monkeypatch):
    monkeypatch.setattr(tcbp, "_enable_win_ansi", lambda: None)
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\xe0", "P", "\xe0", "P", "\r"]))  # down, down, enter
    options = [tcbp.PresetOption(label="A", value="a"), tcbp.PresetOption(label="B", value="b"),
               tcbp.PresetOption(label="C", value="c")]
    assert tcbp._select_option_ansi(options, default_idx=0) == 2


def test_select_option_ansi_wraps_up_from_first(monkeypatch):
    monkeypatch.setattr(tcbp, "_enable_win_ansi", lambda: None)
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\xe0", "H", "\r"]))  # up, enter
    options = [tcbp.PresetOption(label="A", value="a"), tcbp.PresetOption(label="B", value="b")]
    assert tcbp._select_option_ansi(options, default_idx=0) == 1  # [ko] 첫 항목에서 위로 이동하면 마지막 항목으로 순환 / [en] moving up from the first entry wraps to the last


def test_select_option_ansi_esc_raises_cancelled(monkeypatch):
    monkeypatch.setattr(tcbp, "_enable_win_ansi", lambda: None)
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\x1b"]))
    options = [tcbp.PresetOption(label="A", value="a")]
    with pytest.raises(tcbp._PromptCancelled):
        tcbp._select_option_ansi(options, default_idx=0)


def test_read_line_prefilled_enter_confirms_default(monkeypatch, capsys):
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\r"]))
    assert tcbp._read_line_prefilled("size: ", "1024") == "1024"


def test_read_line_prefilled_backspace_then_retype(monkeypatch):
    # [ko] 프리필된 "1024"에서 두 글자(끝에서부터 "4","2") 지우고 "9"를 추가 → "109" (끝에서만 편집 가능한 의도된 단순화)
    # [en] Backspace twice on the prefilled "1024" (removes "4" then "2" from the end) then append "9" -> "109" (append/delete-at-end only, a deliberate simplification)
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\x08", "\x08", "9", "\r"]))
    assert tcbp._read_line_prefilled("size: ", "1024") == "109"


def test_read_line_prefilled_esc_raises_cancelled(monkeypatch):
    monkeypatch.setattr(tcbp.msvcrt, "getwch", _fake_getwch(["\x1b"]))
    with pytest.raises(tcbp._PromptCancelled):
        tcbp._read_line_prefilled("size: ", "1024")
