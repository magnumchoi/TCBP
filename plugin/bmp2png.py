#!/usr/bin/env python3
"""
[ko]
[플러그인 개요]
이름: bmp2png.py
버전: v1.0
타입: TCBP FileSession 플러그인
목적: BMP를 최적 압축된 PNG로 변환
설명: 1단계로 BMP를 PNG로 변환하고, 2단계로 oxipng로 최적화하여 파일 크기를 최소화한다.
     TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 파일 1개를 처리할 수 있다
기타:
- 최적화를 위해 oxipng.exe 가 필요하다. oxipng.exe가 없으면 최적화 단계는 스킵된다.
- oxipng.exe는 plugin/oxipng.exe로 번들링한다.
  session.params["oxipng_exe"](=job.defaults를 통한 커스텀 경로 지정, 14장 메커니즘 재사용)가 있으면 그걸 우선.
- 1단계 BMP→PNG 변환은 OpenCV를 사용하고, 없으면 Pillow로 폴백. 2단계에서 최적화할 것이므로 1단계는 압축율을 낮추고 고속 인코딩
- 2단계 oxipng 실행(단일 스레드로. 멀티스레드화는 TCBP가 담당.) 최적화 레벨 5사용. 메타데이터는 제거.

독립실행시:
    python bmp2png.py <input> <output> [delete=true] [oxipng_exe=...]

[en]
[Plugin Overview]
Name: bmp2png.py
Version: v1.0
Type: TCBP FileSession plugin
Purpose: Convert BMP to an optimally compressed PNG
Description: Step 1 converts BMP to PNG; step 2 runs oxipng to optimize it and minimize file size.
             Can be called via run(session) through TCBP, or run standalone (without tcbp) on a single file.
Notes:
- oxipng.exe is required for optimization. If oxipng.exe is missing, the optimization step is skipped.
- oxipng.exe is bundled as plugin/oxipng.exe. If session.params["oxipng_exe"] is set (a custom path
  via job.defaults, reusing the Chapter 14 mechanism), that path is used instead.
- Step 1 (BMP→PNG) uses OpenCV, falling back to Pillow if unavailable. Since step 2 optimizes it
  anyway, step 1 favors low compression and fast encoding.
- Step 2 runs oxipng (single-threaded — TCBP itself handles multi-threading) at optimization level 5,
  stripping metadata.

Standalone execution:
    python bmp2png.py <input> <output> [delete=true] [oxipng_exe=...]

"""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, FileSession, ExecResult, parse_params, _to_bool

_BUNDLED_OXIPNG = Path(__file__).resolve().parent / "oxipng.exe"

# [ko] BMP→PNG 변환 / oxipng 최적화 (bmp2png.py에서 벤더링)
# [en] BMP→PNG conversion / oxipng optimization (vendored from bmp2png.py)


def bmp_to_png(bmp_path: str, png_path: str) -> tuple[bool, str]:
    """
    [ko] OpenCV(우선) 또는 Pillow(폴백)로 BMP를 PNG로 변환한다.
    [en] Convert BMP to PNG using OpenCV (preferred) or Pillow (fallback).
    """
    try:
        import cv2
        import numpy as np

        with open(bmp_path, "rb") as f:
            img_bytes = np.frombuffer(f.read(), dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise Exception("Failed to decode BMP from buffer with OpenCV")
        is_success, buffer = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if not is_success:
            raise Exception("Failed to encode PNG with OpenCV")
        with open(png_path, "wb") as f:
            f.write(buffer.tobytes())
        return True, ""
    except ImportError:
        try:
            from PIL import Image
            img = Image.open(bmp_path)
            img.save(png_path, "PNG", compress_level=1)
            return True, ""
        except Exception as e:
            return False, f"ERROR (Pillow): {e}"
    except Exception as e:
        return False, f"ERROR (OpenCV): {e}"


def optimize_png(png_path: str, oxipng_exe: str | None) -> tuple[bool, str]:
    """
    [ko] oxipng로 PNG를 최적화한다. oxipng이 없으면 완화 실패(스킵)로 처리한다.
    [en] Optimize PNG with oxipng. If oxipng is unavailable, treat it as a soft failure (skip).
    """
    if not oxipng_exe:
        return False, "oxipng.exe not found, skipped"
    try:
        cmd = [oxipng_exe, "-o", "5", "--strip", "safe", "--threads", "1", png_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        return True, ""
    except FileNotFoundError:
        return False, "oxipng.exe not found, skipped"
    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout
        return False, f"oxipng failed: {error_message.strip()}"
    except Exception as e:
        return False, f"optimization error: {e}"


def _resolve_oxipng_exe(params: dict) -> str | None:
    custom = str(params.get("oxipng_exe", "")).strip()
    candidate = Path(custom) if custom else _BUNDLED_OXIPNG
    return str(candidate) if candidate.is_file() else None


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(input_path: str, output_path: str, params: dict) -> list[str]:
    """
    [ko] 변환 + 최적화를 수행하고, 참고용 노트 목록(oxipng 스킵/삭제 등)을 반환한다.
    [en] Perform conversion + optimization, returning a list of informational notes (oxipng skip/delete, etc.).
    """
    ok, msg = bmp_to_png(input_path, output_path)
    if not ok:
        raise RuntimeError(msg)

    notes = []
    oxipng_exe = _resolve_oxipng_exe(params)
    opt_ok, opt_msg = optimize_png(output_path, oxipng_exe)
    if not opt_ok:
        notes.append(f"[{opt_msg}]")

    if opt_ok and _to_bool(str(params.get("delete", "false"))):
        try:
            Path(input_path).unlink()
            notes.append("[source deleted]")
        except Exception as e:
            notes.append(f"[delete failed: {e}]")

    return notes


@plugin(
    name="bmp2png",
    version="1.0",
    author="Magnum Choi",
    session_type="file", requirements=["opencv-python", "Pillow", "numpy"], notes_per_file=0,
    thread_safe=True,  # [ko] 모듈 전역 가변 상태 없음(_BUNDLED_OXIPNG는 import 시 1회 계산되는 상수) (5.10절)
                       # [en] no module-level mutable state (_BUNDLED_OXIPNG is a constant computed once at import) (Section 5.10)
)
def run(session: FileSession) -> ExecResult:  # [ko] TCBP 진입점 / [en] TCBP entry point
    try:
        notes = _process(session.input, session.output, session.params)
    except Exception as exc:
        return ExecResult(False, str(exc))
    # [ko] notes는 별도 줄이 아니라 [idx] input → output 줄 뒤에 그대로 붙어 표시된다
    # [en] notes are shown appended directly after the [idx] input → output line,
    #      not on a separate line
    return ExecResult(True, " ".join(notes))


if __name__ == "__main__":  # [ko] 단독 CLI 진입점 / [en] standalone CLI entry point
    if len(sys.argv) < 3:
        print("Usage: python bmp2png.py <input> <output> [delete=true] [oxipng_exe=...]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {
        "delete":     raw.get("delete", "false"),
        "oxipng_exe": raw.get("oxipng_exe", ""),
    }
    try:
        notes = _process(input_path, output_path, cli_params)
        print(f"OK: {input_path} {' '.join(notes)}".strip())
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
