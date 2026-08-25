"""
[ko] Logging 설정
[en] Logging Setup
"""
import datetime
import logging
import sys
from pathlib import Path

from core.config import _SCRIPT_DIR


def _resolve_log_path(log_file: str, job_name: str) -> Path:
    """
    [ko]
    log_file 안의 {job}/{timestamp} 자리표시자를 치환하고, 상대경로면
    _SCRIPT_DIR 기준으로 고정한다 — 여러 번 실행해도 한 파일에 계속 쌓이지
    않고 실행마다 별도 파일로 분리되게 한다.

    [en]
    Expand {job}/{timestamp} placeholders in log_file and anchor the result
    to _SCRIPT_DIR if relative, so repeated runs land in their own file instead
    of appending to one shared log.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    expanded  = log_file.format(job=job_name or "job", timestamp=timestamp)
    path      = Path(expanded)
    return path if path.is_absolute() else _SCRIPT_DIR / path


class _FileOnlyFilter(logging.Filter):
    """
    [ko]
    logger.warning(msg, extra={"file_only": True})로 남긴 레코드를 콘솔
    핸들러에서만 걸러낸다 (파일 핸들러는 그대로 통과) — FileSession 플러그인의
    slot 초과 경고가 parallel 모드의 ANSI 블록 렌더링을 깨지 않도록 하기 위함
    (10.3.1.1).

    [en]
    Filters out records logged via logger.warning(msg, extra={"file_only": True})
    from the console handler only (the file handler still passes them through)
    — so a FileSession plugin's slot-overflow warning doesn't corrupt the ANSI
    block rendering in parallel mode (10.3.1.1).
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "file_only", False)


def setup_logging(log: bool, log_file: str, job_name: str = "") -> logging.Logger:
    logger = logging.getLogger("tcbp")
    logger.setLevel(logging.DEBUG)

    # [ko] 콘솔은 레벨 프리픽스 없는 순수 메시지를 유지하고(OutputManager의 ANSI
    #      덮어쓰기가 이를 전제로 함), 파일에는 타임스탬프+레벨을 남겨 별도의
    #      *_failed.log 없이도 실패 건만 필터링(grep "[ERROR]")할 수 있게 한다.
    # [en] Console keeps the bare message (OutputManager's ANSI overwrite relies on
    #      no level prefix); the file gets timestamp+level so failures can be
    #      filtered (grep "[ERROR]") without spinning off a separate *_failed.log.
    console_fmt = logging.Formatter("%(message)s")
    file_fmt    = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(console_fmt)
    ch.addFilter(_FileOnlyFilter())
    logger.addHandler(ch)

    if log and log_file:
        log_path = _resolve_log_path(log_file, job_name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    return logger
