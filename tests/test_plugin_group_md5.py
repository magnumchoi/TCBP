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


def _tmp_files(base: Path, names: list[str]) -> list[str]:
    """[ko] base 아래에 각 name으로 파일을 생성하고 문자열 경로 리스트를 반환한다."""
    paths = []
    for name in names:
        p = base / name
        _write(p)
        paths.append(str(p))
    return paths


# [ko] unit: _process() 개별 동작 (16.3.1)
# [en] unit: individual _process() behaviors (16.3.1)

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


def test_process_logs_created_message(tmp_path):
    f1 = tmp_path / "a.txt"
    _write(f1)
    logs = []
    group_md5._process([str(f1)], {"bom": False, "chunk_size": 8}, log_fn=logs.append)
    assert any("created" in line for line in logs)


def test_run_batch_session_returns_batch_result(tmp_path):
    from tcbp import BatchSession

    f1 = tmp_path / "a.txt"
    _write(f1)
    session = BatchSession(filelist=[str(f1)], output=None, taskid="t", params={"bom": False, "chunk_size": 8})
    object.__setattr__(session, "_log_fn", lambda text, slot: None)
    result = group_md5.run(session)
    assert str(f1) in result.succeeded


# [ko] unit: _extract_protected_id() 보호 식별자 판별
# [en] unit: _extract_protected_id() protected-identifier detection

@pytest.mark.parametrize("stem, expected", [
    pytest.param("ABC-1234 Movie Title", "ABC-1234", id="hyphenated_with_context_protected"),
    pytest.param("SONE100 Actress Title", "SONE-100", id="whitelisted_protected_without_hyphen"),
    pytest.param("AGEMIX100 Movie", "AGEMIX-100", id="whitelisted_6plus_chars_protected_without_hyphen"),
    pytest.param("AAA001", None, id="unregistered_prefix_treated_as_sequence_number"),
    pytest.param("No Digits Here", None, id="no_match"),
    pytest.param("Some Title Here ZZZQ009 More Text", "ZZZQ-009", id="unregistered_prefix_with_context_protected"),
    pytest.param("[STUDIO] ZZZQ009", "ZZZQ-009", id="unregistered_prefix_bracket_only_context_protected"),
    pytest.param("ZZZQ-009", None, id="unregistered_prefix_bare_hyphenated_no_context_treated_as_sequence_number"),
])
def test_extract_protected_id(stem, expected):
    assert group_md5._extract_protected_id(stem) == expected


# [ko] unit: _normalize_title() 노이즈 제거 규칙
# [en] unit: _normalize_title() noise-stripping rules

@pytest.mark.parametrize("stem, expected", [
    pytest.param("AAA001", "AAA", id="unregistered_prefix_sequence_number_digits_dropped"),
    pytest.param("SONE100 Actress Title", "SONE100 Actress Title", id="whitelisted_part_number_kept"),
    pytest.param("ABC-1234 Movie Title", "ABC-1234 Movie Title", id="hyphenated_part_number_kept"),
    pytest.param("Title PART1", "Title", id="variable_segment_removed"),
    pytest.param("Title disc_A", "Title", id="disc_underscore_segment_removed"),
    pytest.param("Some Title ZZZQ009 More Text", "Some Title ZZZQ009 More Text",
                 id="unregistered_prefix_with_context_kept"),
    pytest.param("[STUDIO] ZZZQ009", "[STUDIO] ZZZQ009", id="unregistered_prefix_bracket_only_context_kept"),
    pytest.param("ZZZQ-009", "ZZZQ", id="unregistered_prefix_bare_hyphenated_no_context_digits_dropped"),
    pytest.param("[STUDIO] MIHD009_", "[STUDIO] MIHD009", id="trailing_underscore_after_part_num_stripped"),
    pytest.param("[STUDIO] MIHD009__", "[STUDIO] MIHD009", id="multiple_trailing_underscores_after_part_num_stripped"),
    pytest.param("ZZZQ009_", "ZZZQ", id="trailing_underscore_after_bare_unwhitelisted_code_still_sequence_number"),
])
def test_normalize_title(stem, expected):
    assert group_md5._normalize_title(stem) == expected


def test_normalize_title_preserves_bracket_group_content():
    # [ko] 괄호 안쪽 내용은 노이즈 제거 규칙의 영향을 받지 않아야 한다
    # [en] Bracket-group content must be unaffected by the noise-stripping rules
    assert group_md5._normalize_title("Title DISC1 [제작사] SONE100") == "Title [제작사] SONE100"


# [ko] unit: group_files_by_pattern() 그룹핑 요구사항 사례 (요구사항 문서 10)
#      모든 케이스가 "파일명 리스트 -> {그룹명: 파일 수}" 형태로 동일하므로 로직 하나를
#      파라미터화된 데이터로 공유한다.
# [en] unit: group_files_by_pattern() grouping cases required by the spec doc (doc section 10)
#      Every case has the same "filenames -> {group name: file count}" shape, so one
#      parametrized test shares the logic across all the data.

GROUPING_CASES = [
    pytest.param(
        ["AAA001.jpg",
         "AAA002.jpg",
         "AAA003.jpg",
         "BBB001.jpg",
         "BBB002.jpg",
         "BBB003.jpg"],
        {"AAA": 3,
         "BBB": 3},
        id="numbered_sequence_grouped_and_named_without_numbers",
    ),
    pytest.param(
        ["블라블라 영화 제목.jpg",
         "블라블라 영화 제목 PART1.mp4",
         "블라블라 영화 제목 PART2.mp4"],
        {"블라블라 영화 제목": 3},
        id="part_prefixed_files_group_with_bare_title",
    ),
    pytest.param(
        ["중얼중얼중얼 만화 제목.jpg",
         "중얼중얼중얼 만화 제목 disc_A.jpg",
         "중얼중얼중얼 만화 제목 disc_B.jpg"],
        {"중얼중얼중얼 만화 제목": 3},
        id="disc_underscore_suffix_files_group_with_bare_title",
    ),
    pytest.param(
        ["블라블라 영화 제목 [제작사] SONE100.jpg",
         "블라블라 영화 제목 DISC1 [제작사] SONE100.mp4",
         "블라블라 영화 제목 DISC2 [제작사] SONE100.mp4"],
        {"블라블라 영화 제목 [제작사] SONE100": 3},
        id="variable_segment_stripped_even_with_surrounding_bracket_tokens",
    ),
    pytest.param(
        # [ko] 공통 토큰이 많아 일반 유사도만으로는 임계값을 넘길 수 있는 상황에서도,
        #      서로 다른 보호 식별자(품번)가 있으면 병합되면 안 된다 (요구사항 2).
        ["ABC-1234 Some Really Long Common Title Extra Words Here.mp4",
         "ABC-5678 Some Really Long Common Title Extra Words Here.mp4"],
        {"ABC-1234 Some Really Long Common Title Extra Words Here": 1,
         "ABC-5678 Some Really Long Common Title Extra Words Here": 1},
        id="different_part_numbers_do_not_collapse_into_one_group",
    ),
    pytest.param(
        # [ko] "SONE100"처럼 하이픈 없이 붙은 실제 품번(KNOWN_LABEL_PREFIXES 등록 레이블)은
        #      "AAA001" 같은 순번과 문자열 구조가 동일하지만, 화이트리스트 덕분에 서로 다른
        #      품번끼리는 병합되지 않아야 한다.
        ["SONE100 Some Actress Movie Title.mp4",
         "SONE101 Some Actress Movie Title.mp4"],
        {"SONE100 Some Actress Movie Title": 1,
         "SONE101 Some Actress Movie Title": 1},
        id="hyphenless_known_label_part_numbers_do_not_collapse",
    ),
    pytest.param(
        # [ko] KNOWN_LABEL_PREFIXES에 없는 접두어는 여전히 순번으로 취급되어 병합된다
        #      (화이트리스트 확장이 기존 순번 그룹핑을 깨지 않는지 확인).
        ["AAA001.jpg",
         "AAA002.jpg",
         "AAA003.jpg"],
        {"AAA": 3},
        id="hyphenless_numbered_sequence_with_unknown_prefix_still_groups",
    ),
    pytest.param(
        # [ko] MIHD009 실제 버그 재현(회귀 방지): KNOWN_LABEL_PREFIXES에 없는 레이블이라도,
        #      코드 앞뒤에 제목/태그(컨텍스트)가 있으면 보호되어 서로 다른 품번끼리
        #      병합되지 않아야 한다.
        # [en] Regression test for the real MIHD009 bug: even an unregistered label must
        #      stay protected (and not collapse into another part number) when the code
        #      appears alongside a title/tag (context) in the filename.
        ["Title Text [STUDIO] ZZZQ009.mp4",
         "Title Text [STUDIO] ZZZQ010.mp4"],
        {"Title Text [STUDIO] ZZZQ009": 1,
         "Title Text [STUDIO] ZZZQ010": 1},
        id="unregistered_prefix_with_context_do_not_collapse",
    ),
    pytest.param(
        # [ko] 품번 바로 뒤에 붙은 언더바 하나 차이로 그룹이 갈라지던 버그의 회귀 테스트.
        # [en] Regression test for the bug where a single trailing underscore right after
        #      the part number split what should have been one group into two.
        ["Title Text [STUDIO] MIHD009.jpg",
         "Title Text [STUDIO] MIHD009.mp4",
         "Title Text [STUDIO] MIHD009_.jpg"],
        {"Title Text [STUDIO] MIHD009": 3},
        id="trailing_underscore_after_part_num_does_not_split_group",
    ),
]


@pytest.mark.parametrize("filenames, expected_groups", GROUPING_CASES)
def test_group_files_by_pattern(tmp_path, filenames, expected_groups):
    files = _tmp_files(tmp_path, filenames)
    groups = group_md5.group_files_by_pattern(files)
    patterns = {key.split("|", 1)[1]: len(paths) for key, paths in groups.items()}
    assert patterns == expected_groups


# [ko] unit: _process() 종단 간 — 그룹핑 결과가 실제 .md5 파일로 이어지는지 확인
#      (group_files_by_pattern 자체가 아니라, 해시 계산+파일 쓰기까지 거친 뒤의 결과)
# [en] unit: _process() end-to-end — verifies grouping results flow through to actual
#      .md5 files (not just group_files_by_pattern, but after hashing + writing too)

END_TO_END_CASES = [
    pytest.param(
        ["ABC-1234 Movie Title.mp4",
         "ABC-1234 Movie Title.srt",
         "Completely Different Name.jpg"],
        {"ABC-1234 Movie Title.md5",
         "Completely Different Name.md5"},
        id="similar_filenames_are_grouped",
    ),
    pytest.param(
        ["블라블라 영화 제목.jpg",
         "블라블라 영화 제목 PART1.mp4",
         "블라블라 영화 제목 PART2.mp4"],
        {"블라블라 영화 제목.md5"},
        id="writes_md5_named_after_group_with_variable_segment_stripped",
    ),
]


@pytest.mark.parametrize("filenames, expected_md5_names", END_TO_END_CASES)
def test_process_creates_expected_md5_files(tmp_path, filenames, expected_md5_names):
    files = _tmp_files(tmp_path, filenames)
    result = group_md5._process(files, {"bom": False, "chunk_size": 8}, log_fn=lambda t: None)
    assert sorted(result.succeeded) == sorted(files)
    assert result.failed == []
    md5_names = {p.name for p in tmp_path.glob("*.md5")}
    assert md5_names == expected_md5_names


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
