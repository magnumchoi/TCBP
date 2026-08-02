#!/usr/bin/env python3
"""
[ko]
[플러그인 개요]
이름: mozjpeg.py
타입: TCBP FileSession 플러그인
목적: MozJPEG을 사용한 JPEG 재압축/변환
설명: TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 파일 1개를 처리할 수 있다.
기타:
- MozJPEG은 Mozilla 재단이 발표한 고효율 JPEG 라이브러리로, 
  표준 JPEG 라이브러리에 대해 디코딩 호환성을 보장하고, 더 작은 크기와 더 나은 화질을 제공한다.
- MozJPEG은 jpeglib 패키지에 포함되어 있으며 pip install jpeglib로 설치 가능하다.
- 입력이 JPEG이면 재압축, BMP/PNG/WebP 등이면 JPEG으로 변환한다.
- 알파 채널이 있는 이미지는 흰색 배경에 합성한 뒤 변환한다.
- quality는 1~100 범위여야 하며, 벗어나면 오류로 처리한다.
- 입력 포맷 : `.bmp`, `.png`, `.jpg`, `.jpeg`, `.webp`
- 출력 포맷 : `.jpg` (항상)
독립실행시:
    python mozjpeg.py <input> <output> [quality=100]
테크니컬 노트:
- 설치된 MozJPEG 버전 중 최신(403 → 300 → 201 → 101 순)을 자동 선택하며, 없으면 표준 libjpeg로 폴백한다.
- 상기의 버전 선택 결과값은 전역 변수 _CHOSEN_MOZJPEG에 캐시된다.
  전역 캐시는 본래는 멀티스레드에 안전하게 쓰려면 lock을 사용해야 하나,
  이 경우에는 멱등적(계산 결과가 항시 동일함)이므로 lock없이도 안전하다.

[en]
[Plugin Overview]
Name: mozjpeg.py
Type: TCBP FileSession plugin
Purpose: Recompress/convert images to JPEG using MozJPEG
Description: Can be called via run(session) through TCBP, or run standalone (without tcbp) on a single file.
Notes:
- MozJPEG is a high-efficiency JPEG library from the Mozilla Foundation — it guarantees decoding
  compatibility with the standard JPEG library while producing smaller files with better quality.
- MozJPEG is bundled inside the jpeglib package; install it with `pip install jpeglib`.
- JPEG input is recompressed; BMP/PNG/WebP, etc. are converted to JPEG.
- Images with an alpha channel are composited onto a white background before conversion.
- quality must be in the 1-100 range; a value outside that range is treated as an error.
- Supported input formats: `.bmp`, `.png`, `.jpg`, `.jpeg`, `.webp`
- Output format: `.jpg` (always)
Standalone execution:
    python mozjpeg.py <input> <output> [quality=100]
Technical notes:
- Automatically selects the newest installed MozJPEG version (in order 403 → 300 → 201 → 101),
  falling back to standard libjpeg if none are available.
- The above version-selection result is cached in the global _CHOSEN_MOZJPEG.
  A global cache like this would normally need a lock to be thread-safe,
  but here it's safe without one because the computation is idempotent
  (the result is always the same).

"""
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, FileSession, ExecResult, parse_params

"""
[ko]
jpeglib/numpy/Pillow는 필수이지만 module 레벨에서 강제 import하지 않는다 —
이렇게 해야 미설치 환경에서도 validate_config.py의 import-only 검증
(load_plugin())이 실패하지 않고, 실제 처리 시점(_process)에서만 명확한
RuntimeError를 낸다.

[en]
jpeglib/numpy/Pillow are required, but they are not force-imported at module
level — this way, load_plugin()'s import-only check in validate_config.py
still succeeds even without them installed, and only _process() raises a
clear RuntimeError at actual processing time.
"""
try:
    import jpeglib
except ImportError:
    jpeglib = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None

# [ko] MozJPEG 버전 선택 / 파일 처리 핵심 로직 (MozJPEG.py에서 벤더링)
# [en] MozJPEG version selection / core file-processing logic (vendored from MozJPEG.py)

SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def is_jpeg_path(p: Path) -> bool:
    return p.suffix.lower() in {".jpg", ".jpeg"}


def is_supported_input(p: Path) -> bool:
    return p.suffix.lower() in SUPPORTED_INPUT_EXTS


_CHOSEN_MOZJPEG = None


def _choose_mozjpeg_version():
    try:
        avail = set(jpeglib.version.versions())
    except Exception:
        avail = set()
    for v in ("mozjpeg403", "mozjpeg300", "mozjpeg201", "mozjpeg101"):
        if v in avail:
            return v
    return None


def _ensure_mozjpeg_selected():
    global _CHOSEN_MOZJPEG
    if _CHOSEN_MOZJPEG is None:
        _CHOSEN_MOZJPEG = _choose_mozjpeg_version()
    return _CHOSEN_MOZJPEG


def process_jpeg(input_path: Path, output_path: Path, quality: int) -> tuple[bool, str]:
    """
    [ko] JPEG을 MozJPEG으로 재압축해 output_path에 쓴다.
    [en] Recompress a JPEG with MozJPEG and write the result to output_path.
    """
    try:
        ver = _ensure_mozjpeg_selected()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_in_f:
            tmp_in = Path(tmp_in_f.name)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_out_f:
            tmp_out = Path(tmp_out_f.name)

        try:
            with open(input_path, "rb") as src, open(tmp_in, "wb") as dst:
                shutil.copyfileobj(src, dst)

            if ver:
                with jpeglib.version(ver):
                    im = jpeglib.read_spatial(str(tmp_in))
                    im.write_spatial(str(tmp_out), qt=quality)
            else:
                im = jpeglib.read_spatial(str(tmp_in))
                im.write_spatial(str(tmp_out), qt=quality)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_out, "rb") as src, open(output_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        finally:
            for p in (tmp_in, tmp_out):
                if p.exists():
                    p.unlink()

        return True, ""
    except Exception as e:
        return False, f"Failed (JPEG): {input_path} -> {e}"


def process_non_jpeg(input_path: Path, output_path: Path, quality: int) -> tuple[bool, str]:
    """
    [ko] BMP/PNG/WebP 등을 알파 합성 후 JPEG으로 변환해 output_path에 쓴다.
    [en] Composite alpha for BMP/PNG/WebP, etc., convert to JPEG, and write to output_path.
    """
    try:
        with Image.open(input_path) as pil_img:
            pil_img.load()
            mode = pil_img.mode
            if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in pil_img.info):
                bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                rgb_img = pil_img.convert("RGBA")
                bg.paste(rgb_img, mask=rgb_img.split()[-1])
            else:
                bg = pil_img if pil_img.mode == "RGB" else pil_img.convert("RGB")
            arr = np.asarray(bg, dtype=np.uint8)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_out_f:
            tmp_out = Path(tmp_out_f.name)

        try:
            jpeg = jpeglib.from_spatial(arr)
            ver = _ensure_mozjpeg_selected()
            if ver:
                with jpeglib.version(ver):
                    jpeg.write_spatial(str(tmp_out), qt=quality)
            else:
                jpeg.write_spatial(str(tmp_out), qt=quality)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_out, "rb") as src, open(output_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        finally:
            if tmp_out.exists():
                tmp_out.unlink()

        return True, ""
    except Exception as e:
        return False, f"Failed (convert): {input_path} -> {e}"


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(input_path: str, output_path: str, params: dict) -> None:
    if jpeglib is None or np is None or Image is None:
        raise RuntimeError("mozjpeg plugin requires jpeglib, numpy, Pillow — pip install jpeglib numpy Pillow")

    src, out = Path(input_path), Path(output_path)
    if not is_supported_input(src):
        raise ValueError(f"unsupported extension: {src.suffix}")

    quality = int(params.get("quality", 100))
    if not (1 <= quality <= 100):
        raise ValueError(f"quality must be between 1 and 100 (got {quality})")

    ok, msg = process_jpeg(src, out, quality) if is_jpeg_path(src) else process_non_jpeg(src, out, quality)
    if not ok:
        raise RuntimeError(msg)


@plugin(
    name="mozjpeg",
    version="1.0",
    author="Magnum Choi",
    session_type="file",
    requirements=["jpeglib", "numpy", "Pillow"],
    notes_per_file=0,
    # [ko] _CHOSEN_MOZJPEG 전역 캐시가 락 없이 안전한 이유는 상단 "테크니컬 노트" 및
    #      플러그인 가이드 5.10절 참고 — 멱등적 계산이라 True로 둔다.
    # [en] See the "Technical notes" above and the plugin guide's Section 5.10 for why
    #      the _CHOSEN_MOZJPEG global cache is safe without a lock — it's an idempotent
    #      computation, so this stays True.
    thread_safe=True,
)
def run(session: FileSession) -> ExecResult:  # [ko] TCBP 진입점 / [en] TCBP entry point
    try:
        _process(session.input, session.output, session.params)
    except Exception as exc:
        return ExecResult(False, str(exc))
    return ExecResult(True, "")


if __name__ == "__main__":  # [ko] 단독 CLI 진입점 / [en] standalone CLI entry point
    if len(sys.argv) < 3:
        print("Usage: python mozjpeg.py <input> <output> [quality=100]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {"quality": raw.get("quality", "100")}
    try:
        _process(input_path, output_path, cli_params)
        print(f"OK: {input_path}")
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
