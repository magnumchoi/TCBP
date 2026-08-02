"""
[ko]
plugin/testdata/<name>/를 순회하며 실제 standalone CLI를 subprocess로
구동하고 결과를 expected_output과 비교한다 (16.3.3). 4.1의 "tcbp 없이 단독
CLI로 실행 가능"을 실제로 검증하는 유일한 계층 — unit 계층은 argparse를
거치지 않으므로 CLI 인자 파싱 버그를 못 잡는다.

신규 FileSession 플러그인을 추가할 때 이 파일은 수정할 필요가 없다 —
plugin/testdata/<name>/ 폴더만 추가하면 자동으로 포함된다. BatchSession
플러그인(group_md5)은 1:1 input/output 골든 방식과 안 맞아 제외한다
(test_plugin_group_md5.py에 전용 cli 테스트가 따로 있음).

Pillow/numpy는 이 테스트(RMSE 픽셀 비교)에만 쓰이는 tests 전용 dev
의존성이다 — tcbp.py 코어 의존성(pydantic-with-fallback, 3.8.1)과 무관하다.

[en]
Walks plugin/testdata/<name>/, drives the actual standalone CLI via
subprocess, and compares the result against expected_output (16.3.3). The
only layer that actually verifies 4.1's "runnable as a standalone CLI
without tcbp" — the unit layer never goes through argparse, so it can't
catch CLI argument-parsing bugs.

This file needs no changes when adding a new FileSession plugin — just add a
plugin/testdata/<name>/ folder and it's automatically included. The
BatchSession plugin (group_md5) is excluded since it doesn't fit the 1:1
input/output golden approach (test_plugin_group_md5.py has its own dedicated
cli test instead).

Pillow/numpy are dev dependencies used only by this test (RMSE pixel
comparison) — unrelated to tcbp.py's core dependencies
(pydantic-with-fallback, 3.8.1).
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
TESTDATA_DIR = PLUGIN_DIR / "testdata"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_DEFAULT_IMAGE_RMSE_TOLERANCE = 1.0


def _discover_golden_cases() -> list[str]:
    if not TESTDATA_DIR.is_dir():
        return []
    return sorted(p.name for p in TESTDATA_DIR.iterdir() if p.is_dir())


def _images_match(actual_path: Path, expected_path: Path, tolerance: float) -> tuple[bool, str]:
    from PIL import Image
    import numpy as np

    a_img = Image.open(actual_path).convert("RGBA")
    e_img = Image.open(expected_path).convert("RGBA")
    if a_img.size != e_img.size:
        return False, f"size mismatch: {a_img.size} != {e_img.size}"
    a = np.asarray(a_img, dtype=np.float64)
    e = np.asarray(e_img, dtype=np.float64)
    rmse = math.sqrt(float(np.mean((a - e) ** 2)))
    return rmse <= tolerance, f"RMSE={rmse:.3f} (tolerance={tolerance})"


@pytest.mark.cli
@pytest.mark.parametrize("name", _discover_golden_cases())
def test_plugin_cli_matches_golden_output(name, tmp_path):
    case_dir = TESTDATA_DIR / name
    plugin_path = PLUGIN_DIR / f"{name}.py"
    assert plugin_path.exists(), f"plugin/testdata/{name}/ 는 있는데 plugin/{name}.py가 없음"

    input_files = [p for p in case_dir.glob("input.*")]
    assert len(input_files) == 1, f"{case_dir}에 input.* 파일이 정확히 1개 있어야 함"
    input_path = input_files[0]

    expected_path = next(case_dir.glob("expected_output.*"))
    actual_path = tmp_path / expected_path.name

    params_file = case_dir / "params.json"
    params = json.loads(params_file.read_text(encoding="utf-8")) if params_file.exists() else {}
    param_args = [f"{k}={v}" for k, v in params.items()]

    proc = subprocess.run(
        [sys.executable, str(plugin_path), str(input_path), str(actual_path), *param_args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"CLI 실행 실패:\n{proc.stdout}\n{proc.stderr}"
    assert actual_path.exists(), f"출력 파일이 생성되지 않음: {actual_path}"

    if expected_path.suffix.lower() in _IMAGE_EXTS:
        tolerance_file = case_dir / "tolerance.json"
        tolerance = (json.loads(tolerance_file.read_text(encoding="utf-8"))["rmse"]
                     if tolerance_file.exists() else _DEFAULT_IMAGE_RMSE_TOLERANCE)
        ok, detail = _images_match(actual_path, expected_path, tolerance)
        assert ok, f"{name}: 이미지 픽셀 비교 실패 — {detail}"
    else:
        assert actual_path.read_bytes() == expected_path.read_bytes(), f"{name}: 바이트 비교 실패"


def test_at_least_one_golden_case_discovered():
    assert _discover_golden_cases(), "plugin/testdata/ 아래 골든 케이스가 하나도 없음"
