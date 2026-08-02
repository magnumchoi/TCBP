"""
[ko]
plugin/bmp2png.py의 _process() 직접 호출. opencv-python/Pillow가 없는
환경에서는 bmp_to_png() 내부에서 각각 시도되므로, 최소 Pillow는 있어야
테스트가 의미가 있다 (없으면 skip).

[en]
Calls plugin/bmp2png.py's _process() directly. Without opencv-python/Pillow,
each is tried inside bmp_to_png() individually, so this test is only
meaningful with at least Pillow installed (skipped otherwise).
"""
import pytest

bmp2png = pytest.importorskip("bmp2png")
Image = pytest.importorskip("PIL.Image")


def _make_bmp(path, color=(10, 20, 30), size=(32, 32)):
    Image.new("RGB", size, color).save(path)


def test_process_converts_bmp_to_png(tmp_path):
    src = tmp_path / "in.bmp"
    out = tmp_path / "out.png"
    _make_bmp(src)
    notes = bmp2png._process(str(src), str(out), {})
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "PNG"
        assert im.size == (32, 32)
    assert isinstance(notes, list)


def test_process_with_delete_removes_original(tmp_path):
    src = tmp_path / "in.bmp"
    out = tmp_path / "out.png"
    _make_bmp(src)
    notes = bmp2png._process(str(src), str(out), {"delete": True})
    assert out.exists()
    assert not src.exists()
    assert "[source deleted]" in notes


def test_process_without_delete_keeps_original(tmp_path):
    src = tmp_path / "in.bmp"
    out = tmp_path / "out.png"
    _make_bmp(src)
    bmp2png._process(str(src), str(out), {"delete": False})
    assert src.exists()


def test_missing_oxipng_is_soft_failure_not_exception(tmp_path):
    src = tmp_path / "in.bmp"
    out = tmp_path / "out.png"
    _make_bmp(src)
    notes = bmp2png._process(str(src), str(out), {"oxipng_exe": str(tmp_path / "nonexistent.exe")})
    assert out.exists()  # [ko] PNG는 만들어짐 — 최적화만 스킵 / [en] the PNG is still created — only optimization is skipped
    assert any("oxipng.exe not found" in n for n in notes)


def test_resolve_oxipng_exe_defaults_to_bundled():
    resolved = bmp2png._resolve_oxipng_exe({})
    assert resolved == str(bmp2png._BUNDLED_OXIPNG)


def test_run_returns_exec_result(tmp_path):
    from tcbp import FileSession

    src = tmp_path / "in.bmp"
    out = tmp_path / "out.png"
    _make_bmp(src)
    session = FileSession(input=str(src), output=str(out), itemid=1, taskid="t", params={"delete": False})
    result = bmp2png.run(session)
    assert result.success is True
    assert out.exists()
