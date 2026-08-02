"""
[ko]
plugin/remove_bom.py의 _process() 직접 호출 — subprocess 없이 빠르게 검증
(16.3.1). argparse/CLI 계층은 test_plugin_cli_golden.py가 별도로 검증한다.

[en]
Calls plugin/remove_bom.py's _process() directly — a fast check with no
subprocess (16.3.1). The argparse/CLI layer is verified separately by
test_plugin_cli_golden.py.
"""
from pathlib import Path

import remove_bom

BOM = bytes([0xEF, 0xBB, 0xBF])


def test_strips_bom_at_start(tmp_path):
    src = tmp_path / "in.txt"
    src.write_bytes(BOM + b"hello world")
    remove_bom._process(str(src), str(src), {"backup": False, "eachline": False})
    assert src.read_bytes() == b"hello world"


def test_no_bom_leaves_file_untouched(tmp_path):
    src = tmp_path / "in.txt"
    original = b"no bom here"
    src.write_bytes(original)
    remove_bom._process(str(src), str(src), {"backup": False, "eachline": False})
    assert src.read_bytes() == original


def test_backup_created_only_when_bom_found(tmp_path):
    src = tmp_path / "in.txt"
    src.write_bytes(BOM + b"content")
    remove_bom._process(str(src), str(src), {"backup": True, "eachline": False})
    backup = Path(str(src) + ".bak")
    assert backup.exists()
    assert backup.read_bytes() == BOM + b"content"  # [ko] 백업은 원본(BOM 포함) 그대로 / [en] the backup keeps the original as-is (including the BOM)


def test_no_backup_when_no_bom(tmp_path):
    src = tmp_path / "in.txt"
    src.write_bytes(b"content")
    remove_bom._process(str(src), str(src), {"backup": True, "eachline": False})
    assert not Path(str(src) + ".bak").exists()


def test_eachline_strips_bom_from_every_line():
    result = remove_bom.remove_bom_each_line(BOM + b"line1\n" + BOM + b"line2")
    assert result.bytes == b"line1\nline2"
    assert result.bom_count == 2


def test_run_returns_exec_result_success(tmp_path):
    from tcbp import FileSession

    src = tmp_path / "in.txt"
    src.write_bytes(BOM + b"hi")
    session = FileSession(input=str(src), output=str(src), itemid=1, taskid="t",
                           params={"backup": False, "eachline": False})
    result = remove_bom.run(session)
    assert result.success is True
    assert src.read_bytes() == b"hi"


def test_run_returns_exec_result_failure_on_missing_file(tmp_path):
    from tcbp import FileSession

    missing = tmp_path / "does_not_exist.txt"
    session = FileSession(input=str(missing), output=str(missing), itemid=1, taskid="t",
                           params={"backup": False, "eachline": False})
    result = remove_bom.run(session)
    assert result.success is False
    assert result.message  # [ko] 에러 메시지가 비어있지 않아야 함 / [en] the error message must not be empty
