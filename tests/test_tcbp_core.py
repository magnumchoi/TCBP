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
    with pytest.raises(SystemExit):
        tcbp._coerce_params({"backup": "maybe"}, declared)


def test_coerce_params_invalid_int_exits():
    declared = [tcbp.JobParam(key="size", type="int")]
    with pytest.raises(SystemExit):
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
    with pytest.raises(SystemExit):
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

    with pytest.raises(SystemExit):
        tcbp.resolve_input_files(str(f), job, "TestJob")


def test_resolve_input_files_directory_mode_rejects_missing_path(tmp_path):
    job = _make_resolved_job(input_mode="directory")
    with pytest.raises(SystemExit):
        tcbp.resolve_input_files(str(tmp_path / "does_not_exist"), job, "TestJob")


def test_resolve_input_files_list_mode_rejects_directory_argument(tmp_path):
    job = _make_resolved_job()  # [ko] input_mode 기본값 "list" / [en] default input_mode is "list"
    with pytest.raises(SystemExit):
        tcbp.resolve_input_files(str(tmp_path), job, "TestJob")


def test_resolve_input_files_list_mode_reads_list_file(tmp_path):
    target = tmp_path / "a.bmp"
    target.write_text("x")
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(target), encoding="utf-8")
    job = _make_resolved_job()

    files = tcbp.resolve_input_files(str(listfile), job, "TestJob")

    assert files == [target]
