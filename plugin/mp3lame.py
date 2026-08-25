#!/usr/bin/env python3
"""
[ko][플러그인 개요]
이름: mp3lame.py
버전: v1.0
타입: TCBP FileSession 플러그인
목적: WAV/FLAC/OGG 등을 LAME으로 MP3 인코딩
설명: TCBP를 통해 run(session)으로 호출되거나, tcbp 없이 단독 CLI로 파일 1개를 처리할 수 있다.
독립실행시:
    python mp3lame.py <input> <output> [bitrate=128]
기타:
- lameenc는 libmp3lame의 Python 바인딩으로, PCM(16-bit signed, 인터리브) bytes만 받는다 —
  WAV 이외의 포맷(FLAC/OGG 등)은 직접 디코딩할 수 없다.
- soundfile(libsndfile 바인딩)로 입력 파일을 16-bit PCM numpy 배열로 디코딩한 뒤,
  그 결과를 lameenc에 넘긴다.
- 입력 포맷 : `.wav`, `.flac`, `.ogg`, `.aiff`, `.aif`
- 출력 포맷 : `.mp3` (항상)
- bitrate는 MPEG-1 Layer III 표준 비트레이트 중 하나여야 하며, 벗어나면 오류로 처리한다.
- 3채널 이상(예: 5.1채널)의 입력은 지원하지 않는다 — MP3 자체가 모노/스테레오만 지원.
테크니컬 노트:
- lameenc.Encoder()는 _process() 호출마다(=파일마다) 새로 생성한다 — 모듈 전역에 캐싱/공유하지
  않으므로 병렬 처리 시 스레드 간 공유 가변 상태 자체가 없다 (플러그인 가이드 5.10절).
- lameenc는 스테레오 모드(joint-stereo 등)를 직접 제어하는 API를 제공하지 않는다 — bit_rate/
  in_sample_rate/channels/quality만 설정 가능하며, 스테레오 처리 방식은 LAME 내부 휴리스틱에 맡겨진다.
- 파일명이 lameenc.py가 아니라 mp3lame.py인 이유: pip 패키지 lameenc와 이름이 겹치면,
  plugin/이 sys.path에 올라간 상황(예: pytest)에서 `import lameenc`가 실제 라이브러리 대신
  이 플러그인 파일 자신을 가리켜버린다 — libmp3lame(내부 C 라이브러리 이름)을 딴 mp3lame으로
  회피한다.
버전이력:
- v1.0 : 최초 작성

[en][Plugin Overview]
Name: mp3lame.py
Version: v1.0
Type: TCBP FileSession plugin
Purpose: Encode WAV/FLAC/OGG, etc. to MP3 using LAME
Description: Can be called via run(session) through TCBP, or run standalone (without tcbp) on a single file.
Standalone execution:
    python mp3lame.py <input> <output> [bitrate=128]
Notes:
- lameenc is a Python binding for libmp3lame that only accepts PCM (16-bit signed, interleaved)
  bytes — it cannot decode any format other than raw PCM itself (FLAC/OGG/etc. are out of scope for it).
- soundfile (a libsndfile binding) decodes the input file into a 16-bit PCM numpy array first,
  which is then handed to lameenc.
- Supported input formats: `.wav`, `.flac`, `.ogg`, `.aiff`, `.aif`
- Output format: `.mp3` (always)
- bitrate must be one of the standard MPEG-1 Layer III bitrates; a value outside that set is
  treated as an error.
- Inputs with 3 or more channels (e.g. 5.1 surround) are not supported — MP3 itself only supports
  mono/stereo.
Technical notes:
- A fresh lameenc.Encoder() is created on every _process() call (i.e. per file) — never cached or
  shared at module level, so there is no shared mutable state between threads during parallel
  processing at all (plugin guide, Section 5.10).
- lameenc exposes no API to directly control the stereo mode (e.g. joint-stereo) — only bit_rate/
  in_sample_rate/channels/quality can be set; the stereo handling is left to LAME's own internal
  heuristics.
- Why the file is named mp3lame.py instead of lameenc.py: naming it lameenc.py would collide
  with the pip package `lameenc` — whenever plugin/ ends up on sys.path (e.g. under pytest),
  `import lameenc` would resolve to this plugin file itself instead of the real library. Named
  after libmp3lame (the underlying C library) instead, to avoid that collision.
Version history:
- v1.0 : Initial version.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # [ko] tcbp.py가 있는 상위 폴더 / [en] parent folder containing tcbp.py
from tcbp import plugin, FileSession, ExecResult, parse_params

"""
[ko]
lameenc/soundfile/numpy는 필수이지만 module 레벨에서 강제 import하지 않는다 —
이렇게 해야 미설치 환경에서도 validate_config.py의 import-only 검증
(load_plugin())이 실패하지 않고, 실제 처리 시점(_process)에서만 명확한
RuntimeError를 낸다.

[en]
lameenc/soundfile/numpy are required, but they are not force-imported at module
level — this way, load_plugin()'s import-only check in validate_config.py
still succeeds even without them installed, and only _process() raises a
clear RuntimeError at actual processing time.
"""
try:
    import lameenc as _lameenc
except ImportError:
    _lameenc = None

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import numpy as np
except ImportError:
    np = None

SUPPORTED_INPUT_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}

# [ko] MPEG-1 Layer III 표준 비트레이트(kbps). job의 preset UI가 128/192/256/320만 노출하지만,
#      단독 CLI/직접 호출 경로도 있으므로 전체 표준 집합으로 방어적으로 검증한다.
# [en] Standard MPEG-1 Layer III bitrates (kbps). The job's preset UI only exposes
#      128/192/256/320, but there's also a standalone CLI/direct-call path, so the
#      full standard set is validated defensively here.
_VALID_BITRATES = {32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320}


def is_supported_input(p: Path) -> bool:
    return p.suffix.lower() in SUPPORTED_INPUT_EXTS


def encode_mp3(input_path: Path, output_path: Path, bitrate: int) -> tuple[bool, str]:
    """
    [ko] input_path를 16-bit PCM으로 디코딩(soundfile)한 뒤 MP3로 인코딩(lameenc)해 output_path에 쓴다.
    [en] Decode input_path to 16-bit PCM (soundfile), encode it to MP3 (lameenc), and write it to output_path.
    """
    try:
        data, sample_rate = sf.read(str(input_path), dtype="int16", always_2d=True)
        n_channels = data.shape[1]
        if n_channels > 2:
            return False, f"unsupported channel count: {n_channels} (MP3 supports mono/stereo only)"

        encoder = _lameenc.Encoder()
        encoder.set_bit_rate(bitrate)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(n_channels)
        encoder.set_quality(2)  # [ko] 0(최고 품질/최저 속도) ~ 9(최저 품질/최고 속도) 중 2 — 사실상 최고 품질권 / [en] 0 (best quality/slowest) to 9 (worst quality/fastest) — 2 is effectively top-tier quality

        pcm_bytes = np.ascontiguousarray(data).tobytes()
        mp3_data = encoder.encode(pcm_bytes)
        mp3_data += encoder.flush()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(mp3_data)

        return True, ""
    except Exception as e:
        return False, f"Failed: {input_path} -> {e}"


# [ko] 플러그인 핵심 로직 — run()과 단독 CLI가 공유
# [en] Core plugin logic — shared by run() and the standalone CLI

def _process(input_path: str, output_path: str, params: dict) -> None:
    if _lameenc is None or sf is None or np is None:
        raise RuntimeError("mp3lame plugin requires lameenc, soundfile, numpy — pip install lameenc soundfile numpy")

    src, out = Path(input_path), Path(output_path)
    if not is_supported_input(src):
        raise ValueError(f"unsupported extension: {src.suffix}")

    bitrate = int(params.get("bitrate", 128))
    if bitrate not in _VALID_BITRATES:
        raise ValueError(f"bitrate must be one of {sorted(_VALID_BITRATES)} (got {bitrate})")

    ok, msg = encode_mp3(src, out, bitrate)
    if not ok:
        raise RuntimeError(msg)


@plugin(
    name="mp3lame",
    contract_version="1.0",
    version="1.0",
    author="Magnum Choi",
    session_type="file",
    requirements=["lameenc", "soundfile", "numpy"],
    notes_per_file=0,
    # [ko] lameenc.Encoder()를 파일마다 새로 생성하고 모듈 전역에 캐싱/공유하지 않으므로
    #      공유 가변 상태가 아예 없다 (상단 "테크니컬 노트", 플러그인 가이드 5.10절).
    # [en] A fresh lameenc.Encoder() is created per file and never cached/shared at
    #      module level, so there is no shared mutable state at all (see "Technical
    #      notes" above, plugin guide Section 5.10).
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
        print("Usage: python mp3lame.py <input> <output> [bitrate=128]")
        raise SystemExit(1)
    input_path, output_path, *rest = sys.argv[1:]
    raw = parse_params(rest)
    cli_params = {"bitrate": raw.get("bitrate", "128")}
    try:
        _process(input_path, output_path, cli_params)
        print(f"OK: {input_path}")
    except Exception as exc:
        print(f"FAILED: {input_path} -> {exc}")
        raise SystemExit(1)
