"""
[ko]
tcbp.py/validate_config.py 자체를 subprocess로 구동하는 end-to-end
테스트 (16.3.4). 전부 tmp_path 스크래치와 전용 임시 config.toml을 쓰고,
실제 config.toml/plugin/은 건드리지 않는다.

실제 config.toml의 [global] pause=true는 대화형 프롬프트라 subprocess
테스트와 안 맞으므로, 여기서는 pause=false로 둔 전용 임시 config를 쓴다 —
plugin = "..." 참조는 tcbp.py 자신의 위치(_SCRIPT_DIR) 기준으로 풀리므로
실제 plugin/remove_bom.py, plugin/group_md5.py를 그대로 재사용할 수 있다.

--strict/slot 초과의 subprocess 레벨 재현은 하지 않는다 — 그 로직 자체는
test_tcbp_core.py의 _make_log_fn 단위 테스트가 이미 커버한다(Stage 1에서
수동으로도 검증됨).

[en]
End-to-end tests that drive tcbp.py/validate_config.py themselves via
subprocess (16.3.4). All use tmp_path scratch space and a dedicated
temporary config.toml — the real config.toml/plugin/ are never touched.

The real config.toml's [global] pause=true is an interactive prompt, which
doesn't fit a subprocess test, so a dedicated temporary config with
pause=false is used here — a plugin = "..." reference resolves relative to
tcbp.py's own location (_SCRIPT_DIR), so the real plugin/remove_bom.py and
plugin/group_md5.py can be reused as-is.

Subprocess-level reproduction of --strict/slot overflow isn't done here —
that logic itself is already covered by test_tcbp_core.py's _make_log_fn
unit tests (also verified manually in Stage 1).
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TCBP_PY = ROOT / "tcbp.py"
VALIDATE_PY = ROOT / "validate_config.py"

_MINI_CONFIG = """
[global]
lang = "ko"
pause = false
log = false

[jobs.RemoveBOM]
desc                   = "test job"
plugin                 = "remove_bom"
output                 = "{dir}/{base}{ext}"
allow_output_overwrite = true
params = [
    { key="backup",   type="bool" },
    { key="eachline", type="bool" },
]

[jobs.GroupMD5]
desc   = "test job"
plugin = "group_md5"
output = ""
params = [
    { key="bom",        type="bool" },
    { key="chunk_size", type="int" },
]

[jobs.RemoveBOMDir]
desc                   = "test job (directory input mode, 12장)"
plugin                 = "remove_bom"
input_mode             = "directory"
recursive              = true
include                = ["*.txt"]
output                 = "{dir}/{base}{ext}"
allow_output_overwrite = true
params = [
    { key="backup",   type="bool" },
    { key="eachline", type="bool" },
]

[jobs.GroupMD5Preset]
desc   = "test job (params[].preset)"
plugin = "group_md5"
output = ""
params = [
    { key="chunk_size", desc="chunk size", type="int", default=64, preset=[
        { label="8",  value=8 },
        { label="16", value=16 },
        { label="32", value=32 },
        { label="64", value=64 },
    ] },
    { key="bom", desc="strip BOM", type="bool" },
]

[jobs.GroupMD5BadPreset]
desc   = "test job (preset default not in preset values -> config error)"
plugin = "group_md5"
output = ""
params = [
    { key="chunk_size", type="int", default=999, preset=[
        { label="8",  value=8 },
        { label="64", value=64 },
    ] },
]
"""


def _run(*args, cwd=None, stdin_input=None):
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=cwd or ROOT, input=stdin_input,
    )


@pytest.fixture()
def mini_config(tmp_path):
    cfg = tmp_path / "mini_config.toml"
    cfg.write_text(_MINI_CONFIG, encoding="utf-8")
    return cfg


def _make_bom_file(path: Path):
    path.write_bytes(bytes([0xEF, 0xBB, 0xBF]) + b"content")


@pytest.mark.integration
def test_validate_config_full_sweep_no_errors():
    proc = _run(str(VALIDATE_PY), "config.toml")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "총 오류 0개" in proc.stdout


@pytest.mark.integration
def test_tcbp_removebom_dry_run_leaves_files_untouched(tmp_path, mini_config):
    f = tmp_path / "a.txt"
    _make_bom_file(f)
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(f), encoding="utf-8")

    proc = _run(str(TCBP_PY), "RemoveBOM", str(listfile), "backup=false", "eachline=false",
                "--config", str(mini_config), "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[DRY-RUN]" in proc.stdout
    assert f.read_bytes().startswith(bytes([0xEF, 0xBB, 0xBF]))  # BOM 그대로


@pytest.mark.integration
def test_tcbp_removebom_real_run_strips_bom(tmp_path, mini_config):
    f = tmp_path / "a.txt"
    _make_bom_file(f)
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(f), encoding="utf-8")

    proc = _run(str(TCBP_PY), "RemoveBOM", str(listfile), "backup=false", "eachline=false",
                "--config", str(mini_config))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "성공: 1  실패: 0  전체: 1" in proc.stdout
    assert not f.read_bytes().startswith(bytes([0xEF, 0xBB, 0xBF]))


@pytest.mark.integration
def test_tcbp_groupmd5_dry_run_single_summary_line(tmp_path, mini_config):
    f1 = tmp_path / "sample.bin"
    f1.write_text("hi", encoding="utf-8")
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(f1), encoding="utf-8")

    proc = _run(str(TCBP_PY), "GroupMD5", str(listfile), "bom=false", "chunk_size=8",
                "--config", str(mini_config), "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "plugin=group_md5" in proc.stdout
    assert not list(tmp_path.glob("*.md5"))  # [ko] dry-run이라 실제 파일은 안 생김 / [en] no real file is created since this is a dry-run


@pytest.mark.integration
def test_tcbp_groupmd5_real_run_creates_md5(tmp_path, mini_config):
    f1 = tmp_path / "sample.bin"
    f1.write_text("hi", encoding="utf-8")
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(f1), encoding="utf-8")

    proc = _run(str(TCBP_PY), "GroupMD5", str(listfile), "bom=false", "chunk_size=8",
                "--config", str(mini_config))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert list(tmp_path.glob("*.md5"))  # [ko] BatchSession — output 없이도 정상 동작 (8.3.2 회귀 테스트) / [en] BatchSession — works fine without output (8.3.2 regression test)


# [ko] 폴더(디렉토리) 입력 모드 — input_mode 계약 (12장)
# [en] Folder (directory) input mode — the input_mode contract (Chapter 12)

@pytest.mark.integration
def test_tcbp_directory_mode_recursive_processes_nested_files(tmp_path, mini_config):
    (tmp_path / "sub").mkdir()
    _make_bom_file(tmp_path / "a.txt")
    _make_bom_file(tmp_path / "sub" / "b.txt")

    proc = _run(str(TCBP_PY), "RemoveBOMDir", str(tmp_path), "backup=false", "eachline=false",
                "--config", str(mini_config))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "성공: 2  실패: 0  전체: 2" in proc.stdout
    assert not (tmp_path / "a.txt").read_bytes().startswith(bytes([0xEF, 0xBB, 0xBF]))
    assert not (tmp_path / "sub" / "b.txt").read_bytes().startswith(bytes([0xEF, 0xBB, 0xBF]))


@pytest.mark.integration
def test_tcbp_directory_mode_rejects_file_argument(tmp_path, mini_config):
    listfile = tmp_path / "list.txt"
    listfile.write_text("hello", encoding="utf-8")

    proc = _run(str(TCBP_PY), "RemoveBOMDir", str(listfile), "backup=false", "eachline=false",
                "--config", str(mini_config))
    assert proc.returncode != 0
    assert "input_mode" in proc.stdout + proc.stderr


@pytest.mark.integration
def test_tcbp_list_mode_rejects_directory_argument(tmp_path, mini_config):
    proc = _run(str(TCBP_PY), "RemoveBOM", str(tmp_path), "backup=false", "eachline=false",
                "--config", str(mini_config))
    assert proc.returncode != 0
    assert "input_mode" in proc.stdout + proc.stderr


# [ko] params[].preset — 선택 UI / 최종 확인 (신규)
#      subprocess의 stdin은 tty가 아니므로 자동으로 번호 선택 폴백 경로를 탄다.
# [en] params[].preset — selection UI / final confirmation (new)
#      subprocess stdin is never a tty, so these automatically take the
#      numbered-fallback path.

@pytest.fixture()
def preset_listfile(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_text("hi", encoding="utf-8")
    listfile = tmp_path / "list.txt"
    listfile.write_text(str(f), encoding="utf-8")
    return listfile


@pytest.mark.integration
def test_tcbp_preset_default_config_error_exits(tmp_path, mini_config, preset_listfile):
    proc = _run(str(TCBP_PY), "GroupMD5BadPreset", str(preset_listfile), "--config", str(mini_config))
    assert proc.returncode != 0
    assert "preset" in (proc.stdout + proc.stderr).lower()


@pytest.mark.integration
def test_tcbp_preset_cli_value_out_of_range_rejected(tmp_path, mini_config, preset_listfile):
    proc = _run(str(TCBP_PY), "GroupMD5Preset", str(preset_listfile), "chunk_size=999", "bom=false",
                "--config", str(mini_config))
    assert proc.returncode != 0
    assert "999" in proc.stdout + proc.stderr


@pytest.mark.integration
def test_tcbp_preset_cli_priority_skips_prompt_and_confirm(tmp_path, mini_config, preset_listfile):
    proc = _run(str(TCBP_PY), "GroupMD5Preset", str(preset_listfile), "chunk_size=32", "bom=false",
                "--config", str(mini_config), "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "최종 파라미터 확인" not in proc.stdout  # [ko] 값이 전부 CLI로 주어졌으므로 확인 화면이 뜨지 않아야 함 / [en] all values came via CLI, so no confirmation screen should appear


@pytest.mark.integration
def test_tcbp_preset_sequential_prompt_shows_summary_and_proceeds(tmp_path, mini_config, preset_listfile):
    # [ko] chunk_size: Enter(=default 64), bom: "false" 입력, 최종 확인: Enter(=진행)
    # [en] chunk_size: Enter (=default 64), bom: type "false", final confirm: Enter (=proceed)
    proc = _run(str(TCBP_PY), "GroupMD5Preset", str(preset_listfile),
                "--config", str(mini_config), "--dry-run", stdin_input="\nfalse\n\n")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "최종 파라미터 확인" in proc.stdout
    assert "chunk_size = 64" in proc.stdout
    assert "bom = false" in proc.stdout


@pytest.mark.integration
def test_tcbp_preset_cancel_via_c_token_aborts(tmp_path, mini_config, preset_listfile):
    proc = _run(str(TCBP_PY), "GroupMD5Preset", str(preset_listfile),
                "--config", str(mini_config), "--dry-run", stdin_input="c\n")
    assert proc.returncode != 0
    assert "취소되었습니다" in proc.stdout + proc.stderr
    assert not list(tmp_path.glob("*.md5"))


@pytest.mark.integration
def test_tcbp_preset_final_confirm_cancel_skips_execution(tmp_path, mini_config, preset_listfile):
    # [ko] chunk_size/bom 모두 default 확정 후, 최종 확인 화면에서 "2"(취소) 선택
    # [en] confirm defaults for chunk_size/bom, then pick "2" (Cancel) at the final confirmation screen
    proc = _run(str(TCBP_PY), "GroupMD5Preset", str(preset_listfile),
                "--config", str(mini_config), stdin_input="\nfalse\n2\n")
    assert proc.returncode != 0
    assert "취소되었습니다" in proc.stdout + proc.stderr
    assert not list(tmp_path.glob("*.md5"))
