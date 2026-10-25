import numpy as np
from PIL import Image

from airlens.data.quality import assess


def _save(tmp_path, name, arr):
    p = tmp_path / name
    Image.fromarray(arr.astype(np.uint8)).save(p)
    return p


def _outdoor(h=240, w=320):
    # Langit terang dan halus di atas, tanah lebih gelap bertekstur di bawah.
    rng = np.random.default_rng(0)
    img = np.zeros((h, w, 3))
    img[: h // 2] = [170, 190, 215]
    img[h // 2 :] = rng.integers(40, 120, size=(h - h // 2, w, 3))
    return img


def test_normal_outdoor_passes(tmp_path):
    assert assess(_save(tmp_path, "ok.png", _outdoor()))["reject_reason"] is None


def test_dark_rejected(tmp_path):
    assert assess(_save(tmp_path, "dark.png", _outdoor() * 0.15))["reject_reason"] == "terlalu_gelap"


def test_overexposed_rejected(tmp_path):
    assert assess(_save(tmp_path, "bright.png", np.full((240, 320, 3), 252)))["reject_reason"] == "terlalu_terang"


def test_night_by_hour(tmp_path):
    assert assess(_save(tmp_path, "n.png", _outdoor()), hour=21)["reject_reason"] == "malam"


def test_small_rejected(tmp_path):
    assert assess(_save(tmp_path, "s.png", _outdoor(60, 80)))["reject_reason"] == "terlalu_kecil"


def test_no_sky_rejected(tmp_path):
    rng = np.random.default_rng(1)
    busy = rng.integers(0, 255, size=(240, 320, 3))  # tekstur tinggi di seluruh bingkai
    assert assess(_save(tmp_path, "busy.png", busy))["reject_reason"] == "langit_tidak_terlihat"


def test_corrupt_rejected(tmp_path):
    p = tmp_path / "broken.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0 bukan jpeg")
    assert assess(p)["reject_reason"] == "rusak"
