"""Skema tiga tingkat (Low / Elevated / High): pemetaan kelas lama -> baru, saran per tingkat, pemetaan AQI IQAir ->
tingkat (batas 100/101 dan 200/201), tampilan API untuk model baru, model 3 kelas lama, dan model 5 kelas
(kompatibilitas rollback), serta promote yang menganggap nama lama dan baru sebagai skema yang sama."""

import pytest

from airlens.aqi import CATEGORIES
from airlens.tiers import (LEGACY_NAMES, SCHEME, TIER_IDS, TIER_MERGE, TIERS, aqi_to_tier, is_legacy_three_class,
                           normalize_classes, tier_of, tier_view)
from airlens_api.pipeline import PredictionPipeline, class_ranges

LEGACY = ["moderate", "unhealthy", "very_unhealthy"]
LEGACY_MERGE = {"good": "moderate", "usg": "unhealthy", "hazardous": "very_unhealthy"}
FIVE = ["good", "moderate", "usg", "unhealthy", "very_unhealthy"]
FIVE_MERGE = {"hazardous": "very_unhealthy"}


def test_merge_covers_every_epa_category_in_order():
    assert set(TIER_MERGE) == set(CATEGORIES)
    order = [TIER_IDS.index(TIER_MERGE[c]) for c in CATEGORIES]
    assert order == sorted(order)                       # urutan EPA terjaga
    assert [TIERS[t]["epa"] for t in TIER_IDS] == [("good", "moderate"), ("usg", "unhealthy"), ("very_unhealthy", "hazardous")]


@pytest.mark.parametrize("aqi,tier", [(0, "low"), (100, "low"), (101, "elevated"), (150, "elevated"), (200, "elevated"),
                                      (201, "high"), (300, "high"), (301, "high"), (612, "high")])
def test_iqair_aqi_to_tier_boundaries(aqi, tier):
    assert aqi_to_tier(aqi) == tier


def test_labels_and_advice_per_tier():
    assert [TIERS[t]["label_en"] for t in TIER_IDS] == ["Low", "Elevated", "High"]
    assert [TIERS[t]["label_id"] for t in TIER_IDS] == ["Rendah", "Meningkat", "Tinggi"]
    assert "seperti biasa" in TIERS["low"]["advice_id"]
    assert "Kelompok sensitif" in TIERS["elevated"]["advice_id"] and "membatasi" in TIERS["elevated"]["advice_id"]
    assert "Semua orang menghindari" in TIERS["high"]["advice_id"] and "tetap di dalam" in TIERS["high"]["advice_id"]
    v = tier_view("elevated")
    assert v["label"] == "Meningkat" and v["label_en"] == "Elevated" and v["aqi_range"] == [101, 200] and v["scheme"] == SCHEME


def test_legacy_names_map_to_new_tiers():
    assert LEGACY_NAMES == {"moderate": "low", "unhealthy": "elevated", "very_unhealthy": "high"}
    assert is_legacy_three_class(LEGACY, LEGACY_MERGE) and is_legacy_three_class(LEGACY, None)
    assert not is_legacy_three_class(FIVE, FIVE_MERGE)
    assert [tier_of(c, LEGACY, LEGACY_MERGE) for c in LEGACY] == ["low", "elevated", "high"]
    assert tier_of("moderate", FIVE, FIVE_MERGE) is None          # 5 kelas: tetap kategori EPA
    assert tier_of("high", list(TIER_IDS), TIER_MERGE) == "high"
    # nama EPA dan nama lama sama-sama dipetakan TIER_MERGE ke tingkat yang sama (dipakai data lama + compare_merge)
    assert all(TIER_MERGE[c] == t for c, t in LEGACY_NAMES.items())


def test_promote_treats_legacy_and_new_names_as_same_scheme():
    assert normalize_classes(LEGACY, LEGACY_MERGE) == normalize_classes(list(TIER_IDS), TIER_MERGE)
    assert normalize_classes(FIVE, FIVE_MERGE) != normalize_classes(list(TIER_IDS), TIER_MERGE)


@pytest.mark.parametrize("classes,merge,cat,label,rng", [
    (list(TIER_IDS), TIER_MERGE, "elevated", "Meningkat", [101, 200]),          # model baru
    (LEGACY, LEGACY_MERGE, "unhealthy", "Meningkat", [101, 200]),               # model 3 kelas lama (rollback)
    (LEGACY, LEGACY_MERGE, "very_unhealthy", "Tinggi", [201, 500]),
    (FIVE, FIVE_MERGE, "usg", "Tidak sehat bagi kelompok sensitif", [101, 150]),  # model 5 kelas: kategori EPA
])
def test_api_category_view_for_new_legacy_and_five_class_models(classes, merge, cat, label, rng):
    view = PredictionPipeline._category_view(None, cat, classes, merge)
    assert view["key"] == cat and view["label"] == label and view["aqi_range"] == rng
    assert view["advice"] and view["color"].startswith("#")
    assert class_ranges(classes, merge)[cat] == tuple(rng)


def test_iqair_comparison_uses_tier_ranges():
    """AQI IQAir dipetakan lewat skema model: 150 -> elevated (model baru) atau unhealthy (model lama), sama tingkatnya."""
    from airlens.aqi import aqi_to_category

    for classes, merge in ((list(TIER_IDS), TIER_MERGE), (LEGACY, LEGACY_MERGE)):
        cats = [merge.get(aqi_to_category(a), aqi_to_category(a)) for a in (100, 101, 200, 201)]
        assert [classes.index(c) for c in cats] == [0, 1, 1, 2]
