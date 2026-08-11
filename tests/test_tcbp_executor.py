"""
[ko]
core/executor.py(CommandExecutor, JobRunner)와 core/display.py(OutputManager)의
직접 단위테스트 — subprocess 없이 빠르게 도는 계층. 지금까지
test_tcbp_integration.py의 느린 subprocess 통합테스트로만 간접 검증되던
오케스트레이션 로직(병렬/순차 분기, on_error=stop 취소, ANSI 블록 순서
보장, plugin 성공-그러나-output-미생성 안전장치)을 직접 검증한다.

[en]
Direct unit tests for core/executor.py (CommandExecutor, JobRunner) and
core/display.py (OutputManager) — a layer that runs fast, without any
subprocess. Directly verifies orchestration logic (parallel/sequential
branching, on_error=stop cancellation, ANSI block ordering, the
plugin-succeeded-but-no-output safety net) that was previously only
indirectly covered by test_tcbp_integration.py's slow subprocess-based tests.
"""
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import tcbp


def _logger():
    return MagicMock(spec=logging.Logger)


def _make_resolved_job(**overrides) -> "tcbp.ResolvedJob":
    base = dict(
        desc="", tool_name="", tool_path="dummy_tool", on_error="continue",
        parallel=False, max_workers=4, output="{dir}/{base}_out{ext}",
        pre=[], commands=["tool {input} {output}"], post=[], log=False, log_file="",
        pause=False, tools={}, stderr_quiet=False, params=[], defaults={},
        notes_per_file=0, uses_output=False,
    )
    base.update(overrides)
    return tcbp.ResolvedJob(**base)


def _make_files(tmp_path, names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_text("x", encoding="utf-8")
        paths.append(p)
    return paths


def _fake_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ============================================================
# [ko] CommandExecutor
# [en] CommandExecutor
# ============================================================

def test_command_executor_dry_run_skips_subprocess(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("dry-run must not spawn a subprocess"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=True)
    result = ex.run("some command")
    assert result.success is True
    assert "[DRY-RUN]" in logger.info.call_args[0][0]


def test_command_executor_success_logs_stdout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0, stdout="done"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=False)
    result = ex.run("tool a.txt")
    assert result.success is True
    logger.info.assert_any_call("  done")


def test_command_executor_failure_returns_stderr_as_message(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=1, stderr="boom"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=False)
    result = ex.run("tool a.txt")
    assert result.success is False
    assert result.message == "boom"
    assert any("STDERR: boom" in str(c) for c in logger.warning.call_args_list)


def test_command_executor_quiet_suppresses_all_logging(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0, stdout="hi", stderr="warn"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=False)
    ex.run("tool a.txt", quiet=True)
    logger.info.assert_not_called()
    logger.warning.assert_not_called()


def test_command_executor_stderr_quiet_suppresses_stderr_only(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0, stdout="hi", stderr="warn"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=False, stderr_quiet=True)
    ex.run("tool a.txt")
    logger.info.assert_any_call("  hi")
    logger.warning.assert_not_called()


def test_command_executor_run_pre_post_msg_entry_never_spawns_subprocess(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("a { msg = ... } entry must not spawn a subprocess"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=False)
    global_ctx = tcbp.GlobalContext(ctx={}, raw_ctx={"taskid": "t1"})
    ex.run_pre_post([{"msg": "Starting batch {taskid}"}], global_ctx, "PRE")
    logger.info.assert_called_once_with("Starting batch t1")


def test_command_executor_run_pre_post_dry_run_prefixes_label(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("dry-run must not spawn a subprocess"))
    logger = _logger()
    ex = tcbp.CommandExecutor(logger, dry_run=True)
    global_ctx = tcbp.GlobalContext(ctx={"taskid": "t1"}, raw_ctx={"taskid": "t1"})
    ex.run_pre_post(["echo {taskid}"], global_ctx, "POST")
    assert logger.info.call_args[0][0] == "[DRY-RUN][POST] echo t1"


# ============================================================
# [ko] OutputManager — ANSI 블록 순서 보장 (콘솔 출력이 아니라
#      logger.debug()에 찍히는 평문 내용으로 검증한다 — ANSI 이스케이프
#      파싱을 피하면서도 순서/내용을 정확히 확인할 수 있다)
# [en] OutputManager — order-preserving ANSI blocks (verified via the plain
#      text passed to logger.debug() rather than parsing ANSI escapes —
#      avoids ANSI parsing while still precisely checking order/content)
# ============================================================

def test_output_manager_start_buffers_until_predecessor_arrives(capsys):
    logger = _logger()
    mgr = tcbp.OutputManager(logger, notes_per_file=0)
    mgr.on_start(2, "b.txt")
    assert "b.txt" not in capsys.readouterr().out  # [ko] idx=1이 아직 안 와서 버퍼링됨 / [en] buffered — idx=1 hasn't arrived yet
    mgr.on_start(1, "a.txt")
    out = capsys.readouterr().out
    assert "a.txt" in out and "b.txt" in out
    assert out.index("a.txt") < out.index("b.txt")  # [ko] 둘 다 이제서야 순서대로 flush / [en] both flush now, in order


def test_output_manager_finish_written_in_completion_order_not_index_order(capsys):
    logger = _logger()
    mgr = tcbp.OutputManager(logger, notes_per_file=0)
    mgr.on_start(1, "a.txt")
    mgr.on_start(2, "b.txt")
    capsys.readouterr()  # [ko] start 출력 비우기 / [en] drain the start output
    mgr.on_finish(2, "b.txt", "b_out.txt", True)
    mgr.on_finish(1, "a.txt", "a_out.txt", False)
    lines = [c.args[0] for c in logger.debug.call_args_list]
    assert len(lines) == 2
    assert "[   2]" in lines[0] and "→" in lines[0]   # [ko] 먼저 끝난 2번이 먼저 기록됨 / [en] idx 2 finished first, so it's recorded first
    assert "[   1]" in lines[1] and "✗" in lines[1]


def test_output_manager_note_before_start_is_queued_then_applied_on_flush():
    logger = _logger()
    mgr = tcbp.OutputManager(logger, notes_per_file=1)
    mgr.on_note(1, 0, "queued message")  # [ko] idx=1 블록이 아직 화면에 없음 / [en] idx=1's block hasn't appeared yet
    logger.debug.assert_not_called()
    mgr.on_start(1, "a.txt")
    assert logger.debug.call_count == 1
    assert "queued message" in logger.debug.call_args[0][0]


def test_output_manager_note_after_start_written_immediately():
    logger = _logger()
    mgr = tcbp.OutputManager(logger, notes_per_file=1)
    mgr.on_start(1, "a.txt")
    mgr.on_note(1, 0, "progress update")
    assert logger.debug.call_count == 1
    assert "progress update" in logger.debug.call_args[0][0]


def test_output_manager_block_reserves_one_blank_line_per_note_slot(capsys):
    logger = _logger()
    mgr = tcbp.OutputManager(logger, notes_per_file=2)
    mgr.on_start(1, "a.txt")
    out = capsys.readouterr().out
    # [ko] 제목줄 1 + notes_per_file(2)만큼의 예약 빈 줄 = 3줄. on_error=stop 등으로
    #      note가 끝내 안 와도 이 빈 줄은 그대로 남아 "중단 시 빈 칸으로 flush"를 만족한다.
    # [en] Title line (1) + notes_per_file (2) reserved blank lines = 3 lines. Even if
    #      a note never arrives (e.g. on_error=stop), this reserved blank line simply
    #      stays blank, satisfying "flush as a blank line on abort".
    assert out.count("\n") == 3


# ============================================================
# [ko] JobRunner — 오케스트레이션 (CommandExecutor.run을 몽키패치해 실제
#      subprocess 없이 성공/실패 조합을 정확히 통제한다)
# [en] JobRunner — orchestration (CommandExecutor.run is monkeypatched so
#      success/failure combinations are controlled precisely without a real
#      subprocess)
# ============================================================

def test_jobrunner_dry_run_never_spawns_a_real_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("dry-run must never spawn a real subprocess"))
    job = _make_resolved_job()
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt", "b.txt"])
    tcbp.JobRunner(job, logger, dry_run=True).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "성공: 2" in summary and "실패: 0" in summary and "전체: 2" in summary


def test_jobrunner_sequential_all_succeed(tmp_path, monkeypatch):
    monkeypatch.setattr(tcbp.CommandExecutor, "run", lambda self, cmd, cwd=None, quiet=False: tcbp.ExecResult(True, ""))
    job = _make_resolved_job()
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt", "b.txt"])
    tcbp.JobRunner(job, logger, dry_run=False).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "성공: 2" in summary and "실패: 0" in summary and "전체: 2" in summary


def test_jobrunner_sequential_on_error_stop_aborts_after_first_failure(tmp_path, monkeypatch):
    calls = []

    def fake_run(self, cmd, cwd=None, quiet=False):
        calls.append(cmd)
        return tcbp.ExecResult(False, "boom")

    monkeypatch.setattr(tcbp.CommandExecutor, "run", fake_run)
    job = _make_resolved_job(on_error="stop")
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt", "b.txt", "c.txt"])
    tcbp.JobRunner(job, logger, dry_run=False).run(files, {})
    assert len(calls) == 1  # [ko] 첫 파일 실패 후 나머지는 아예 시도하지 않음 / [en] the rest are never even attempted after the first failure
    summary = logger.info.call_args_list[-1].args[0]
    assert "실패: 1" in summary and "전체: 3" in summary


def test_jobrunner_sequential_on_error_continue_processes_every_file(tmp_path, monkeypatch):
    calls = []

    def fake_run(self, cmd, cwd=None, quiet=False):
        calls.append(cmd)
        return tcbp.ExecResult(False, "boom")

    monkeypatch.setattr(tcbp.CommandExecutor, "run", fake_run)
    job = _make_resolved_job(on_error="continue")
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt", "b.txt", "c.txt"])
    tcbp.JobRunner(job, logger, dry_run=False).run(files, {})
    assert len(calls) == 3
    summary = logger.info.call_args_list[-1].args[0]
    assert "실패: 3" in summary and "전체: 3" in summary


def test_jobrunner_parallel_processes_all_files_and_counts_correctly(tmp_path, monkeypatch):
    monkeypatch.setattr(tcbp.CommandExecutor, "run", lambda self, cmd, cwd=None, quiet=False: tcbp.ExecResult(True, ""))
    job = _make_resolved_job(parallel=True, max_workers=4)
    logger = _logger()
    files = _make_files(tmp_path, [f"f{i}.txt" for i in range(5)])
    tcbp.JobRunner(job, logger, dry_run=False).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "성공: 5" in summary and "실패: 0" in summary and "전체: 5" in summary


def test_jobrunner_parallel_on_error_stop_cancels_pending_tasks(tmp_path, monkeypatch):
    """
    [ko]
    max_workers=1이므로 단일 워커는 큐를 제출 순서(1..6)대로만 처리할 수 있다 —
    즉 나중 파일이 실행됐다면 그 앞의 파일들도 전부 실행됐어야 한다. 1번째 파일이
    즉시 실패하면 on_error=stop이 그 자리에서 남은 futures를 취소하므로, "정확히
    몇 번째까지 실행됐는가"는 취소 시점과 워커 스케줄링의 미세한 경합에 달려
    있어 결정적이지 않지만(그래서 정확히 1개만 호출됐는지는 단언하지 않는다),
    최소한 **마지막 파일만큼은 절대 실행되지 않는다** — 6개 전부가 그 좁은 경합
    창 안에서 끝나는 것은 사실상 불가능하다. 취소 로직 자체가 완전히 사라지면
    (예: `for f in future_map: f.cancel()`가 삭제되면) 6개 전부 실행되어 이
    단언이 깨지므로, 회귀 감지 목적은 그대로 달성한다.

    [en]
    With max_workers=1, the single worker can only ever process the queue in
    submission order (1..6) — so if a later file ran, every file before it
    must have run too. Since on_error=stop cancels the remaining futures the
    instant the 1st file fails, exactly how many files ran before cancellation
    lands is subject to a narrow scheduling race (so this doesn't assert
    exactly one call) — but at minimum the **last file is guaranteed to never
    run**, since all 6 completing within that narrow race window is
    effectively impossible. If the cancellation logic were removed entirely
    (e.g. the `for f in future_map: f.cancel()` line got deleted), all 6 would
    run and this assertion would catch it — so the regression-detection goal
    still holds.
    """
    calls = []

    def fake_run(self, cmd, cwd=None, quiet=False):
        calls.append(cmd)
        return tcbp.ExecResult(False, "boom")

    monkeypatch.setattr(tcbp.CommandExecutor, "run", fake_run)
    job = _make_resolved_job(parallel=True, max_workers=1, on_error="stop")
    logger = _logger()
    files = _make_files(tmp_path, [f"f{i}.txt" for i in range(6)])
    tcbp.JobRunner(job, logger, dry_run=False).run(files, {})
    assert calls[0] == 'tool "f0.txt" "f0_out.txt"'
    assert 'tool "f5.txt" "f5_out.txt"' not in calls
    assert len(calls) < 6


def _make_plugin_info(**overrides) -> "tcbp.PluginInfo":
    base = dict(
        name="dummy", contract_version=tcbp.CONTRACT_VERSION, version="1.0", author="test",
        session_type="file", requirements=[], notes_per_file=0, thread_safe=True,
    )
    base.update(overrides)
    return tcbp.PluginInfo(**base)


def test_jobrunner_file_plugin_success_with_output_written(tmp_path):
    def run_fn(session):
        Path(session.output).write_text("done", encoding="utf-8")
        return tcbp.ExecResult(True, "")
    run_fn.plugin_info = _make_plugin_info()

    job = _make_resolved_job(plugin_name="dummy", commands=[])
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt"])
    tcbp.JobRunner(job, logger, dry_run=False, run_fn=run_fn, plugin_info=run_fn.plugin_info).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "성공: 1" in summary and "실패: 0" in summary


def test_jobrunner_file_plugin_success_without_output_file_is_downgraded_to_failure(tmp_path):
    """
    [ko] remove_bom처럼 output을 안 써도 성공을 반환하는 플러그인 대비 안전장치
         (core/executor.py의 _process_file_plugin 참고) — CLI Job의 uses_output
         검사와 동등한 보호를 플러그인에도 적용한다.
    [en] The safety net for a plugin that returns success without ever writing
         output (like remove_bom) — see _process_file_plugin in
         core/executor.py. Applies the same protection CLI Jobs get from the
         uses_output check.
    """
    def run_fn(session):
        return tcbp.ExecResult(True, "")  # [ko] 파일을 실제로 쓰지 않음 / [en] never actually writes the file

    run_fn.plugin_info = _make_plugin_info()
    job = _make_resolved_job(plugin_name="dummy", commands=[])
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt"])
    tcbp.JobRunner(job, logger, dry_run=False, run_fn=run_fn, plugin_info=run_fn.plugin_info).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "실패: 1" in summary


def test_jobrunner_batch_plugin_uses_batch_result_counts(tmp_path):
    def run_fn(session):
        return tcbp.BatchResult(succeeded=session.filelist[:2], failed=session.filelist[2:])
    run_fn.plugin_info = _make_plugin_info(session_type="batch")

    job = _make_resolved_job(plugin_name="dummy_batch", commands=[], output="")
    logger = _logger()
    files = _make_files(tmp_path, ["a.txt", "b.txt", "c.txt"])
    tcbp.JobRunner(job, logger, dry_run=False, run_fn=run_fn, plugin_info=run_fn.plugin_info).run(files, {})
    summary = logger.info.call_args_list[-1].args[0]
    assert "성공: 2" in summary and "실패: 1" in summary and "전체: 3" in summary
