#!/usr/bin/env python3
"""
[ko][플러그인 개요]
이름: remove_bom.py
버전: v1.0
타입: TCBP FileSession 플러그인
목적: 텍스트 파일의 UTF-8 BOM(Byte Order Mark) 제거
설명: TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 파일 1개를 처리할 수 있다.
독립실행시:
    python remove_bom.py <input> <output> [backup=true] [eachline=true]
기타:
- BOM 이란 UTF-8 인코딩된 텍스트 파일에서, 이 파일이 유니코드 파일임을 알리기 위해
  파일 시작부에 붙는 3바이트 시그니처(0xEF, 0xBB, 0xBF)를 말한다.
- 본 플러그인은 파일 시작부의 BOM뿐 아니라, 파일의 중간 각 줄에 삽입된 BOM도 제거한다. (eachline=true 파라미터)
  원래는 시작부에만 BOM이 있어야 하나, `copy /a 01.txt + 02.txt result.txt` 등으로 파일을 강제로 이어붙이면
  BOM이 중간에 혼입될 수 있다. 이때 일반 텍스트 에디터로는 확인 및 제거가 불가능하다.
- backup=true 지정 시 원본을 .bak 확장자로 보관한 뒤 덮어쓴다.
- BOM이 실제로 없으면 출력 파일을 만들지 않고 원본을 그대로 둔다.
버전이력:
- v1.0 : 최초 작성

[en][Plugin Overview]
Name: remove_bom.py
Version: v1.0
Type: TCBP FileSession plugin
Purpose: Remove the UTF-8 BOM (Byte Order Mark) from text files
Description: Can be called via run(session) through TCBP, or run standalone (without tcbp) on a single file.
Standalone execution:
    python remove_bom.py <input> <output> [backup=true] [eachline=true]
Notes:
- A BOM is a 3-byte signature (0xEF, 0xBB, 0xBF) placed at the start of a UTF-8-encoded text file to
  mark it as a Unicode file.
- This plugin removes not only a BOM at the start of the file but also BOMs inserted mid-file at the
  start of individual lines (the eachline=true parameter). A BOM should normally appear only at the
  very start of a file, but forcibly concatenating files (e.g. `copy /a 01.txt + 02.txt result.txt`)
  can leave stray BOMs embedded in the middle — something an ordinary text editor can neither detect
  nor remove.
- When backup=true is set, the original is kept with a .bak extension before being overwritten.
- If no BOM is actually found, no output file is written and the original is left untouched.
Version history:
- v1.0 : Initial version.
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, FileSession, ExecResult, parse_params, _to_bool

# [ko] BOM 제거 핵심 로직
# [en] Core BOM-removal logic

BOM = bytes([0xEF, 0xBB, 0xBF])
CR = 0x0D
LF = 0x0A


class BOMRemovalResult:
    def __init__(self, processed_bytes: bytes, bom_count: int):
        self.bytes = processed_bytes
        self.bom_count = bom_count


def remove_bom_from_file(file_bytes: bytes) -> BOMRemovalResult:
    if len(file_bytes) >= 3 and file_bytes[:3] == BOM:
        return BOMRemovalResult(file_bytes[3:], 1)
    return BOMRemovalResult(file_bytes, 0)


def remove_bom_each_line(file_bytes: bytes) -> BOMRemovalResult:
    cleaned_bytes = bytearray()
    i = 0
    bom_count = 0

    if len(file_bytes) == 0:
        return BOMRemovalResult(bytes(), 0)

    while True:
        line = bytearray()

        while i < len(file_bytes):
            if (i + 1 < len(file_bytes) and
                    file_bytes[i] == CR and
                    file_bytes[i + 1] == LF):
                break
            elif file_bytes[i] == LF or file_bytes[i] == CR:
                break
            else:
                line.append(file_bytes[i])
                i += 1

        if len(line) >= 3 and bytes(line[:3]) == BOM:
            line = line[3:]
            bom_count += 1

        cleaned_bytes.extend(line)

        if i < len(file_bytes):
            if (i + 1 < len(file_bytes) and
                    file_bytes[i] == CR and
                    file_bytes[i + 1] == LF):
                cleaned_bytes.append(CR)
                cleaned_bytes.append(LF)
                i += 2
            elif file_bytes[i] == CR or file_bytes[i] == LF:
                cleaned_bytes.append(file_bytes[i])
                i += 1

        if i >= len(file_bytes):
            break

    return BOMRemovalResult(bytes(cleaned_bytes), bom_count)


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(input_path: str, output_path: str, params: dict) -> None:
    src = Path(input_path)
    file_bytes = src.read_bytes()

    result = remove_bom_each_line(file_bytes) if params.get("eachline") else remove_bom_from_file(file_bytes)

    # [ko] BOM이 실제로 있었을 때만 backup + 덮어쓰기 — 없으면 원본을 그대로 둔다 (기존 동작 그대로 승계)
    # [en] Only back up + overwrite when a BOM was actually present — otherwise leave the original untouched (preserves prior behavior)
    if result.bom_count > 0:
        if params.get("backup"):
            shutil.copy2(src, src.with_suffix(src.suffix + ".bak"))
        Path(output_path).write_bytes(result.bytes)


@plugin(
    name="remove_bom",
    contract_version="1.0",
    version="1.0",
    author="Magnum Choi",
    session_type="file",
    requirements=[],
    notes_per_file=1,
    thread_safe=True,  # [ko] 모듈 전역 가변 상태 없음 (5.10절) / [en] no module-level mutable state (Section 5.10)
)
def run(session: FileSession) -> ExecResult:  # [ko] TCBP 진입점 / [en] TCBP entry point
    try:
        _process(session.input, session.output, session.params)
    except Exception as exc:
        return ExecResult(False, str(exc))
    session.log(f"done: {Path(session.input).name}", slot=0)
    return ExecResult(True, "")


if __name__ == "__main__":  # [ko] 단독 CLI 진입점 / [en] standalone CLI entry point
    if len(sys.argv) < 3:
        print("Usage: python remove_bom.py <input> <output> [backup=true] [eachline=true]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {
        "backup":   _to_bool(raw.get("backup", "false")),
        "eachline": _to_bool(raw.get("eachline", "false")),
    }
    try:
        _process(input_path, output_path, cli_params)
        print(f"OK: {input_path}")
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
