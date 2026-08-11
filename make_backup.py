#!/usr/bin/env python3
"""
[ko]
프로젝트 루트를 tcbp_v{version}.zip으로 백업한다. 버전은 pyproject.toml의
[project].version에서 읽는다. __pycache__/.git/.egg-info 등 산출물과 이전
백업 zip은 포함하지 않는다.

Usage:
    python backup.py

[en]
Backs up the project root into tcbp_v{version}.zip. The version is read from
pyproject.toml's [project].version. Build artifacts (__pycache__, .git,
.egg-info, etc.) and previous backup zips are excluded.

Usage:
    python backup.py
"""
import fnmatch
import tomllib
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# [ko] .gitignore와 동일한 취지 — 산출물/캐시/가상환경 디렉터리는 백업에서 제외한다.
# [en] Mirrors .gitignore's intent — build artifacts, caches, and virtualenv dirs are excluded from the backup.
_EXCLUDE_DIR_NAMES = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", "build", "dist", "htmlcov",
    ".claude", ".vscode", ".idea",
}
_EXCLUDE_FILE_PATTERNS = ("*.pyc", "*.pyo", "tcbp_v*.zip", "tcbp_error.log", "*.log")


def _read_version() -> str:
    with open(_ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _should_skip(rel_path: Path) -> bool:
    if any(part in _EXCLUDE_DIR_NAMES or part.endswith(".egg-info") for part in rel_path.parts):
        return True
    return any(fnmatch.fnmatch(rel_path.name, pattern) for pattern in _EXCLUDE_FILE_PATTERNS)


def main() -> None:
    version  = _read_version()
    out_path = _ROOT / f"tcbp_v{version}.zip"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_ROOT.rglob("*")):
            if path.is_dir():
                continue
            rel_path = path.relative_to(_ROOT)
            if _should_skip(rel_path):
                continue
            zf.write(path, rel_path)

    print(f"created: {out_path}")


if __name__ == "__main__":
    main()
