"""
[ko]
`params`는 임의 개수의 key=value를 받기 위해 nargs=REMAINDER를 쓴다.
REMAINDER의 단점: 한 번 소비를 시작하면 이후 토큰을 전부 그대로 삼킨다 —
filelist 뒤에 오는 --dry-run 같은 플래그도 예외가 아니다. _split_known_flags()가
사용자가 어디에 입력했든 인식되는 플래그를 argv에서 미리 뽑아내어, REMAINDER는
job/filelist/key=value 토큰만 보게 한다.

[en]
`params` uses nargs=REMAINDER so it can collect an open-ended list of
key=value pairs. REMAINDER's downside: once it starts consuming, it grabs
every remaining token verbatim — including flags like --dry-run if they
appear after `filelist`. _split_known_flags() pulls recognized flags out of
argv up front (regardless of where the user typed them) so REMAINDER only
ever sees job/filelist/key=value tokens.
"""
import argparse
import sys
from importlib.metadata import version as _pkg_version

from messages import _t

try:
    __version__ = _pkg_version("tcbp")
except Exception:
    __version__ = "unknown"


def _prescan_lang(argv: list[str]) -> str | None:
    """
    [ko] --lang 값을 argparse 파싱 전에 미리 알아내어 --help 텍스트도 올바른 언어로 보여준다.
    [en] Detect --lang before argparse runs, so --help text is shown in the right language too.
    """
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


_FLAGS_WITH_VALUE = {"--config", "--lang"}
_FLAGS_BOOL       = {"--dry-run", "-h", "--help", "--strict", "--version"}

def _split_known_flags(argv: list[str]) -> list[str]:
    """
    [ko]
    인식되는 플래그를 원래 상대 순서 그대로 앞으로 옮기고, 그 뒤에
    나머지 토큰(job/filelist/params)을 원래 상대 순서 그대로 이어붙인다.

    [en]
    Reorder argv so recognized flags come first, in original relative order,
    followed by the remaining tokens (job/filelist/params) in original relative
    order.
    """
    flags: list[str] = []
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        name = a.split("=", 1)[0]
        if name in _FLAGS_WITH_VALUE:
            if "=" in a:
                flags.append(a)
                i += 1
            elif i + 1 < len(argv):
                flags.extend([a, argv[i + 1]])
                i += 2
            else:
                flags.append(a)  # [ko] 값 누락; argparse가 평소대로 오류를 내도록 둠 / [en] missing value; let argparse raise its usual error
                i += 1
        elif a in _FLAGS_BOOL:
            flags.append(a)
            i += 1
        else:
            remaining.append(a)
            i += 1
    return flags + remaining


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tcbp",
        description=_t("cli_description"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{_t("cli_epilog_header")}
  python tcbp.py Conv2PNG       list.txt
  python tcbp.py ResizeImages   list.txt size=1024
  python tcbp.py CropImages     list.txt x=10 y=20 width=800 height=600
  python tcbp.py ResizeImages   list.txt size=1024 --dry-run
  python tcbp.py Conv2PNG       list.txt --config custom.toml
        """,
    )
    parser.add_argument("job",      help=_t("help_job"))
    parser.add_argument("filelist", help=_t("help_filelist"))
    parser.add_argument("params",   nargs=argparse.REMAINDER, metavar="key=value", help=_t("help_params"))
    parser.add_argument("--config", default=None, help=_t("help_config"))
    parser.add_argument("--dry-run", action="store_true", help=_t("help_dry_run"))
    parser.add_argument("--strict", action="store_true", help=_t("help_strict"))
    parser.add_argument("--lang", choices=["ko", "en"], default=None, help=_t("help_lang"))
    parser.add_argument("--version", action="version", version=f"tcbp {__version__}")
    return parser.parse_args(_split_known_flags(sys.argv[1:]))
