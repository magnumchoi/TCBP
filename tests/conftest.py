import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

"""
[ko]
tcbp.py는 패키지가 아니라 TCBP 루트의 단일 파일이므로(0장), 테스트에서
`import tcbp`가 되려면 루트를 sys.path에 넣어야 한다. plugin/ 디렉터리도
추가해 각 플러그인 unit 테스트가 `import remove_bom` 식으로 모듈을 직접
가져와 _process()에 접근할 수 있게 한다 (16.3.1).

[en]
tcbp.py is a single file at the TCBP root, not a package (Chapter 0), so
`import tcbp` in tests requires putting the root on sys.path. The plugin/
directory is added too, so each plugin's unit tests can directly
`import remove_bom`-style and reach _process() (16.3.1).
"""
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "plugin"))
