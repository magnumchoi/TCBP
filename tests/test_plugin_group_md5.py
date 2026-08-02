"""
[ko]
plugin/group_md5.py 테스트. BatchSession이라 test_plugin_cli_golden.py의
1:1 input/output 골든 러너 대상이 아니다 — 이 파일 안에 unit(_process 직접
호출) + cli(단독 CLI를 subprocess로 구동) 테스트를 함께 둔다.

[en]
Tests for plugin/group_md5.py. As a BatchSession, it isn't a target for
test_plugin_cli_golden.py's 1:1 input/output golden runner — this file holds
both the unit tests (calling _process() directly) and the cli tests (driving
the standalone CLI via subprocess) together.
"""
import subprocess
import sys
from pathlib import Path

import pytest

import group_md5

PLUGIN_PATH = Path(__file__).resolve().parent.parent / "plugin" / "group_md5.py"


def _write(path: Path, text: str = "content"):
    path.write_text(text, encoding="utf-8")


# [ko] unit: _process() 직접 호출 (16.3.1)
# [en] unit: calling _process() directly (16.3.1)

def test_similar_filenames_are_grouped(tmp_path):
    f1 = tmp_path / "ABC-1234 Movie Title.mp4"
    f2 = tmp_path / "ABC-1234 Movie Title.srt"
    f3 = tmp_path / "Completely Different Name.jpg"
    for f in (f1, f2, f3):
        _write(f, str(f))

    logs = []
    result = group_md5._process([str(f1), str(f2), str(f3)], {"bom": False, "chunk_size": 8},
                                 log_fn=logs.append)

    assert sorted(result.succeeded) == sorted(str(f) for f in (f1, f2, f3))
    assert result.failed == []
    md5_files = list(tmp_path.glob("*.md5"))
    assert len(md5_files) == 2  # [ko] f1+f2가 한 그룹, f3가 단독 그룹 / [en] f1+f2 form one group, f3 is its own group
    assert any("created" in line for line in logs)


def test_missing_file_goes_to_failed(tmp_path):
    existing = tmp_path / "a.txt"
    _write(existing)
    missing = str(tmp_path / "does_not_exist.txt")

    result = group_md5._process([str(existing), missing], {"bom": False, "chunk_size": 8}, log_fn=lambda t: None)

    assert str(existing) in result.succeeded
    assert missing in result.failed


def test_md5_file_content_format(tmp_path):
    f1 = tmp_path / "sample.bin"
    _write(f1, "hello")
    group_md5._process([str(f1)], {"bom": False, "chunk_size": 8}, log_fn=lambda t: None)
    md5_files = list(tmp_path.glob("*.md5"))
    assert len(md5_files) == 1
    content = md5_files[0].read_text(encoding="utf-8")
    assert content.strip().endswith(f"*{f1.name}")
    md5_hex = content.split()[0]
    assert len(md5_hex) == 32  # MD5 hex digest 길이


def test_bom_option_writes_utf8_sig(tmp_path):
    f1 = tmp_path / "sample.bin"
    _write(f1, "hello")
    group_md5._process([str(f1)], {"bom": True, "chunk_size": 8}, log_fn=lambda t: None)
    md5_file = next(tmp_path.glob("*.md5"))
    assert md5_file.read_bytes().startswith(b"\xef\xbb\xbf")


def test_run_batch_session_returns_batch_result(tmp_path):
    from tcbp import BatchSession

    f1 = tmp_path / "a.txt"
    _write(f1)
    session = BatchSession(filelist=[str(f1)], output=None, taskid="t", params={"bom": False, "chunk_size": 8})
    object.__setattr__(session, "_log_fn", lambda text, slot: None)
    result = group_md5.run(session)
    assert str(f1) in result.succeeded


# [ko] cli: 단독 CLI를 subprocess로 구동 (4.5)
# [en] cli: driving the standalone CLI via subprocess (4.5)

@pytest.mark.cli
def test_standalone_cli_groups_and_hashes(tmp_path):
    f1 = tmp_path / "ABC-1234 Movie Title.mp4"
    f2 = tmp_path / "ABC-1234 Movie Title.srt"
    for f in (f1, f2):
        _write(f, str(f))
    list_file = tmp_path / "list.txt"
    list_file.write_text(f"{f1}\n{f2}\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(PLUGIN_PATH), str(list_file), "bom=false", "chunk_size=8"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "succeeded=2 failed=0" in proc.stdout
    assert list(tmp_path.glob("*.md5"))
