"""
[ko] 데이터 모델
ConfigLoader / ContextBuilder / CommandExecutor / JobRunner가 공유하는
데이터클래스. dict/tuple을 느슨하게 주고받는 대신 타입을 명시해두는 것이
클래스를 분리할 수 있게 하는 전제 조건이며, 향후 플러그인 코드가 기댈 수
있는 안정적인 계약이 된다.

[en] DATA MODELS
Dataclasses shared across ConfigLoader / ContextBuilder / CommandExecutor /
JobRunner. Keeping these as explicit types (rather than loose dict/tuple
passing) is what lets those classes be split apart in the first place, and
gives future plugin code a stable contract to build against.
"""
import dataclasses
from dataclasses import dataclass
from typing import Any, Callable

from core.contract import strict_dataclass


@dataclass
class PresetOption:
    label: str
    value: Any = None


@dataclass
class JobParam:
    key: str
    desc: str = ""
    type: str = ""
    default: Any = None
    preset: list[PresetOption] = dataclasses.field(default_factory=list)


@dataclass
class ResolvedJob:
    desc:           str
    tool_name:      str
    tool_path:      str
    on_error:       str
    parallel:       bool
    max_workers:    int
    output:         str
    pre:            list
    commands:       list
    post:           list
    log:            bool
    log_file:       str
    pause:          bool
    tools:          dict[str, str]
    stderr_quiet:   bool
    params:         list[JobParam]
    defaults:       dict[str, str]
    notes_per_file: int
    uses_output:    bool
    plugin_name:            str  = ""     # [ko] plugin = "..." (6장) — tool과 상호 배타적 / [en] plugin = "..." (Chapter 6) — mutually exclusive with tool
    allow_output_overwrite: bool = False  # [ko] output이 의도적으로 input을 덮어써도 되는 Job (범용 opt-out) / [en] a Job whose output intentionally overwrites input (general opt-out)
    input_mode: str       = "list"        # [ko] "list" | "directory" — FileList 인자의 계약(12장) / [en] "list" | "directory" — the contract for the FileList argument (Chapter 12)
    recursive:  bool      = False         # [ko] input_mode="directory"일 때 하위 폴더까지 재귀 탐색 / [en] when input_mode="directory", search subfolders recursively
    include:    list      = dataclasses.field(default_factory=list)  # [ko] input_mode="directory"일 때 적용할 글롭 패턴 목록 (비어있으면 전체) / [en] glob patterns applied when input_mode="directory" (empty means everything)


@dataclass
class FileContext:
    ctx:         dict
    raw_ctx:     dict
    output_path: str
    cwd:         str


@dataclass
class GlobalContext:
    ctx:     dict
    raw_ctx: dict


@strict_dataclass(frozen=True)
class ExecResult:
    """
    [ko]
    CLI Job과 FileSession 플러그인 Job이 공유하는 파일 1개 처리 결과.
    이제 plugin↔TCBP 경계를 넘는 값이므로(3.4), 다른 내부 전용 dataclass와
    달리 strict_dataclass로 검증한다.

    [en]
    The single-file processing result shared by CLI Jobs and FileSession
    plugin Jobs. Since this value now crosses the plugin↔TCBP boundary (3.4),
    unlike other internal-only dataclasses, it is validated via
    strict_dataclass.
    """
    success: bool
    message: str = ""


@strict_dataclass(frozen=True)
class BatchResult:
    """
    [ko]
    BatchSession 플러그인의 run() 반환값 (3.4/8.3.4). succeeded/failed는
    session.filelist 전체를 다 채우지 않아도 된다 — TCBP는 강제하지 않는다.

    [en]
    The return value of a BatchSession plugin's run() (3.4/8.3.4).
    succeeded/failed don't need to fully cover session.filelist — TCBP
    doesn't enforce that.
    """
    succeeded: list = dataclasses.field(default_factory=list)
    failed:    list = dataclasses.field(default_factory=list)


@strict_dataclass(frozen=True)
class FileSession:
    """
    [ko]
    FileSession 플러그인의 run(session) 인자 (3.4~3.7, 8.2). log() 호출을
    제외하고 읽기 전용이다. _log_fn은 생성자 주입 필드다 — TCBP가 세션을
    생성할 때 인스턴스별 콜백을 함께 넘긴다(11장; frozen dataclass이므로
    생성 이후에는 object.__setattr__ 없이 재할당할 수 없다).

    [en]
    The argument to a FileSession plugin's run(session) (3.4-3.7, 8.2).
    Read-only aside from calling log(). _log_fn is a constructor-injected
    field — TCBP passes the per-instance callback in when constructing the
    session (Chapter 11; being a frozen dataclass, it can't be reassigned
    after construction without object.__setattr__).
    """
    input:  str
    output: str
    itemid: int   # [ko] 파일당 1-based 순번. ctx["itemid"](임시파일명용 랜덤 문자열)와는 무관 — 혼동 금지. / [en] 1-based per-file sequence number. Unrelated to ctx["itemid"] (a random string for temp filenames) — don't confuse the two.
    taskid: str
    params: dict

    _log_fn: Callable[[str, int], None] | None = dataclasses.field(default=None, repr=False, compare=False)

    def log(self, text: str, slot: int = 0) -> None:
        if self._log_fn is not None:
            self._log_fn(text, slot)


@strict_dataclass(frozen=True)
class BatchSession:
    """
    [ko]
    BatchSession 플러그인의 run(session) 인자 (8.3). filelist는 TCBP가 이미
    읽고 존재 확인까지 마친 절대경로 문자열 리스트다 (8.3.1).

    [en]
    The argument to a BatchSession plugin's run(session) (8.3). filelist is a
    list of absolute-path strings TCBP has already read and confirmed exist
    (8.3.1).
    """
    filelist: list
    output:   str | None
    taskid:   str
    params:   dict

    _log_fn: Callable[[str, int], None] | None = dataclasses.field(default=None, repr=False, compare=False)

    def log(self, text: str, slot: int = 0) -> None:
        if self._log_fn is not None:
            self._log_fn(text, slot)
