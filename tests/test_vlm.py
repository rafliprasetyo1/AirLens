from airlens.models import vlm

CLASSES = ["good", "moderate", "usg", "unhealthy", "very_unhealthy"]


def test_skipped_when_url_empty():
    r = vlm.classify(["/tidak/ada.jpg"], CLASSES, base_url="")
    assert r["status"] == "dilewati" and "kosong" in r["reason"]


def test_skipped_when_unreachable():
    r = vlm.classify(["/tidak/ada.jpg"], CLASSES, base_url="http://127.0.0.1:9/v1")
    assert r["status"] == "dilewati" and "tidak terjangkau" in r["reason"]


def test_parse_category():
    assert vlm.parse_category('{"category": "usg", "reason": "kabut"}', CLASSES) == "usg"
    assert vlm.parse_category('{"category": "hazardous"}', CLASSES) is None  # bukan kelas akhir
    assert vlm.parse_category("bukan json", CLASSES) is None
