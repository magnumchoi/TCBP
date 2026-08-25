"""
[ko]
플러그인 로딩. ./plugin/<name>.py로의 매핑은 결정론적이다 — 별도 탐색/등록
메커니즘 없음. tcbp.py 런타임과 validate_config.py가 load_plugin()을 그대로
공유해, 플러그인 로딩 로직이 두 곳에서 따로 구현되며 어긋나는 일이 없게 한다.
PluginInfo.contract_version과 core/contract.py의 CONTRACT_VERSION을 비교하는
계약 호환성 검사(_check_contract_version)도 여기서 담당한다.

[en]
Plugin loading. Mapping to ./plugin/<name>.py is deterministic — there is no
separate discovery/registration mechanism. The tcbp.py runtime and
validate_config.py share load_plugin() as-is, so the plugin loading logic is
never implemented twice and never drifts apart. Also owns the contract
compatibility check (_check_contract_version) comparing PluginInfo.contract_version
against core/contract.py's CONTRACT_VERSION.
"""
import importlib.util
import re
from pathlib import Path
from typing import Callable

from core.config import _SCRIPT_DIR
from core.contract import CONTRACT_VERSION, PluginInfo, TcbpError
from messages import _t


_PLUGIN_NAME_RE = re.compile(r"^[\w-]+$")


def _plugin_path(name: str) -> Path:
    if not _PLUGIN_NAME_RE.match(name):
        raise TcbpError(_t("err_plugin_invalid_name", name=name))
    return _SCRIPT_DIR / "plugin" / f"{name}.py"


# [ko] 플러그인 계약 버전 검사 (PluginInfo.contract_version) — 정책:
#      - 형식이 "MAJOR.MINOR"가 아니면 오류.
#      - MAJOR가 다르면 오류 (하위 호환을 깨는 변경이 있었다는 뜻).
#      - MAJOR가 같고 선언된 MINOR가 현재보다 크면 오류 (플러그인이 이 TCBP가
#        아직 갖지 않은 계약 기능을 요구한다는 뜻).
#      - MAJOR가 같고 MINOR가 같거나 낮으면 호환 — MINOR 상승은 항상 하위
#        호환 추가만 의미하므로 통과시킨다.
# [en] Plugin contract-version check (PluginInfo.contract_version) — policy:
#      - Not in "MAJOR.MINOR" form -> error.
#      - Differing MAJOR -> error (a compatibility-breaking change happened).
#      - Same MAJOR but a declared MINOR greater than the current one -> error
#        (the plugin requires a contract feature this TCBP doesn't have yet).
#      - Same MAJOR and MINOR equal or lower -> compatible — a MINOR bump only
#        ever means a backward-compatible addition, so it's let through.
_CONTRACT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def _check_contract_version(name: str, declared: str) -> None:
    m = _CONTRACT_VERSION_RE.match(declared)
    if not m:
        raise TcbpError(_t("err_plugin_contract_version_invalid", name=name, value=declared))
    declared_major, declared_minor = int(m.group(1)), int(m.group(2))
    current_major, current_minor = (int(x) for x in CONTRACT_VERSION.split("."))
    if declared_major != current_major:
        raise TcbpError(_t("err_plugin_contract_major_mismatch", name=name, declared=declared, current=CONTRACT_VERSION))
    if declared_minor > current_minor:
        raise TcbpError(_t("err_plugin_contract_minor_ahead", name=name, declared=declared, current=CONTRACT_VERSION))


def load_plugin(name: str) -> Callable:
    """
    [ko]
    ./plugin/<name>.py를 import하고, @plugin(...)으로 검증된 run() 함수를
    반환한다. run(session)은 절대 호출하지 않는다 — import까지만 한다.
    PluginInfo.contract_version이 현재 CONTRACT_VERSION과 호환되지 않으면
    이 자리에서 즉시 거부한다(_check_contract_version). 실패 시 i18n
    메시지를 담은 TcbpError를 던진다 (5.5, 10장).

    [en]
    Imports ./plugin/<name>.py and returns its run() function, validated via
    @plugin(...). Never calls run(session) — import only. If
    PluginInfo.contract_version is incompatible with the current
    CONTRACT_VERSION, it is rejected right here (_check_contract_version).
    Raises a TcbpError carrying an i18n message on failure (5.5, Chapter 10).
    """
    path = _plugin_path(name)
    if not path.exists():
        raise TcbpError(_t("err_plugin_not_found", name=name, path=str(path)))
    spec = importlib.util.spec_from_file_location(f"tcbp_plugin_{name}", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise TcbpError(_t("err_plugin_import_failed", name=name, error=str(exc))) from exc
    run_fn = getattr(module, "run", None)
    if run_fn is None or not callable(run_fn):
        raise TcbpError(_t("err_plugin_no_run", name=name))
    info = getattr(run_fn, "plugin_info", None)
    if not isinstance(info, PluginInfo):
        raise TcbpError(_t("err_plugin_invalid_metadata", name=name))
    _check_contract_version(name, info.contract_version)
    return run_fn
