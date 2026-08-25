"""
[ko] 화면 표시용 파일명 축약
[en] Filename Truncation for Screen Display
"""
import logging
import re
import shutil
import sys
import threading
import unicodedata
from pathlib import Path

from core.winapi import _enable_win_ansi
from messages import _t

try:
    from wcwidth import wcswidth as _wcswidth, wcwidth as _wcwidth_char
except ImportError:
    _wcswidth = None
    _wcwidth_char = None


# [ko] 파일명/메시지는 신뢰할 수 없는 소스(예: 압축 해제 결과, 네트워크 공유)에서 올 수
#      있다. ANSI 커서 제어 시퀀스와 함께 그대로 stdout에 쓰이므로, ESC(0x1b) 등 제어
#      문자를 출력 직전에 제거해 터미널 이스케이프 인젝션/로그 위조를 막는다.
# [en] Filenames/messages can come from an untrusted source (e.g. archive
#      extraction, a network share). They're written to stdout alongside our own
#      ANSI cursor-control sequences, so control characters (ESC 0x1b, etc.) are
#      stripped right before output to prevent terminal escape injection / log forging.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _strip_control_chars(s: str) -> str:
    return _CONTROL_CHARS_RE.sub("", s)


def _char_width(ch: str) -> int:
    """
    [ko]
    단일 문자의 콘솔 표시 폭. wcwidth 패키지가 설치되어 있으면 이를 사용하고,
    없으면 east_asian_width 기반 근사치로 대체한다.

    [en]
    Console display width of a single character. Uses the wcwidth package if
    installed, otherwise falls back to an east_asian_width-based approximation.
    """
    if _wcwidth_char is not None:
        w = _wcwidth_char(ch)
        if w >= 0:
            return w
        return 0  # [ko] 결합문자 등 wcwidth가 음수를 반환하는 경우 폭 0 취급 / [en] Treat combining characters etc. (wcwidth returns negative) as width 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(s: str) -> int:
    """
    [ko]
    한글/한자/가나 등 전각 문자는 폭 2, 그 외는 폭 1로 콘솔 표시 폭을 계산한다.
    wcwidth 패키지가 설치되어 있으면 wcswidth로 정확한 터미널 표시 폭을 계산하고,
    없으면 east_asian_width 기반 근사치로 대체한다.

    [en]
    Compute console display width, treating fullwidth characters (Hangul,
    Hanja, Kana, etc.) as width 2 and everything else as width 1. Uses wcwidth's
    wcswidth for an accurate terminal display width if the package is installed,
    otherwise falls back to an east_asian_width-based approximation.
    """
    if _wcswidth is not None:
        w = _wcswidth(s)
        if w >= 0:
            return w
    return sum(_char_width(ch) for ch in s)


def _max_name_display_len() -> int:
    """
    [ko]
    "[idx] in → out" 한 줄에 맞도록 파일명 1개당 최대 표시 폭을 계산한다.
    input/output 두 개가 나란히 출력되므로 각각 콘솔 폭의 절반보다 약간 작게 잡는다.

    [en]
    Compute the max display width per filename so that "[idx] in → out" fits on
    one line. Since input/output are printed side by side, each is set to a bit
    less than half the console width.
    """
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    overhead = len("[9999] ") + len(" → ")
    per_name = (cols - overhead) // 2 - 2
    return max(per_name, 10)


def _truncate_filename(name: str, max_width: int) -> str:
    """
    [ko]
    긴 파일명을 표시할 때 확장자는 항상 남기고, 중간을 "..."로 생략한다.
    폭 계산은 전각 문자를 2칸으로 취급하는 _display_width 기준.

    [en]
    When displaying a long filename, always keep the extension and elide the
    middle with "...". Width is computed via _display_width, which treats
    fullwidth characters as 2 columns.
    """
    name = _strip_control_chars(name)
    if _display_width(name) <= max_width:
        return name
    stem = Path(name).stem
    ext = Path(name).suffix
    budget = max_width - _display_width(ext) - 3  # [ko] "..." 폭 3 제외 / [en] subtract the "..." width of 3
    if budget < 10:
        budget = 10  # [ko] 최소 폭 보장 / [en] guarantee a minimum width
    if _display_width(stem) <= budget:
        return stem + ext
    width = 0
    cut = 0
    for i, ch in enumerate(stem):
        w = _char_width(ch)
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return stem[:cut] + "..." + ext


def _max_message_display_len() -> int:
    """
    [ko]
    { msg = ... } 한 줄 표시에 맞는 최대 폭. 콘솔 줄바꿈이 생기면
    ANSI 커서 계산이 어긋나므로 반드시 한 줄 안에 들어오도록 자른다.

    [en]
    Max width that fits a { msg = ... } line on one line. If the console line
    wraps, the ANSI cursor math breaks, so it must always be truncated to fit on
    a single line.
    """
    cols = shutil.get_terminal_size(fallback=(120, 24)).columns
    return max(cols - 4, 10)


def _truncate_message(text: str, max_width: int) -> str:
    """
    [ko] 긴 메시지를 한 줄 폭에 맞춰 말미를 "..."로 생략한다.
    [en] Truncate the tail of a long message with "..." to fit a single line's width.
    """
    text = _strip_control_chars(text)
    if _display_width(text) <= max_width:
        return text
    budget = max_width - 3
    width = 0
    cut = 0
    for i, ch in enumerate(text):
        w = _char_width(ch)
        if width + w > budget:
            break
        width += w
        cut = i + 1
    return text[:cut] + "..."


# [ko] 멀티스레드 순서 보장 출력 매니저
# [en] Order-Preserving Output Manager for Multithreading

class OutputManager:
    """
    [ko]
    스레드로부터 start/note/finish 이벤트를 받아 출력한다.

    파일 1개는 고정 크기 블록(1 + notes_per_file 줄)을 차지한다.
    on_start()  → 버퍼링 후 순서가 되면 블록 전체(제목줄 + note 예약 빈 줄)를 한 번에 출력
    on_note()   → 블록 내 지정된 예약 줄을 그 자리에서 덮어씀 (ANSI, 도착 순서 무관)
    on_finish() → 블록의 제목줄을 완료 순서대로 즉시 결과로 덮어씀 (ANSI, 번호 순서 무관)

    on_error=stop 등으로 뒤의 note가 아예 발생하지 않으면, 예약된 빈 줄이 그대로 남아
    "중단 시 빈 칸으로 flush"를 별도 코드 없이 자연스럽게 만족한다.

    [en]
    Receives start/note/finish events from threads and prints them.

    Each file occupies a fixed-size block (1 + notes_per_file lines).
    on_start()  -> buffers, and once its turn comes, prints the whole block
                   (title line + reserved blank lines for notes) at once
    on_note()   -> overwrites the reserved line within the block in place
                   (via ANSI, regardless of arrival order)
    on_finish() -> immediately overwrites the block's title line with the result,
                   in completion order (via ANSI, regardless of index order)

    If a later note never fires at all (e.g. due to on_error=stop), the reserved
    blank line simply stays blank — satisfying "flush as a blank line on abort"
    naturally, with no extra code needed.
    """

    def __init__(self, logger: logging.Logger, notes_per_file: int = 0) -> None:
        _enable_win_ansi()
        self._logger        = logger
        self._lock          = threading.Lock()
        self._notes_per_file = notes_per_file
        self._block_height   = 1 + notes_per_file
        self._start_buf  : dict[int, str]                        = {}
        self._finish_buf : dict[int, tuple[str, str, bool, str]] = {}
        self._pending_notes: dict[int, dict[int, str]]      = {}
        self._rows       : dict[int, int]                   = {}
        self._line_count  = 0
        self._next_start  = 1

    def on_start(self, idx: int, filename: str) -> None:
        with self._lock:
            self._start_buf[idx] = _truncate_filename(filename, _max_name_display_len())
            self._flush()

    def on_note(self, idx: int, slot: int, text: str) -> None:
        with self._lock:
            if idx not in self._rows:
                # [ko] 블록이 아직 화면에 안 나왔으면(거의 없는 경우) 대기했다가 start flush 시 반영
                # [en] If the block hasn't appeared on screen yet (rare), wait and apply it
                #      when start is flushed
                self._pending_notes.setdefault(idx, {})[slot] = text
                return
            self._write_note(idx, slot, text)

    def on_finish(self, idx: int, in_name: str, out_name: str, ok: bool, note: str = "") -> None:
        # [ko] note가 있으면 별도 예약 줄이 아니라 제목줄 자체에 줄바꿈 없이 덧붙여 표시한다
        # [en] if note is given, it is appended in place on the title line itself
        #      (no line break) rather than on a separate reserved line
        with self._lock:
            self._finish_buf[idx] = (in_name, out_name, ok, note)
            self._flush()

    def _write_note(self, idx: int, slot: int, text: str) -> None:
        base_row = self._rows[idx]
        row      = base_row + 1 + slot
        line     = f"  {_truncate_message(text, _max_message_display_len())}"
        up       = self._line_count - row
        sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
        sys.stdout.flush()
        self._logger.debug(line)

    def _flush(self) -> None:
        # [ko] start 이벤트를 순서대로 출력 (제목줄 + note용 예약 빈 줄을 블록으로 한 번에 출력)
        # [en] Print start events in order (print the block — title line + reserved
        #      blank lines for notes — all at once)
        while self._next_start in self._start_buf:
            idx      = self._next_start
            filename = self._start_buf.pop(idx)
            self._rows[idx] = self._line_count
            # [ko] on_finish()가 이 줄을 완료 결과로 덮어쓰기 전까지, 대기 중인 파일이
            #      멈춘 것처럼 보이지 않도록 "처리 중..." 표시를 붙여둔다
            # [en] until on_finish() overwrites this line with the result, tag it
            #      "Processing..." so a queued file doesn't look like it has stalled
            sys.stdout.write(f"[{idx:>4}] {filename} {_t('label_processing')}\n")
            sys.stdout.write("\n" * self._notes_per_file)
            self._line_count += self._block_height
            sys.stdout.flush()
            self._next_start += 1
            for slot, text in sorted(self._pending_notes.pop(idx, {}).items()):
                self._write_note(idx, slot, text)

        # [ko] finish 이벤트: start가 출력된 항목은 완료 순서대로 즉시 출력 (번호 순서 무관)
        # [en] finish events: items whose start was printed are shown immediately in
        #      completion order (regardless of index order)
        for idx in sorted(k for k in list(self._finish_buf) if k in self._rows):
            in_name, out_name, ok, note = self._finish_buf.pop(idx)
            row                   = self._rows.pop(idx)
            mark                  = "→" if ok else "✗"
            max_len               = _max_name_display_len()
            line                  = f"[{idx:>4}] {_truncate_filename(in_name, max_len)} {mark} {_truncate_filename(out_name, max_len)}"
            if note:
                line = _truncate_message(f"{line}  {note}", _max_message_display_len())
            up                    = self._line_count - row
            # [ko] \033[{up}A\r : 목표 행으로 이동  \033[K : 행 지우기  \033[{up}B\r : 복귀
            # [en] \033[{up}A\r : move to target row  \033[K : clear the row  \033[{up}B\r : move back
            sys.stdout.write(f"\033[{up}A\r{line}\033[K\033[{up}B\r")
            sys.stdout.flush()
            # [ko] 콘솔은 ANSI 덮어쓰기, 로그 파일에는 완성된 결과 행만 기록
            # [en] Console is overwritten via ANSI; the log file only records the final result row
            self._logger.debug(line)
