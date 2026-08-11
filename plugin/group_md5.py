#!/usr/bin/env python3
"""
[ko]
[플러그인 개요]
이름: group_md5.py
버전: v1.1
타입: TCBP BatchSession 플러그인
목적: 파일들을 이름 유사도로 그룹핑해 그룹별 MD5 목록(.md5) 파일 생성
설명: TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 실행할 수 있다.
기타:
- 같은 폴더 내 파일명을 토큰 단위로 분해해 가중치 기반 유사도를 계산하고,
  유사한 파일끼리 그룹화해 그룹별로 .md5 파일 하나를 생성한다.
- 진행률은 session.log()를 거치지 않고 stdout에 \r로 숫자 %만 직접 출력한다.
  (BatchSession은 병렬 처리가 없어 안전. rich 등 ANSI 커서 이동 라이브러리는 사용하지 않음)
- 그룹 처리가 끝난 뒤의 최종 결과("생성됨: xxx.md5 (N개 파일)")만 log()로 남긴다.

독립실행시:
    python group_md5.py <list_file> [bom=true] [chunk_size=64]

[en]
[Plugin Overview]
Name: group_md5.py
Version: v1.1
Type: TCBP BatchSession plugin
Purpose: Group files by filename similarity and generate a grouped MD5 (.md5) list file per group
Description: Can be called via run(session) through TCBP, or run standalone (without tcbp).
Notes:
- Breaks file names within the same folder into tokens, computes a weighted similarity score,
  groups similar files together, and writes one .md5 file per group.
- Progress is printed directly to stdout as a numeric % using \r, bypassing session.log()
  (safe because BatchSession never runs in parallel; ANSI-cursor-based libraries such as rich are
  intentionally not used).
- Only the final result per group (e.g. "created: xxx.md5 (N files)") is reported via log().

Standalone execution:
    python group_md5.py <list_file> [bom=true] [chunk_size=64]

"""
import sys
import os
import re
import hashlib
import time
from pathlib import Path
from collections import defaultdict, Counter
from types import SimpleNamespace
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, BatchSession, BatchResult, parse_params, _to_bool, _truncate_filename

TRUNCATE_LENGTH = 60
PROGRESS_UPDATE_INTERVAL = 1.5  # [ko] 진행률 콜백 최소 호출 간격(초) — 오리지널 refresh_per_second=0.67과 동일 / [en] minimum interval (seconds) between progress callbacks — matches the original refresh_per_second=0.67

# [ko] 가변 식별자(part/disc/cd/vol/ep/track + 번호)의 접두어 데이터.
#      정규식은 코드에서 동적으로 생성되므로, 새 접두어는 이 목록에만 추가하면 된다.
# [en] Prefix data for variable identifiers (part/disc/cd/vol/ep/track + number).
#      The regex is generated dynamically from this list, so adding a new prefix
#      only requires editing this set.
VARIABLE_PREFIXES = {"DISC", "PART", "CD", "VOL", "EP", "TRACK"}
VARIABLE_TOKEN = "<VARIABLE>"
_VARIABLE_TOKEN_WEIGHT = 0.1  # [ko] 가변/숫자 토큰은 그룹 식별에 거의 기여하지 않도록 낮은 가중치 부여 / [en] low weight so variable/numeric tokens barely influence grouping

# [ko] 그룹핑/해시 핵심 로직 (GroupMD5.py에서 벤더링)
# [en] Core grouping/hashing logic (vendored from GroupMD5.py)

def get_truncated_filename_for_display(file_path: str, max_length: int = TRUNCATE_LENGTH) -> str:
    """
    [ko]
    tcbp._truncate_filename()에 위임한다 — len() 기반(코드포인트 개수)이 아니라
    전각 문자(한글/한자/가나 등)를 폭 2로 계산하는 화면 표시 폭 기준으로 자르므로,
    한글/일본어 파일명도 콘솔 폭을 넘기지 않는다.

    [en]
    Delegates to tcbp._truncate_filename() — truncates by on-screen display
    width (treating fullwidth characters like Hangul/Hanja/Kana as width 2)
    rather than len() (code point count), so Korean/Japanese filenames don't
    overflow the console width either.
    """
    return _truncate_filename(Path(file_path).name, max_length)


def detect_encoding(file_path: Path) -> str:
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read(3)
            return "utf-8-sig" if raw_data.startswith(b"\xef\xbb\xbf") else "utf-8"
    except Exception:
        return "utf-8"


def calculate_md5(file_path: str, chunk_size: int,
                   progress_cb: Callable[[int, int], None] | None = None) -> str:
    """
    [ko]
    progress_cb는 청크를 읽을 때마다 호출하는 게 아니라 최대 PROGRESS_UPDATE_INTERVAL초에
    한 번만 호출한다(오리지널 GroupMD5.py의 refresh_per_second=0.67, 즉 약 1.5초
    간격과 동일) — 작은 chunk_size로 큰 파일을 처리할 때 매 청크마다 print()가
    호출되어 콘솔 출력이 병목이 되는 것을 방지한다. 단, 마지막 청크(완료 시점)는
    간격과 무관하게 항상 호출해 100%가 누락되지 않게 한다.

    [en]
    progress_cb is called at most once every PROGRESS_UPDATE_INTERVAL seconds,
    not on every chunk read (matches the original GroupMD5.py's
    refresh_per_second=0.67, i.e. about a 1.5-second interval) — this prevents
    print() from becoming a bottleneck when a small chunk_size is used against
    a large file. The final chunk (completion) always calls it regardless of
    the interval, so 100% is never skipped.
    """
    hash_md5 = hashlib.md5()
    total = os.path.getsize(file_path)
    done = 0
    last_update = 0.0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hash_md5.update(chunk)
            done += len(chunk)
            if progress_cb:
                now = time.monotonic()
                if done >= total or now - last_update >= PROGRESS_UPDATE_INTERVAL:
                    progress_cb(done, total)
                    last_update = now
    return hash_md5.hexdigest()


def _get_part_num_from_input_name(input_name: str) -> SimpleNamespace:
    match = re.search(r"([A-Za-z]{2,5})-?([0-9]{3,4})", input_name)
    if not match:
        return SimpleNamespace(pn_full="N/A", pn_letters="N/A", pn_numbers="N/A")
    letters, numbers = match.groups()
    letters = letters.upper()
    return SimpleNamespace(pn_full=f"{letters}-{numbers}", pn_letters=letters, pn_numbers=numbers)


def _split_alpha_digit_boundary(token: str) -> list[str]:
    """
    [ko]
    문자↔숫자 경계에서만 분리한다("aaa001" -> ["aaa","001"], "part12" -> ["part","12"]).
    구분 문자(하이픈 등)가 letter/digit 사이에 끼어 있으면 분리하지 않는다
    ("ABC-1234"는 그대로 유지되어 FC2-PPV/품번 패턴 가중치 로직이 깨지지 않는다).

    [en]
    Splits only at letter<->digit boundaries ("aaa001" -> ["aaa","001"],
    "part12" -> ["part","12"]). A non-alnum character (e.g. a hyphen) sitting
    between the letter and digit prevents the split ("ABC-1234" stays intact so
    the FC2-PPV/part-number weighting logic downstream keeps working).
    """
    if not token:
        return []

    def kind(ch: str) -> str:
        if ch.isdigit():
            return "digit"
        if ch.isalpha():
            return "alpha"
        return "other"

    parts: list[str] = []
    cur = [token[0]]
    prev_kind = kind(token[0])
    for ch in token[1:]:
        cur_kind = kind(ch)
        if {prev_kind, cur_kind} == {"alpha", "digit"}:
            parts.append("".join(cur))
            cur = [ch]
        else:
            cur.append(ch)
        prev_kind = cur_kind
    parts.append("".join(cur))
    return parts


def _tokenize_stem(stem: str) -> list[str]:
    """
    [ko]
    파일명 stem을 토큰으로 분해한다. 구분자: 공백/콤마/언더바.
    (), [], {} 묶음은 하나의 토큰으로 취급. 하이픈(-)은 분리하지 않는다.
    묶음 밖의 연속 문자열은 문자/숫자 경계에서 추가로 분리된다(_split_alpha_digit_boundary).

    [en]
    Breaks a filename stem into tokens. Delimiters: whitespace/comma/underscore.
    A (), [], or {} group is treated as a single token. Hyphens (-) are not split.
    Runs outside of a bracket group are further split at letter/digit boundaries
    (_split_alpha_digit_boundary).
    """
    s = stem
    tokens: list[str] = []
    i = 0
    N = len(s)
    buf: list[str] = []

    def flush_buf():
        if buf:
            token = "".join(buf).strip()
            if token:
                tokens.extend(_split_alpha_digit_boundary(token))
            buf.clear()

    pairs = {"(": ")", "[": "]", "{": "}"}
    seps = {",", "_"}
    while i < N:
        ch = s[i]
        if ch.isspace():
            flush_buf()
            while i < N and s[i].isspace():
                i += 1
            continue
        if ch in seps:
            flush_buf()
            i += 1
            continue
        if ch in pairs:
            flush_buf()
            close = pairs[ch]
            j = i + 1
            depth = 1
            while j < N and depth > 0:
                if s[j] == ch:
                    depth += 1
                elif s[j] == close:
                    depth -= 1
                j += 1
            tokens.append(s[i:j].strip())
            i = j
            continue
        buf.append(ch)
        i += 1
    flush_buf()
    return tokens


def _find_variable_spans(tokens: list[str]) -> list[tuple[int, int]]:
    """
    [ko]
    토큰 목록에서 가변 식별자(Variable Segment) 구간을 찾아 (시작, 끝) 인덱스 쌍으로
    반환한다. VARIABLE_PREFIXES 접두어 + 짧은 영숫자 접미어의 2토큰 시퀀스
    (예: ["DISC","1"], ["PART","01"], ["DISC","A"])와, 분리되지 않고 붙어 있는
    단일 토큰(예: "DISC1") 두 형태를 모두 인식한다. 정규식은 VARIABLE_PREFIXES에서
    매 호출마다 동적으로 생성되므로, 접두어 추가는 그 목록만 수정하면 된다.

    [en]
    Scans the token list for Variable Segments and returns them as (start, end)
    index pairs. Recognizes both a 2-token sequence of a VARIABLE_PREFIXES word
    followed by a short alphanumeric suffix (e.g. ["DISC","1"], ["PART","01"],
    ["DISC","A"]) and a single fused token (e.g. "DISC1"). The regex is built
    dynamically from VARIABLE_PREFIXES on each call, so adding a prefix only
    requires editing that set.
    """
    prefix_alt = "|".join(re.escape(p) for p in sorted(VARIABLE_PREFIXES, key=len, reverse=True))
    prefix_re = re.compile(rf"^(?:{prefix_alt})$", re.IGNORECASE)
    fused_re = re.compile(rf"^(?:{prefix_alt})[-_]?[A-Za-z0-9]{{1,4}}$", re.IGNORECASE)
    suffix_re = re.compile(r"^[A-Za-z0-9]{1,4}$")

    spans: list[tuple[int, int]] = []
    i = 0
    n = len(tokens)
    while i < n:
        if i + 1 < n and prefix_re.match(tokens[i]) and suffix_re.match(tokens[i + 1]):
            spans.append((i, i + 2))
            i += 2
            continue
        if fused_re.match(tokens[i]):
            spans.append((i, i + 1))
            i += 1
            continue
        i += 1
    return spans


def _variable_segment_indices(tokens: list[str]) -> set[int]:
    """[ko] 가변 구간에 속한 토큰 인덱스 집합. [en] Set of token indices belonging to Variable Segments."""
    indices: set[int] = set()
    for start, end in _find_variable_spans(tokens):
        indices.update(range(start, end))
    return indices


def _normalize_variable_tokens(tokens: list[str]) -> list[str]:
    """
    [ko] 가변 구간을 단일 VARIABLE_TOKEN으로 치환한 토큰 시퀀스를 반환한다
         (유사도 계산은 원본이 아닌 이 정규화된 시퀀스를 기준으로 수행한다).
    [en] Returns the token sequence with Variable Segments collapsed into a
         single VARIABLE_TOKEN (similarity is computed against this normalized
         sequence, not the original tokens).
    """
    spans = _find_variable_spans(tokens)
    span_start_to_end = dict(spans)
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        if i in span_start_to_end:
            out.append(VARIABLE_TOKEN)
            i = span_start_to_end[i]
        else:
            out.append(tokens[i])
            i += 1
    return out


def _calculate_weighted_similarity(tokens1: list[str], tokens2: list[str],
                                    similarity_threshold: float = 0.7) -> tuple[bool, float]:
    """
    [ko] 가중치 기반 토큰 유사도 계산.
    [en] Compute weighted token similarity.
    """
    if not tokens1 or not tokens2:
        return False, 0.0

    def get_token_weight(token: str) -> float:
        # [ko] VARIABLE_TOKEN(가변 구간)과 순수 숫자 토큰(예: 연번 "001")은 파일 식별에
        #      거의 기여하지 않는 가변 정보이므로, 유사도 판정이 이들에 좌우되지 않도록
        #      고정된 낮은 가중치를 준다 (요구사항 3: 공통 토큰 비율을 적극 활용).
        # [en] VARIABLE_TOKEN and pure-numeric tokens (e.g. a sequence number "001")
        #      carry little identifying information, so they get a fixed low weight
        #      so the match ratio is driven by the meaningful common tokens instead.
        if token == VARIABLE_TOKEN or token.isdigit():
            return _VARIABLE_TOKEN_WEIGHT
        base_weight = len(token) ** 0.7
        if token.startswith("FC2-PPV-"):
            return base_weight * 2.0
        part_info = _get_part_num_from_input_name(token)
        if part_info.pn_full != "N/A":
            return base_weight * 2.0
        if token.startswith(("[", "(", "\u3010")):
            return base_weight * 1.5
        if len(token) > 20:
            return base_weight * 1.8
        if len(token) <= 3:
            return base_weight * 0.5
        return base_weight

    weights1 = [get_token_weight(t) for t in tokens1]
    weights2 = [get_token_weight(t) for t in tokens2]
    max_total_weight = max(sum(weights1), sum(weights2))
    if max_total_weight == 0:
        return False, 0.0

    matched_weight = 0.0
    used_indices2: set[int] = set()
    token_pairs1 = sorted(zip(tokens1, weights1, range(len(tokens1))), key=lambda x: x[1], reverse=True)

    for token1, weight1, _idx1 in token_pairs1:
        best_match_idx = -1
        best_weight = 0.0
        for i, token2 in enumerate(tokens2):
            if i not in used_indices2 and token1 == token2 and weights2[i] > best_weight:
                best_weight = weights2[i]
                best_match_idx = i
        if best_match_idx >= 0:
            matched_weight += min(weight1, weights2[best_match_idx])
            used_indices2.add(best_match_idx)

    similarity_score = matched_weight / max_total_weight
    return similarity_score >= similarity_threshold, similarity_score


def _remove_tokens_by_index(orig: str, tokens: list, remove_idx: set) -> str:
    """
    [ko] 원본 파일명에서 지정된 토큰 인덱스만 제거 (공백/괄호 등 원형 보존).
    [en] Remove only the specified token indices from the original filename (preserving whitespace/brackets, etc.).
    """
    s = orig
    N = len(s)
    pairs = {"(": ")", "[": "]", "{": "}"}
    seps = {",", "_"}
    i = 0
    t_idx = 0
    out: list[str] = []
    buf: list[str] = []

    def flush():
        nonlocal t_idx
        if buf:
            # [ko] _tokenize_stem()과 동일한 문자/숫자 경계 분리를 적용해 인덱스를 맞춘다
            # [en] apply the same letter/digit-boundary split as _tokenize_stem() so indices line up
            for part in _split_alpha_digit_boundary("".join(buf)):
                if t_idx not in remove_idx:
                    out.append(part)
                t_idx += 1
            buf.clear()

    while i < N:
        ch = s[i]
        if ch.isspace():
            flush()
            out.append(ch)
            i += 1
            continue
        if ch in seps:
            flush()
            out.append(ch)
            i += 1
            continue
        if ch in pairs:
            flush()
            close = pairs[ch]
            j = i + 1
            depth = 1
            while j < N and depth > 0:
                if s[j] == ch:
                    depth += 1
                elif s[j] == close:
                    depth -= 1
                j += 1
            token = s[i:j]
            if t_idx not in remove_idx:
                out.extend(token)
            t_idx += 1
            i = j
            continue
        buf.append(ch)
        i += 1
    flush()
    return "".join(out)


def group_files_by_pattern(file_paths: list[str]) -> dict[str, list[str]]:
    """
    [ko] 파일들을 폴더별 + 토큰 유사도 기반으로 그룹화한다.
    [en] Group files by folder plus token-similarity.
    """
    groups: dict[str, list[str]] = {}
    path_groups: dict[str, list[str]] = defaultdict(list)
    for file_path in file_paths:
        path_groups[str(Path(file_path).parent)].append(file_path)

    for dir_path, files in path_groups.items():
        if not files:
            continue
        entries = []
        for fp in files:
            stem = Path(fp).stem
            raw_tokens = _tokenize_stem(stem)
            entries.append({
                "path": fp,
                "stem": stem,
                "tokens": raw_tokens,
                # [ko] 유사도 계산은 정규화된(가변 구간이 VARIABLE_TOKEN으로 치환된) 토큰
                #      시퀀스를 기준으로 한다 (요구사항 7)
                # [en] similarity is computed against the normalized token sequence
                #      (Variable Segments collapsed to VARIABLE_TOKEN) (requirement 7)
                "norm_tokens": _normalize_variable_tokens(raw_tokens),
            })
        N = len(entries)
        assigned: set[int] = set()
        dir_groups: dict[str, list[str]] = {}

        for i in range(N):
            if i in assigned:
                continue
            group = [i]
            ref_tokens = entries[i]["norm_tokens"]
            for j in range(i + 1, N):
                if j in assigned:
                    continue
                is_similar, _score = _calculate_weighted_similarity(ref_tokens, entries[j]["norm_tokens"])
                if is_similar:
                    group.append(j)

            group_idxs = sorted(group)
            group_tokens = [entries[k]["tokens"] for k in group_idxs]
            flat_tokens = [t for toks in group_tokens for t in toks]
            token_counter = Counter(flat_tokens)
            must_keep = {tok for tok, cnt in token_counter.items() if cnt == len(group_tokens)}
            rep_stem = entries[group_idxs[0]]["stem"]
            rep_tokens = entries[group_idxs[0]]["tokens"]
            # [ko] 가변 구간(Variable Segment)은 모든 멤버에 공통으로 존재하더라도
            #      그룹명에서 항상 제거한다 (요구사항 8)
            # [en] Variable Segments are always stripped from the group name even if
            #      common to every member (requirement 8)
            remove_idx = {i for i, t in enumerate(rep_tokens) if t not in must_keep} | _variable_segment_indices(rep_tokens)
            group_name = _remove_tokens_by_index(rep_stem, rep_tokens, remove_idx)
            group_name = re.sub(r"\s+", " ", group_name).strip() or rep_stem
            dir_groups.setdefault(group_name, [])
            for k in group_idxs:
                dir_groups[group_name].append(entries[k]["path"])
                assigned.add(k)

        for pattern, paths in dir_groups.items():
            groups[f"{dir_path}|{pattern}"] = paths

    return groups


def _sanitize_md5_filename(filename: str, base_dir: Path) -> str:
    """
    [ko] Windows에서 유효하도록 파일명을 정리하고, 경로 길이를 안전하게 제한한다.
    [en] Sanitize the filename to be valid on Windows and safely cap the total path length.
    """
    name, ext = os.path.splitext(filename)
    invalid = r'<>:"/\|?*'
    trans = str.maketrans({ch: " " for ch in invalid})
    safe_name = name.translate(trans)
    safe_name = "".join(ch for ch in safe_name if ord(ch) >= 32)
    safe_name = re.sub(r"\s+", " ", safe_name).strip().rstrip(".")

    candidate = f"{safe_name}{ext}"
    full_path = base_dir / candidate
    max_total = 240
    try:
        total_len = len(str(full_path))
    except Exception:
        total_len = 9999
    if total_len > max_total:
        digest = hashlib.md5(name.encode("utf-8", errors="ignore")).hexdigest()[:8]
        allowance = max(16, max_total - (len(str(base_dir)) + 1 + len(ext) + 1 + len(digest)))
        candidate = f"{safe_name[:allowance]}_{digest}{ext}"
    return candidate


def write_group_md5_file(dir_path: str, pattern: str, group_md5_data: list[tuple[str, str]],
                          use_bom: bool, log_fn: Callable[[str], None]) -> None:
    """
    [ko] 그룹의 MD5 목록을 .md5 파일로 쓴다. 실패 시 예외를 던진다(호출부가 집계).
    [en] Write the group's MD5 list to a .md5 file. Raises on failure (the caller tallies it).
    """
    md5_filename = f"{pattern}.md5" if pattern != "misc" else "files.md5"
    md5_filename = _sanitize_md5_filename(md5_filename, base_dir=Path(dir_path))
    md5_file_path = Path(dir_path) / md5_filename
    md5_file_path.parent.mkdir(parents=True, exist_ok=True)

    md5_content = [f"{md5_hash} *{Path(fp).name}" for md5_hash, fp in group_md5_data]
    encoding = "utf-8-sig" if use_bom else "utf-8"
    md5_file_path.write_text("\n".join(md5_content) + "\n", encoding=encoding)

    display_name = get_truncated_filename_for_display(str(md5_file_path))
    log_fn(f"created: {display_name} ({len(group_md5_data)} files)")


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(filelist: list[str], params: dict, log_fn: Callable[[str], None]) -> BatchResult:
    chunk_size = int(params.get("chunk_size", 64)) * 1024 * 1024
    use_bom = _to_bool(str(params.get("bom", "false")))
    succeeded: list[str] = []
    failed: list[str] = []

    try:
        log_fn(f"Num of files : {len(filelist)}")

        valid = [f for f in filelist if Path(f).exists()]
        valid_set = set(valid)
        missing = [f for f in filelist if f not in valid_set]
        for fp in missing:
            log_fn(f"skipped (no files): {get_truncated_filename_for_display(fp)}")
        failed.extend(missing)

        groups = group_files_by_pattern(valid)
        log_fn(f"Num of groups: {len(groups)}")
        total = len(valid)
        done = 0

        for group_key, group_files in groups.items():
            dir_path, pattern = group_key.split("|", 1)
            group_md5_data: list[tuple[str, str]] = []
            group_failed: list[str] = []

            for fp in group_files:
                done += 1
                i, n, name = done, total, Path(fp).name
                # [ko] 진행률 줄에는 줄여서 표시하고, 실패 로그에는 원본 파일명을 그대로 남긴다
                #      (긴 파일명이 콘솔 폭을 넘겨 \r 진행률 줄이 깨지는 것을 방지 — 오리지널
                #      GroupMD5.py의 get_truncated_filename_for_display()와 동일한 방식).
                # [en] The progress line shows a truncated name; the failure log keeps the
                #      original filename as-is (prevents a long filename from wrapping the
                #      console and breaking the \r progress line — same approach as the
                #      original GroupMD5.py's get_truncated_filename_for_display()).
                display_name = get_truncated_filename_for_display(fp)
                try:
                    h = calculate_md5(
                        fp, chunk_size,
                        progress_cb=lambda b, t, i=i, n=n, name=display_name:
                            print(f"\r[{i}/{n}] {name:<{TRUNCATE_LENGTH}} {int(b * 100 / max(t, 1)):3d}%", end="", flush=True),
                    )
                    group_md5_data.append((h, fp))
                except Exception as e:
                    group_failed.append(fp)
                    log_fn(f"failed: {name} — {e}")
                finally:
                    # [ko] 파일별 진행률 \r 줄을 여기서 확정(개행)한다 — 그룹 루프가 끝난 뒤
                    #      한 번만 개행하면, 같은 그룹 내 다음 파일의 \r 진행률이 이전 파일의
                    #      줄을 그대로 덮어써 화면에서 사라져 버린다(예: 2개 파일 그룹에서
                    #      마지막 파일의 진행률만 보이고 첫 파일은 안 보이는 문제).
                    # [en] Finalize (newline) this file's \r progress line right here — if the
                    #      newline only happened once after the whole group loop, the next
                    #      file's \r progress in the same group would overwrite the previous
                    #      file's line in place, making it disappear from the screen (e.g., in
                    #      a 2-file group, only the last file's progress would ever be visible).
                    print()

            if group_md5_data:
                try:
                    write_group_md5_file(dir_path, pattern, group_md5_data, use_bom, log_fn)
                    succeeded.extend(fp for _, fp in group_md5_data)
                except Exception as e:
                    # [ko] 그룹 전체가 결국 아무 출력도 만들지 못했으므로 succeeded가 아니라 failed
                    # [en] The whole group ended up producing no output at all, so it goes to failed, not succeeded
                    group_failed.extend(fp for _, fp in group_md5_data)
                    log_fn(f"failed: entire {pattern}.md5 group ({len(group_md5_data)} files) — {e}")

            failed.extend(group_failed)
    finally:
        print()  # [ko] 중간에 죽거나 개행 없이 리턴하는 경우까지 포함해 개행을 보장 (10.5) / [en] guarantee a trailing newline even if it dies mid-way or returns without one

    return BatchResult(succeeded=succeeded, failed=failed)


@plugin(
    name="group_md5",
    contract_version="1.0",
    version="1.1",
    author="Magnum Choi",
    session_type="batch",
    requirements=[],
    notes_per_file=0,
)
def run(session: BatchSession) -> BatchResult:  # [ko] TCBP 진입점 / [en] TCBP entry point
    """
    [ko]
    run()의 예외는 catastrophic 신호로 예약되어 있다 (3.4/8.3.4) —
    PluginJobExecutor.run_batch()가 이를 filelist 전체 실패로 합성한다.
    여기서 삼키지 않는다 (_process 내부 try/finally는 개행 보장 전용).

    [en]
    An exception from run() is reserved as a catastrophic signal (3.4/8.3.4) —
    PluginJobExecutor.run_batch() synthesizes it into a full filelist failure.
    It is not swallowed here (the try/finally inside _process exists only to
    guarantee a trailing newline).
    """
    return _process(session.filelist, session.params, log_fn=lambda text: session.log(text, slot=0))


if __name__ == "__main__":  # [ko] 단독 CLI 진입점 (4.5) — 리스트 파일을 직접 읽는다 / [en] standalone CLI entry point (4.5) — reads the list file directly
    if len(sys.argv) < 2:
        print("Usage: python group_md5.py <list_file> [bom=true] [chunk_size=64]")
        raise SystemExit(1)
    list_path = Path(sys.argv[1])
    encoding = detect_encoding(list_path)
    lines = [line.strip() for line in list_path.read_text(encoding=encoding).splitlines() if line.strip()]
    base_dir = list_path.parent.resolve()
    files = [str(Path(line).resolve()) if Path(line).is_absolute() else str((base_dir / line).resolve())
             for line in lines]

    cli_params = parse_params(sys.argv[2:])
    result = _process(files, cli_params, log_fn=print)
    print(f"succeeded={len(result.succeeded)} failed={len(result.failed)}")
    raise SystemExit(0 if not result.failed else 1)
