"""
[ko] 파일 목록 로드
[en] File List Loading
"""
import fnmatch
import re
import sys
import uuid
from pathlib import Path

from core.contract import TcbpError
from core.models import FileContext, GlobalContext, ResolvedJob
from core.winapi import _get_short_path
from messages import _t


def load_file_list(filelist_path: str) -> list[Path]:
    path = Path(filelist_path)
    if not path.exists():
        raise TcbpError(f"{_t('err_filelist_not_found')}: {filelist_path}")

    files = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = Path(line)
            if not p.exists():
                print(f"{_t('warn_file_missing')}: {line}", file=sys.stderr)
                continue
            files.append(p)

    if not files:
        raise TcbpError(_t("err_no_files"))

    return files


# [ko] 폴더 입력 모드 — File Enumerator (12장)
# [en] Directory Input Mode — File Enumerator (Chapter 12)

def _walk_files_depth_first(dir_path: Path, patterns: list) -> list[Path]:
    """
    [ko]
    dir_path 한 폴더의 항목을 이름순으로 나눠, 그 폴더 자신의 대상 파일을 먼저
    담고 그 다음에 하위 폴더를 이름순으로 재귀 처리한다 — 폴더 이름이 숫자
    문자열(예: "001")이면 절대경로 문자열 전체를 정렬할 때 형제 파일명(예:
    "009.bmp")보다 앞뒤로 끼어들 수 있는 문제(12장)를 없애, "현재 폴더 자신의
    파일 → 하위 폴더들(이름순, 각각 재귀 동일 규칙)" 순서를 보장한다.

    [en]
    Splits one folder's entries by name, collecting that folder's own matching
    files first, then recursing into its subfolders in name order. This avoids
    the problem (Chapter 12) where a numeric folder name (e.g. "001") can sort
    before or after a sibling filename (e.g. "009.bmp") when the full absolute
    path string is sorted as one flat string — guaranteeing instead "this
    folder's own files → its subfolders (by name, same rule recursively)".
    """
    entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    matched: set[Path] = set()
    for pattern in patterns:
        matched.update(p for p in entries if p.is_file() and fnmatch.fnmatch(p.name, pattern))
    files = sorted(matched, key=lambda p: p.name)
    for entry in entries:
        if entry.is_dir():
            files.extend(_walk_files_depth_first(entry, patterns))
    return files


def enumerate_directory(dir_path: Path, recursive: bool, include: list) -> list[Path]:
    """
    [ko]
    폴더(dir_path)를 스캔해 대상 파일 목록을 만든다 — input_mode="directory" Job의
    File Enumerator 역할. include가 비어 있으면 모든 파일이 대상이고, recursive=true면
    하위 폴더까지 재귀 탐색한다. 정렬은 실행마다 파일시스템이 반환하는 순서에
    좌우되지 않도록 항상 이름순이며, recursive=true일 때는 "폴더 자신의 파일 먼저,
    그다음 하위 폴더를 이름순으로" 규칙(_walk_files_depth_first)을 적용해
    {index}/병렬 출력 순서가 재현 가능하면서도 디렉토리 구조를 직관적으로 따르게 한다.

    [en]
    Scans a folder (dir_path) to build the target file list — the File
    Enumerator for input_mode="directory" Jobs. If include is empty, every
    file is a candidate; if recursive=true, subfolders are searched too.
    Sorting is always by name so it never depends on whatever order the
    filesystem happens to return; when recursive=true, the "own files first,
    then subfolders by name" rule (_walk_files_depth_first) is applied so
    {index}/parallel output ordering is both reproducible and follows the
    directory structure intuitively.
    """
    patterns = include or ["*"]
    if recursive:
        files = _walk_files_depth_first(dir_path, patterns)
    else:
        found: set[Path] = set()
        for pattern in patterns:
            found.update(p for p in dir_path.glob(pattern) if p.is_file())
        files = sorted(found, key=lambda p: p.name)

    if not files:
        raise TcbpError(_t("err_no_files"))
    return files


def resolve_input_files(filelist_arg: str, job: ResolvedJob, job_name: str) -> list[Path]:
    """
    [ko]
    CLI의 FileList 인자를 job.input_mode 계약에 따라 해석한다.
    "directory": 인자가 실제 폴더여야 하며, enumerate_directory()로 파일 목록을 만든다.
    "list"(기본값): 인자가 폴더면 안 되며, 기존 load_file_list()로 목록 파일을 읽는다.
    계약과 실제 인자 종류가 어긋나면 그 자리에서 명확한 에러로 즉시 중단한다 (12장).

    [en]
    Interprets the CLI's FileList argument according to job.input_mode's
    contract. "directory": the argument must actually be a directory;
    enumerate_directory() builds the file list. "list" (the default): the
    argument must not be a directory; the existing load_file_list() reads it
    as a list file. If the contract and the actual argument type disagree,
    aborts immediately with a clear error (Chapter 12).
    """
    if job.input_mode == "directory":
        path = Path(filelist_arg).resolve()
        if not path.exists():
            raise TcbpError(f"{_t('err_directory_not_found')}: {filelist_arg}")
        if not path.is_dir():
            raise TcbpError(f"{_t('err_input_mode_expects_directory', job=job_name)}: {filelist_arg}")
        return enumerate_directory(path, job.recursive, job.include)

    if Path(filelist_arg).is_dir():
        raise TcbpError(f"{_t('err_input_mode_expects_list', job=job_name)}: {filelist_arg}")
    return load_file_list(filelist_arg)


# [ko] Placeholder 치환
# [en] Placeholder Substitution

class SafeDict(dict):
    # [ko] SafeDict: 미정의 placeholder는 원문 유지
    # [en] SafeDict: an undefined placeholder is left as-is
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# [ko] {key.label} / {key.value} — dot 표기 문법 설탕.
#      Python str.format()의 진짜 "{name.attr}" 속성 접근(getattr) 프로토콜을 쓰는 게
#      아니다 — 그러려면 context 값 자체를 .label 속성을 가진 int/str 서브클래스로 감싸야
#      하는데, bool은 파이썬에서 서브클래싱이 안 되어 preset type="bool" 파라미터를 처리할
#      수 없다. 대신 format_map()에 넘기기 전에 정규식으로 {key.label}→{key_label},
#      {key.value}→{key}로 먼저 텍스트 치환한다 — context의 실제 값 타입은 그대로 두고,
#      순수 문자열 전처리 계층 하나만 얹는 방식.
# [en] {key.label} / {key.value} — dot-notation syntactic sugar. This does NOT use
#      Python str.format()'s real "{name.attr}" attribute-access (getattr) protocol —
#      that would require wrapping context values in int/str subclasses carrying a
#      .label attribute, and bool can't be subclassed in Python, so preset
#      type="bool" params couldn't be handled that way. Instead, before handing the
#      template to format_map(), a regex rewrites {key.label}->{key_label} and
#      {key.value}->{key} as plain text — the actual context value types are left
#      untouched; this is just a text-preprocessing layer on top.
_DOT_SUGAR_RE = re.compile(r"\{(\w+)\.(label|value)\}")


def _expand_dot_sugar(template: str, context: dict) -> str:
    def repl(m: re.Match) -> str:
        key, attr = m.group(1), m.group(2)
        lookup = f"{key}_label" if attr == "label" else key
        if lookup in context:
            return "{" + lookup + "}"
        # [ko] 못 찾으면 SafeDict와 같은 "원문 유지" 결과를 내야 하는데, 그냥 "{key.attr}"를
        #      그대로 두면 뒤이은 format_map()이 이걸 진짜 속성 접근으로 다시 파싱해 버려서
        #      (context[key]가 있으면) AttributeError로 죽는다 — 그래서 중괄호를 이스케이프해
        #      format_map()에게는 순수 텍스트로만 보이게 한다.
        # [en] When not found, the result should read the same as SafeDict's "leave as
        #      literal" — but simply keeping "{key.attr}" as-is would let the following
        #      format_map() re-parse it as a real attribute access (crashing with
        #      AttributeError if context[key] exists) — so the braces are escaped to
        #      make it pure literal text to format_map().
        return "{{" + key + "." + attr + "}}"
    return _DOT_SUGAR_RE.sub(repl, template)


def substitute(template: str, context: dict) -> str:
    template = _expand_dot_sugar(template, context)
    return template.format_map(SafeDict(context))


# [ko] 임시 ID 생성 (UUID 기반, 멀티프로세싱 파일명 충돌 회피용)
# [en] Temp ID Generation (UUID-based, avoids multiprocess filename collisions)

def _gen_tmp_id() -> str:
    return "tmp_" + uuid.uuid4().hex[:12]


class ContextBuilder:
    """
    [ko]
    Job의 {placeholder} 치환 context를 만든다 — 파일 단위(build_file_context)와
    배치 전체 1회(build_global_context, pre/post용). Job/user params/task id를
    생성 시점에 고정된 불변 상태로 갖고 있으므로, 병렬 처리용 워커 스레드들이
    인스턴스 하나를 읽기 전용으로 공유해도 안전하다.

    [en]
    Builds the {placeholder} substitution context for a Job — per-file
    (build_file_context) and once for the whole batch (build_global_context,
    used by pre/post). Holds the Job/user params/task id as immutable state
    set at construction time, so a single instance can be shared read-only
    across the worker threads used for parallel processing.
    """

    def __init__(self, job: ResolvedJob, user_params: dict, task_id: str):
        self._job         = job
        self._user_params = user_params
        self._task_id      = task_id

    def build_file_context(self, file_path: Path, index: int) -> FileContext:
        file_path = file_path.resolve()
        input_dir = file_path.parent
        ctx: dict[str, str] = {
            "input":  str(file_path),
            "dir":    str(input_dir),
            "name":   file_path.name,
            "base":   file_path.stem,
            "ext":    file_path.suffix,
            "index":  str(index),
            "tool":   self._job.tool_path,
            "taskid": self._task_id,
            "itemid": _gen_tmp_id(),
            **self._job.defaults,  # [ko] job 내 비표준 키 (기본값) / [en] non-standard keys in job (defaults)
            **self._user_params,   # [ko] CLI 파라미터가 우선 / [en] CLI param takes priority
        }
        output_path = substitute(self._job.output, ctx)
        output_p = Path(output_path).resolve()
        same_dir = (output_p.parent == input_dir)

        # [ko] { msg = "..." } 메시지 치환용 — 명령 인자용 따옴표를 씌우기 전 원본(raw) 값을 보존한다.
        # [en] For { msg = "..." } message substitution — preserve the original (raw) value
        #      before it gets wrapped in quotes for use as a command argument.
        raw_ctx = dict(ctx)
        raw_ctx["output"] = output_path

        """
        [ko]
        {input}/{output}를 파일명(상대 경로)으로 줄이고 cwd=input_dir 로 실행.
        subprocess.run(cwd=unicode_dir)은 CreateProcessW lpCurrentDirectory로 전달되어
        OS가 내부적으로 Unicode 절대 경로로 해석하므로 ANSI 도구도 정상 동작한다.

        [en]
        Shorten {input}/{output} to just the filename (relative path) and run with
        cwd=input_dir. subprocess.run(cwd=unicode_dir) passes cwd via CreateProcessW's
        lpCurrentDirectory, which the OS resolves internally as a Unicode absolute
        path, so ANSI-only tools also work correctly.
        """
        ctx["input"]  = f'"{file_path.name}"'
        ctx["output"] = f'"{output_p.name}"' if same_dir else f'"{_get_short_path(str(output_p))}"'
        ctx["dir"]    = f'"{_get_short_path(str(input_dir))}"'
        ctx["name"]   = f'"{file_path.name}"'
        ctx["base"]   = f'"{file_path.stem}"'
        ctx["tool"]   = f'"{self._job.tool_path}"' if self._job.tool_path else ""

        return FileContext(ctx=ctx, raw_ctx=raw_ctx, output_path=output_path, cwd=str(input_dir))

    def build_global_context(self) -> GlobalContext:
        tool = self._job.tool_path
        raw_ctx = {
            "tool":        tool,
            "max_workers": str(self._job.max_workers),
            "taskid":      self._task_id,
            **self._job.defaults,  # [ko] job 내 비표준 키 (기본값) / [en] non-standard keys in job (defaults)
            **self._user_params,   # [ko] CLI 파라미터가 우선 / [en] CLI param takes priority
        }
        ctx = dict(raw_ctx)
        ctx["tool"] = f'"{tool}"' if tool else ""
        return GlobalContext(ctx=ctx, raw_ctx=raw_ctx)
