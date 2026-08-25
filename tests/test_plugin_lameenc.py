"""
[ko]
plugin/mp3lame.py의 _process() 직접 호출. lameenc/soundfile/numpy가 없는
환경에서는 skip — @plugin(requirements=[...])로 선언만 하고 자동 설치는
하지 않는다는 정책(12.3)과 동일하게, 테스트도 미설치를 에러가 아니라
skip으로 취급한다.

파일명은 mp3lame이지만(플러그인 파일이 pip 패키지 lameenc와의 이름 충돌을
피하려고 그렇게 이름 붙였다 — plugin/mp3lame.py의 모듈 docstring 참고),
이 테스트 파일 자체는 다른 플러그인 테스트들과의 명명 규칙(test_plugin_<이름>.py)
대신 원래 요청한 이름(lameenc)을 그대로 유지한다.

[en]
Calls plugin/mp3lame.py's _process() directly. Skipped in an environment
without lameenc/soundfile/numpy — matching the policy (12.3) that
@plugin(requirements=[...]) only declares them and never auto-installs, this
test also treats them missing as a skip, not an error.

The file is named mp3lame (the plugin file itself is named that way to avoid
a name collision with the pip package `lameenc` — see plugin/mp3lame.py's
module docstring), but this test file keeps the originally-requested name
(lameenc) rather than following the other plugins' test_plugin_<name>.py
convention.
"""
import numpy as np
import pytest

mp3lame = pytest.importorskip("mp3lame")

pytestmark = pytest.mark.skipif(
    mp3lame._lameenc is None or mp3lame.sf is None or mp3lame.np is None,
    reason="lameenc/soundfile/numpy not installed",
)


def _make_wav(path, seconds=0.25, sr=44100, channels=2, freq=440):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    tone = (np.sin(2 * np.pi * freq * t) * 20000).astype(np.int16)
    data = np.tile(tone[:, None], (1, channels)) if channels > 1 else tone
    mp3lame.sf.write(str(path), data, sr, subtype="PCM_16")


def _make_flac(path, seconds=0.25, sr=44100, channels=1, freq=440):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    tone = (np.sin(2 * np.pi * freq * t) * 20000).astype(np.int16)
    data = np.tile(tone[:, None], (1, channels)) if channels > 1 else tone
    mp3lame.sf.write(str(path), data, sr, subtype="PCM_16", format="FLAC")


def test_process_wav_stereo_to_mp3(tmp_path):
    src = tmp_path / "in.wav"
    out = tmp_path / "out.mp3"
    _make_wav(src, channels=2)
    mp3lame._process(str(src), str(out), {"bitrate": 128})
    assert out.exists()
    data, sr = mp3lame.sf.read(str(out))
    assert sr == 44100
    assert data.ndim == 2 and data.shape[1] == 2


def test_process_wav_mono_to_mp3(tmp_path):
    src = tmp_path / "in.wav"
    out = tmp_path / "out.mp3"
    _make_wav(src, channels=1)
    mp3lame._process(str(src), str(out), {"bitrate": 128})
    assert out.exists()


def test_process_flac_to_mp3(tmp_path):
    src = tmp_path / "in.flac"
    out = tmp_path / "out.mp3"
    _make_flac(src)
    mp3lame._process(str(src), str(out), {"bitrate": 192})
    assert out.exists()
    assert out.stat().st_size > 0


def test_unsupported_extension_raises(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("not audio")
    with pytest.raises(ValueError):
        mp3lame._process(str(src), str(tmp_path / "out.mp3"), {"bitrate": 128})


def test_invalid_bitrate_raises(tmp_path):
    src = tmp_path / "in.wav"
    _make_wav(src)
    with pytest.raises(ValueError):
        mp3lame._process(str(src), str(tmp_path / "out.mp3"), {"bitrate": 123})


def test_unsupported_channel_count_raises(tmp_path):
    src = tmp_path / "in.wav"
    _make_wav(src, channels=3)
    with pytest.raises(RuntimeError):
        mp3lame._process(str(src), str(tmp_path / "out.mp3"), {"bitrate": 128})


def test_run_returns_exec_result(tmp_path):
    from tcbp import FileSession

    src = tmp_path / "in.wav"
    out = tmp_path / "out.mp3"
    _make_wav(src)
    session = FileSession(input=str(src), output=str(out), itemid=1, taskid="t", params={"bitrate": 128})
    result = mp3lame.run(session)
    assert result.success is True
    assert out.exists()
