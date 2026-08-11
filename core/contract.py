"""
[ko]
strict_dataclass: pydantic이 있으면 pydantic.dataclasses.dataclass를 그대로
쓰고, 없으면 표준 dataclasses.dataclass + 최소 isinstance 기반 __post_init__
검증으로 폴백

[en]
strict_dataclass: uses pydantic.dataclasses.dataclass as-is if pydantic is
available, otherwise falls back to a standard dataclasses.dataclass plus
minimal isinstance-based validation in __post_init__ (plugin expansion plan
3.8.1).
"""
import dataclasses
import sys
import typing
from typing import Any, Callable, Literal, TypeVar

from messages import _t


class TcbpError(Exception):
    """[ko] tcbp.py 내부 함수가 fail-fast로 실행을 중단할 때 던지는 도메인 예외 (10장). / [en] Domain exception raised when a tcbp.py internal function fail-fasts (Chapter 10)."""


# [ko]
# 플러그인 계약(FileSession/BatchSession/PluginInfo/@plugin의 형태) 자체의 버전.
# "MAJOR.MINOR" 문자열. TCBP 제품 버전(pyproject.toml의 [project].version)과는
# 별개다 — 계약이 실제로 안 바뀐 TCBP 릴리스가 훨씬 많으므로 독립적으로 관리한다.
# MAJOR: 기존 플러그인을 깨뜨리는 변경(필드 제거/타입 변경 등) 시에만 올린다.
# MINOR: 하위 호환되는 추가(새 선택 필드 등) 시 올린다.
# 플러그인은 @plugin(contract_version=...)으로 자신이 작성 시점에 대상으로 삼은
# 계약 버전을 선언하고, load_plugin()이 이를 검사한다 (core/config.py).
#
# [en]
# The version of the plugin *contract* itself (the shape of
# FileSession/BatchSession/PluginInfo/@plugin) — a "MAJOR.MINOR" string.
# Independent of TCBP's own product version (pyproject.toml's
# [project].version), since far more TCBP releases leave the contract
# untouched than change it.
# MAJOR: bumped only for a change that breaks existing plugins (a removed
#        field, a changed type, etc.).
# MINOR: bumped for a backward-compatible addition (a new optional field, etc.).
# Plugins declare which contract version they were written against via
# @plugin(contract_version=...), and load_plugin() checks it (core/config.py).
CONTRACT_VERSION = "1.0"


try:
    from pydantic.dataclasses import dataclass as strict_dataclass
except ImportError:
    def _loose_isinstance(value: Any, hint: Any) -> bool:
        origin = typing.get_origin(hint)
        if origin is Literal:
            return value in typing.get_args(hint)
        if origin is not None:
            return isinstance(value, origin)
        return not isinstance(hint, type) or isinstance(value, hint)

    def strict_dataclass(*, frozen: bool = True):
        """
        [ko] pydantic 미설치 시 폴백
        [en] Fallback for when pydantic isn't installed
        """
        def _wrap(cls):
            hints = typing.get_type_hints(cls)
            user_post_init = cls.__dict__.get("__post_init__")

            def __post_init__(self):
                for f in dataclasses.fields(self):
                    v, hint = getattr(self, f.name), hints.get(f.name)
                    if hint is not None and not _loose_isinstance(v, hint):
                        raise TypeError(f"{cls.__name__}.{f.name}: expected {hint}, got {type(v).__name__}")
                if user_post_init:
                    user_post_init(self)

            cls.__post_init__ = __post_init__
            return dataclasses.dataclass(frozen=frozen)(cls)
        return _wrap

    print(_t("info_pydantic_missing"), file=sys.stderr)
    print(_t("info_pydantic_fallback"), file=sys.stderr)


@strict_dataclass(frozen=True)
class PluginInfo:
    name: str
    contract_version: str  # [ko] 플러그인이 작성 시점에 대상으로 삼은 계약 버전 ("MAJOR.MINOR") — load_plugin()이 CONTRACT_VERSION과 비교 검증 / [en] the contract version ("MAJOR.MINOR") the plugin was written against — load_plugin() validates it against CONTRACT_VERSION
    version: str
    author: str
    session_type: Literal["file", "batch"]
    requirements: list = dataclasses.field(default_factory=list)
    notes_per_file: int = 0
    """
    [ko] FileSession 플러그인이 모듈 전역/클래스 변수 등 파일 간 공유 상태를 락 없이 안전하게 다룰 수 없게 작성됐다면 False로 선언
    [en] Declare False if a FileSession plugin can't safely handle state shared across files
    """
    thread_safe: bool = True


_PluginFunc = TypeVar("_PluginFunc", bound=Callable[..., Any])


def plugin(
    *, name: str, contract_version: str, version: str, author: str,
    session_type: Literal["file", "batch"],
    requirements: list | None = None,
    notes_per_file: int = 0,
    thread_safe: bool = True,
) -> Callable[[_PluginFunc], _PluginFunc]:
    """
    [ko]
    플러그인의 run() 함수에 붙이는 데코레이터. PluginInfo를 만들어 run.plugin_info에 부착한다.
    contract_version은 이 플러그인이 작성 시점에 대상으로 삼은 계약("MAJOR.MINOR",
    예: "1.0")을 선언하는 필수 인자다 — load_plugin()이 현재 CONTRACT_VERSION과
    비교해 호환되지 않으면 즉시 거부한다.

    [en]
    The decorator attached to a plugin's run() function. Builds a PluginInfo and
    attaches it to run.plugin_info. contract_version is a required argument
    declaring the contract ("MAJOR.MINOR", e.g. "1.0") this plugin was written
    against — load_plugin() compares it against the current CONTRACT_VERSION and
    refuses to load it immediately on an incompatibility.
    """
    info = PluginInfo(
        name=name, contract_version=contract_version, version=version, author=author,
        session_type=session_type,
        requirements=list(requirements or []),
        notes_per_file=notes_per_file,
        thread_safe=thread_safe,
    )
    def _decorator(func: _PluginFunc) -> _PluginFunc:
        func.plugin_info = info
        return func
    return _decorator
