"""
[ko]
plugin/*.py 전체를 순회하며 @plugin(...) 메타데이터가 유효한지 검증한다.
tcbp.load_plugin()을 그대로 재사용 — validate_config.py/tcbp.py 런타임과
동일한 로직으로 검증하므로 별도 재구현이 없다 (5.5의 import-time fail-fast를
CI에서 미리 잡아낸다). 신규 플러그인을 plugin/ 아래 추가하면 이 테스트가
자동으로 커버한다 — 테스트 코드 수정 불필요.

[en]
Walks every plugin/*.py and verifies its @plugin(...) metadata is valid.
Reuses tcbp.load_plugin() as-is — validated with the exact same logic as the
validate_config.py/tcbp.py runtime, so there's no separate reimplementation
(catches 5.5's import-time fail-fast ahead of time in CI). Adding a new
plugin under plugin/ is automatically covered by this test — no test code
changes needed.
"""
from pathlib import Path

import pytest

import tcbp

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"


def _discover_plugin_names() -> list[str]:
    return sorted(p.stem for p in PLUGIN_DIR.glob("*.py"))


@pytest.mark.parametrize("name", _discover_plugin_names())
def test_plugin_has_valid_metadata(name):
    run_fn = tcbp.load_plugin(name)
    assert callable(run_fn)
    info = run_fn.plugin_info
    assert isinstance(info, tcbp.PluginInfo)
    assert info.name == name
    assert info.session_type in ("file", "batch")
    assert info.notes_per_file >= 0
    # [ko] 번들 플러그인은 전부 같은 관리자가 유지보수하므로 항상 현재 계약 버전을
    #      그대로 따라가야 한다 — 어긋나면 CONTRACT_VERSION을 올리고도 번들
    #      플러그인 갱신을 잊었다는 뜻이다.
    # [en] Bundled plugins are all maintained by the same person, so they should
    #      always track the current contract version exactly — a mismatch means
    #      CONTRACT_VERSION was bumped without updating the bundled plugins.
    assert info.contract_version == tcbp.CONTRACT_VERSION


def test_at_least_one_plugin_discovered():
    assert _discover_plugin_names(), "plugin/ 아래 .py 플러그인이 하나도 없음"
