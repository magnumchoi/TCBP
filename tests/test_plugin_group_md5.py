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


# [ko] unit: 토큰화 / 가변 구간(Variable Segment) 정규화
# [en] unit: tokenization / Variable Segment normalization

@pytest.mark.parametrize("stem, expected", [
    ("AAA001", ["AAA", "001"]),
    ("PART12", ["PART", "12"]),
    ("DISC_A", ["DISC", "A"]),
])
def test_tokenize_stem_splits_letter_digit_boundary(stem, expected):
    assert group_md5._tokenize_stem(stem) == expected


def test_tokenize_stem_keeps_hyphenated_part_codes_intact():
    # [ko] "ABC-1234"는 letter/digit 사이에 하이픈이 끼어 있으므로 분리되지 않아야 한다
    # [en] "ABC-1234" must not split — a hyphen sits between the letter and digit
    assert group_md5._tokenize_stem("ABC-1234 Movie") == ["ABC-1234", "Movie"]


@pytest.mark.parametrize("tokens, expected", [
    (["DISC1"], ["<VARIABLE>"]),
    (["DISC", "1"], ["<VARIABLE>"]),
    (["DISC", "A"], ["<VARIABLE>"]),
    (["PART", "01"], ["<VARIABLE>"]),
])
def test_normalize_variable_tokens(tokens, expected):
    assert group_md5._normalize_variable_tokens(tokens) == expected


def test_normalize_variable_tokens_preserves_non_variable_tokens():
    assert group_md5._normalize_variable_tokens(["영화", "제목", "PART", "1"]) == ["영화", "제목", "<VARIABLE>"]


# [ko] unit: group_files_by_pattern() 그룹핑 요구사항 사례 (요구사항 문서 10)
# [en] unit: group_files_by_pattern() grouping cases required by the spec doc (doc section 10)

def test_numbered_sequence_files_are_grouped_and_named_without_numbers():
    files = [r"C:\dir\AAA001.jpg", r"C:\dir\AAA002.jpg", r"C:\dir\AAA003.jpg",
              r"C:\dir\BBB001.jpg", r"C:\dir\BBB002.jpg", r"C:\dir\BBB003.jpg"]
    groups = group_md5.group_files_by_pattern(files)
    patterns = {key.split("|", 1)[1]: paths for key, paths in groups.items()}
    assert set(patterns) == {"AAA", "BBB"}
    assert len(patterns["AAA"]) == 3
    assert len(patterns["BBB"]) == 3


def test_part_prefixed_files_group_with_bare_title():
    files = [r"C:\dir\블라블라 영화 제목.jpg", r"C:\dir\블라블라 영화 제목 PART1.mp4",
              r"C:\dir\블라블라 영화 제목 PART2.mp4"]
    groups = group_md5.group_files_by_pattern(files)
    assert len(groups) == 1
    (key, paths), = groups.items()
    assert key.split("|", 1)[1] == "블라블라 영화 제목"
    assert len(paths) == 3


def test_disc_underscore_suffix_files_group_with_bare_title():
    files = [r"C:\dir\중얼중얼중얼 만화 제목.jpg", r"C:\dir\중얼중얼중얼 만화 제목 disc_A.jpg",
              r"C:\dir\중얼중얼중얼 만화 제목 disc_B.jpg"]
    groups = group_md5.group_files_by_pattern(files)
    assert len(groups) == 1
    (key, paths), = groups.items()
    assert key.split("|", 1)[1] == "중얼중얼중얼 만화 제목"
    assert len(paths) == 3


def test_variable_segment_stripped_even_with_surrounding_bracket_tokens():
    files = [r"C:\dir\블라블라 영화 제목 [제작사] 품번.jpg",
              r"C:\dir\블라블라 영화 제목 DISC1 [제작사] 품번.mp4",
              r"C:\dir\블라블라 영화 제목 DISC2 [제작사] 품번.mp4"]
    groups = group_md5.group_files_by_pattern(files)
    assert len(groups) == 1
    (key, paths), = groups.items()
    assert key.split("|", 1)[1] == "블라블라 영화 제목 [제작사] 품번"
    assert len(paths) == 3


# [ko] unit: _process() 종단 간 — 그룹명이 실제 .md5 파일명으로 이어지는지 확인
# [en] unit: _process() end-to-end — verifies the group name flows through to the actual .md5 filename

def test_process_writes_md5_named_after_group_with_variable_segment_stripped(tmp_path):
    f1 = tmp_path / "블라블라 영화 제목.jpg"
    f2 = tmp_path / "블라블라 영화 제목 PART1.mp4"
    f3 = tmp_path / "블라블라 영화 제목 PART2.mp4"
    for f in (f1, f2, f3):
        _write(f, str(f))

    result = group_md5._process([str(f1), str(f2), str(f3)], {"bom": False, "chunk_size": 8},
                                 log_fn=lambda t: None)

    assert sorted(result.succeeded) == sorted(str(f) for f in (f1, f2, f3))
    md5_files = list(tmp_path.glob("*.md5"))
    assert len(md5_files) == 1
    assert md5_files[0].name == "블라블라 영화 제목.md5"


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
