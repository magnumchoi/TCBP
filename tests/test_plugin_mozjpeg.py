"""
[ko]
plugin/mozjpeg.py의 _process() 직접 호출. jpeglib/numpy/Pillow가 없는
환경에서는 skip — @plugin(requirements=[...])로 선언만 하고 자동 설치는
하지 않는다는 정책(12.3)과 동일하게, 테스트도 미설치를 에러가 아니라
skip으로 취급한다.

[en]
Calls plugin/mozjpeg.py's _process() directly. Skipped in an environment
without jpeglib/numpy/Pillow — matching the policy (12.3) that
@plugin(requirements=[...]) only declares them and never auto-installs, this
test also treats them missing as a skip, not an error.
"""
import pytest

mozjpeg = pytest.importorskip("mozjpeg")
Image = pytest.importorskip("PIL.Image")

pytestmark = pytest.mark.skipif(
    mozjpeg.jpeglib is None or mozjpeg.np is None or mozjpeg.Image is None,
    reason="jpeglib/numpy/Pillow not installed",
)


def _make_png(path, color=(255, 0, 0), size=(32, 32)):
    Image.new("RGB", size, color).save(path)


def _make_jpg(path, color=(0, 255, 0), size=(32, 32), quality=90):
    Image.new("RGB", size, color).save(path, quality=quality)


def test_process_png_to_jpg(tmp_path):
    src = tmp_path / "in.png"
    out = tmp_path / "out.jpg"
    _make_png(src)
    mozjpeg._process(str(src), str(out), {"quality": 90})
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "JPEG"
        assert im.size == (32, 32)


def test_process_jpg_recompress(tmp_path):
    src = tmp_path / "in.jpg"
    out = tmp_path / "out.jpg"
    _make_jpg(src)
    mozjpeg._process(str(src), str(out), {"quality": 80})
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "JPEG"


def test_unsupported_extension_raises(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("not an image")
    with pytest.raises(ValueError):
        mozjpeg._process(str(src), str(tmp_path / "out.jpg"), {"quality": 90})


def test_quality_out_of_range_raises(tmp_path):
    src = tmp_path / "in.png"
    _make_png(src)
    with pytest.raises(ValueError):
        mozjpeg._process(str(src), str(tmp_path / "out.jpg"), {"quality": 150})


def test_run_returns_exec_result(tmp_path):
    from tcbp import FileSession

    src = tmp_path / "in.png"
    out = tmp_path / "out.jpg"
    _make_png(src)
    session = FileSession(input=str(src), output=str(out), itemid=1, taskid="t", params={"quality": 85})
    result = mozjpeg.run(session)
    assert result.success is True
    assert out.exists()
