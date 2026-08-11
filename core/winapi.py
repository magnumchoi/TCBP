"""
[ko] 단축 경로 변환, ACP 인코딩 가능 여부 확인, ANSI 이스케이프 활성화, cmd.exe 없이 argv 파싱.
[en] short-path conversion, ACP encodability check, ANSI escape enablement, and argv parsing without cmd.exe.
"""
import ctypes
from pathlib import Path


def _get_short_path(path: str) -> str:
    """
    [ko]
    GetShortPathNameW로 8.3 ASCII 단축 경로를 반환한다.
    파일/디렉토리가 존재하지 않으면 부모 디렉토리까지 재귀적으로 올라간다.

    [en]
    Return the 8.3 ASCII short path via GetShortPathNameW. If the file/directory
    doesn't exist, recurse up to the parent directory.
    """
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 32768)
    if n > 0:
        return buf.value
    p = Path(path)
    if p.parent == p:
        return path
    return str(Path(_get_short_path(str(p.parent))) / p.name)


def _has_non_acp(s: str) -> bool:
    """
    [ko] 시스템 ACP(cp949 등)로 인코딩 불가능한 문자가 포함되어 있으면 True.
    [en] True if the string contains a character that cannot be encoded in the system ACP (cp949, etc).
    """
    try:
        s.encode('mbcs')
        return False
    except UnicodeEncodeError:
        return True


def _enable_win_ansi() -> None:
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode   = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
_CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)

def _parse_cmdline(cmd: str) -> list[str]:
    """
    [ko] cmd.exe를 거치지 않고 Windows API로 직접 파싱 → Unicode 경로 보존.
    [en] Parse directly via the Windows API without going through cmd.exe -> preserves Unicode paths.
    """
    argc = ctypes.c_int(0)
    argv = _CommandLineToArgvW(cmd, ctypes.byref(argc))
    if not argv:
        return [cmd]
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)
