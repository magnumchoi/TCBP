"""
[ko] CommandExecutor & JobRunner — 실행 엔진
[en] CommandExecutor & JobRunner — Execution Engine
"""
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import logging

from core.plugins import load_plugin
from core.context import ContextBuilder, _gen_tmp_id, substitute
from core.contract import PluginInfo
from core.display import OutputManager, _max_name_display_len, _truncate_filename
from core.models import BatchResult, BatchSession, ExecResult, FileSession, GlobalContext, ResolvedJob
from core.params import _coerce_params, _derive_preset_labels
from core.winapi import _has_non_acp, _parse_cmdline
from messages import _t


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
        user_params = {**user_params, **_derive_preset_labels(user_params, self._job.params)}
        self._plugin_params = {**self._job.defaults, **user_params}

        task_id     = _gen_tmp_id()
        ctx_builder = ContextBuilder(self._job, user_params, task_id)
        global_ctx  = ctx_builder.build_global_context()
        total       = len(files)

        # [ko] Plugin은 main()이 미리 로드해서 넘겨준 값을 쓴다 (0번 구조적 수정 — 이중 로드
        #      방지 + _require_essentials()가 session_type을 미리 알 수 있게 함). run_fn이
        #      안 넘어온 채로 plugin_name만 있는 경우(=JobRunner 직접 호출)에만 폴백 로드.
        #      load_plugin()이 실패하면 TcbpError가 그대로 전파되어 main()의 단일
        #      처리 지점에서 처리된다 (10장).
        # [en] For plugins, use the value main() pre-loaded and passed in (structural
        #      fix #0 — avoids a double load and lets _require_essentials() know
        #      session_type ahead of time). Only falls back to loading it when
        #      run_fn wasn't passed in but plugin_name is set (JobRunner called directly).
        #      A load_plugin() failure simply propagates as TcbpError to main()'s single
        #      handling point (Chapter 10).
        run_fn: Callable | None = self._run_fn
        plugin_info: PluginInfo | None = self._plugin_info
        notes_per_file = self._job.notes_per_file
        if self._job.plugin_name and run_fn is None:
            run_fn = load_plugin(self._job.plugin_name)
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
                _log_fn=_make_log_fn(None, 0, 0, self._strict, self._logger),
            )
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

    def _warn_if_output_overwrites_input(self, file_path: Path, output_p: Path) -> None:
        # [ko] validate_config.py의 _check_output_overwrite_risk는 사전 진단용이라
        #      tcbp.py 실행 시 자동으로 호출되지 않는다 — 사용자가 검증을 건너뛰면
        #      원본 파일이 조용히 덮어써질 수 있으므로, 실제 실행 경로에서도 최소한의
        #      경고를 남긴다.
        # [en] validate_config.py's _check_output_overwrite_risk is a pre-run
        #      diagnostic and is never called automatically when tcbp.py runs — if a
        #      user skips validation, the original file could be silently overwritten,
        #      so leave a minimal warning on the actual execution path too.
        if self._job.allow_output_overwrite:
            return
        if output_p.resolve() == file_path.resolve():
            self._logger.warning(_t("warn_output_overwrites_input", path=str(output_p)))

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
        self._warn_if_output_overwrites_input(file_path, output_p)
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
                # [ko] mkdtemp()는 원자적 생성 + 소유권 강제를 보장해 수동 mkdir()보다
                #      symlink/TOCTOU 공격에 안전하다.
                # [en] mkdtemp() guarantees atomic creation + ownership enforcement,
                #      making it safer against symlink/TOCTOU attacks than a manual mkdir().
                tmp_dir = Path(tempfile.mkdtemp(prefix="tcbp_"))
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
        self._warn_if_output_overwrites_input(file_path, output_p)

        if manager:
            manager.on_start(index, file_path.name)
        else:
            max_len = _max_name_display_len()
            self._logger.info(f"[{index:>4}] {_truncate_filename(file_path.name, max_len)} → {_truncate_filename(output_p.name, max_len)}")

        session = FileSession(
            input=raw_ctx["input"], output=raw_ctx["output"],
            itemid=index, taskid=raw_ctx["taskid"],
            params=dict(self._plugin_params),  # [ko] 파일마다 새 복사본 — 병렬 워커들이 하나의 dict를 공유하지 않도록 / [en] a fresh copy per file — so parallel workers never share one dict
            _log_fn=_make_log_fn(manager, index, plugin_info.notes_per_file, self._strict, self._logger),
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
