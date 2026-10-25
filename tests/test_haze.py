import numpy as np
from PIL import Image

from airlens.features.haze import FEATURE_NAMES, haze_features


def _scene(haze: float) -> Image.Image:
    rng = np.random.default_rng(0)
    clear = np.zeros((200, 300, 3))
    clear[:80] = [90, 140, 220]  # langit biru
    clear[80:] = rng.integers(10, 160, size=(120, 300, 3))  # bangunan/jalan bertekstur
    airlight = np.full_like(clear, 200.0)
    return Image.fromarray((clear * (1 - haze) + airlight * haze).astype(np.uint8))


def test_all_features_present_and_finite():
    f = haze_features(_scene(0.2))
    assert list(f) == list(FEATURE_NAMES)
    assert all(np.isfinite(v) for v in f.values())


def test_haze_raises_dark_channel_and_lowers_contrast_and_saturation():
    clear, hazy = haze_features(_scene(0.0)), haze_features(_scene(0.7))
    assert hazy["dark_mean"] > clear["dark_mean"]
    assert hazy["transmission_mean"] < clear["transmission_mean"]
    assert hazy["contrast_rms"] < clear["contrast_rms"]
    assert hazy["sat_mean"] < clear["sat_mean"]
    assert hazy["sky_blue_ratio"] < clear["sky_blue_ratio"]
