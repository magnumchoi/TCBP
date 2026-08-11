#!/usr/bin/env python3
"""
[ko]
tcbp.py - Total Commander Batch Python
TOML 기반 범용 배치 처리 엔진

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]

[en]
tcbp.py - Total Commander Batch Python
A generic TOML-based batch processing engine

Usage:
    python tcbp.py <JobName> <FileList> [key=value ...] [--config <path>] [--dry-run]
"""
import logging
import msvcrt
import os
import sys
from typing import Callable

"""
[ko]
현재 실행 중인 모듈을 "tcbp"라는 고정 이름으로 별칭 등록. 이후 동적 로딩되는
플러그인(load_plugin(), PART 4 참고) 안의 `from tcbp import ...`가 항상
이 실행 중인 모듈 인스턴스를 가리킨다.

[en]
Alias the currently-executing module under the fixed name "tcbp" so that
`from tcbp import ...` inside a dynamically-loaded plugin (see load_plugin(),
PART 4) always resolves to THIS running module instance.
"""
sys.modules.setdefault("tcbp", sys.modules[__name__])

# [ko] i18n — messages 패키지가 상태(_catalog)와 _t/_set_lang을 소유
# [en] i18n — the messages package owns the state (_catalog) and _t/_set_lang
from messages import _t, _set_lang
from core.cli import _prescan_lang, __version__  # [ko] 버전은 importlib.metadata 기반 — cli.py가 단일 소스 / [en] version via importlib.metadata — cli.py is the single source
_set_lang(_prescan_lang(sys.argv[1:]))  # [ko] argparse 이전 조기 언어 적용 / [en] apply --lang early, before argparse runs

# [ko] Windows 콘솔 UTF-8 출력 보장
# [en] Guarantee UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# [ko] 공개 API re-export — 플러그인과 validate_config.py가 `from tcbp import ...`로 접근
# [en] Public API re-export — plugins and validate_config.py access these via `from tcbp import ...`
from core.api import *  # noqa: F401, F403

# [ko] main()에서 필요한 내부 심볼 + 하위 호환을 위해 유지되는 그 밖의 공개 심볼
#      (테스트/플러그인이 직접 참조) — 로직 변경 없이 각자의 모듈에서 그대로 가져온다.
# [en] Internal symbols main() needs, plus other public symbols kept for backward
#      compatibility (referenced directly by tests/plugins) — pulled in as-is from
#      their respective modules, with no logic change.
from core.cli      import parse_args
from core.params   import (prompt_missing_params, parse_params, _coerce_params, _derive_preset_labels,
                            _PromptCancelled, _confirm_final_params, _interactive_available,
                            _select_option, _select_option_ansi, _select_option_fallback,
                            _prompt_preset, _read_line_prefilled, _prompt_free_text,
                            _to_bool, _coerce_single, _validate_cli_preset_values, _preset_label_for)
from core.config   import ConfigLoader, _require_essentials, _value_matches_type, _default_preset_index, _SCRIPT_DIR
from core.plugins  import load_plugin, _check_contract_version
from core.context  import resolve_input_files, enumerate_directory
from core.logging import setup_logging
from core.executor import JobRunner, CommandExecutor, PluginJobExecutor, _make_log_fn
from core.display  import OutputManager, _truncate_filename
from core.winapi   import _enable_win_ansi
from core.contract import TcbpError


# ═══════════════════════════════════════════════════════════════════════════
# [ko] 오류 출력 / 긴급 로그 (setup_logging 이전 크래시용)
# [en] Error Output / Emergency Log (for crashes before setup_logging)
# ═══════════════════════════════════════════════════════════════════════════

def _emergency_log(msg: str, *, test_mode: bool = False) -> None:
    """
    [ko] logger가 초기화되기 전 오류를 logs/tcbp_error.log에 기록한다.
    [en] Record an error that occurred before the logger was initialized into logs/tcbp_error.log.
    """
    try:
        import datetime
        log_dir = _SCRIPT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = "tcbp_error_test.log" if test_mode else "tcbp_error.log"
        path = log_dir / filename
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
    test_mode = os.environ.get("TCBP_TEST") == "1"
    try:
        args        = parse_args()
        print(f"TCBP (v{__version__})")
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
            except TcbpError as exc:
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

        needs_prompt = any(p.key and p.key not in user_params for p in _job.params)
        user_params  = prompt_missing_params(_job, user_params)
        if needs_prompt and not _confirm_final_params(_job, user_params):
            sys.exit(_t("info_cancelled_by_user"))
        files       = resolve_input_files(args.filelist, _job, args.job)

        mode = f"parallel (max_workers={_job.max_workers})" if _job.parallel else "sequential"
        _logger.info(_t("info_file_count", count=len(files), mode=mode))

        runner = JobRunner(_job, _logger, args.dry_run, args.strict, run_fn=run_fn, plugin_info=plugin_info)
        runner.run(files, user_params)

    except TcbpError as e:
        msg = str(e)
        if _logger:
            _logger.error(msg)
        else:
            _emergency_log(msg, test_mode=test_mode)
        _pause_on_error(msg)
        sys.exit(msg)
    except Exception:
        import traceback
        msg = traceback.format_exc()
        if _logger:
            _logger.error(msg)
        else:
            _emergency_log(msg, test_mode=test_mode)
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
