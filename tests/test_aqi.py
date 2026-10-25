import pytest

from airlens.aqi import (
    CATEGORIES,
    aqi_to_category,
    aqi_to_pm25,
    pm25_to_aqi,
    pm25_to_category,
    truncate_pm25,
)

# Batas tiap kategori (tabel 2024, EPA-454/B-24-002 Table 6): nilai tepat di batas atas dan batas bawah berikutnya.
BOUNDARIES_2024 = [
    (0.0, "good"), (9.0, "good"),
    (9.1, "moderate"), (35.4, "moderate"),
    (35.5, "usg"), (55.4, "usg"),
    (55.5, "unhealthy"), (125.4, "unhealthy"),
    (125.5, "very_unhealthy"), (225.4, "very_unhealthy"),
    (225.5, "hazardous"), (500.0, "hazardous"),
]


@pytest.mark.parametrize("conc,expected", BOUNDARIES_2024)
def test_category_boundaries_2024(conc, expected):
    assert pm25_to_category(conc) == expected


@pytest.mark.parametrize("conc,expected", [(9.09, "good"), (35.49, "moderate"), (55.49, "usg"), (125.49, "unhealthy"), (225.49, "very_unhealthy")])
def test_truncation_keeps_lower_category(conc, expected):
    # 9.09 dipotong menjadi 9.0, bukan dibulatkan ke 9.1.
    assert pm25_to_category(conc) == expected


@pytest.mark.parametrize(
    "conc,aqi",
    [(0.0, 0), (9.0, 50), (9.1, 51), (35.4, 100), (35.5, 101), (55.4, 150), (55.5, 151),
     (125.4, 200), (125.5, 201), (225.4, 300), (225.5, 301), (325.4, 500)],
)
def test_aqi_index_at_breakpoints_2024(conc, aqi):
    assert pm25_to_aqi(conc) == aqi


def test_aqi_index_interpolation_and_extrapolation():
    assert pm25_to_aqi(20.0) == 71  # (100-51)/(35.4-9.1)*(20-9.1)+51 = 71.31
    assert pm25_to_aqi(400.0) > 500


def test_old_2012_table_differs_where_expected():
    assert pm25_to_category(10.0, table=2012) == "good"
    assert pm25_to_category(10.0) == "moderate"
    assert pm25_to_category(140.0, table=2012) == "unhealthy"
    assert pm25_to_category(140.0) == "very_unhealthy"


@pytest.mark.parametrize("aqi,conc", [(0, 0.0), (50, 12.0), (51, 12.1), (100, 35.4), (101, 35.5), (150, 55.4), (200, 150.4), (300, 250.4), (400, 350.4), (500, 500.4)])
def test_inverse_2012_hits_breakpoints(aqi, conc):
    assert aqi_to_pm25(aqi, table=2012) == pytest.approx(conc)


@pytest.mark.parametrize("conc", [3.3, 12.0, 20.0, 47.7, 99.9, 180.0, 300.0])
def test_inverse_roundtrip_2012(conc):
    # AQI dibulatkan ke bilangan bulat, jadi balikannya mendekati, tidak persis.
    assert aqi_to_pm25(pm25_to_aqi(conc, table=2012), table=2012) == pytest.approx(conc, abs=1.1)


def test_aqi_to_category_index_limits():
    assert [aqi_to_category(i) for i in (50, 51, 100, 101, 150, 151, 200, 201, 300, 301)] == [
        "good", "moderate", "moderate", "usg", "usg", "unhealthy", "unhealthy", "very_unhealthy", "very_unhealthy", "hazardous",
    ]


def test_truncate_is_exact_for_decimal_inputs():
    assert truncate_pm25(35.5) == 35.5
    assert truncate_pm25(35.49999) == 35.4


@pytest.mark.parametrize("bad", [-1.0, float("nan"), None])
def test_invalid_concentration_rejected(bad):
    with pytest.raises(ValueError):
        pm25_to_category(bad)


def test_categories_ordered():
    assert CATEGORIES[0] == "good" and CATEGORIES[-1] == "hazardous" and len(CATEGORIES) == 6
