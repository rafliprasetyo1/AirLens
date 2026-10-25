from datetime import datetime, time

import pytest

from airlens.data.sources import parse_dhaka_datetime


@pytest.mark.parametrize(
    "date_val,time_val,expected",
    [
        ("23.09.2020", "10.03AM", datetime(2020, 9, 23, 10, 3)),
        ("23.09.2020", "11.37 AM", datetime(2020, 9, 23, 11, 37)),
        ("23.09.2020", "12.34PM", datetime(2020, 9, 23, 12, 34)),
        ("23.09.2020", "12.05AM", datetime(2020, 9, 23, 0, 5)),
        ("01.07.2020", "3.15 PM", datetime(2020, 7, 1, 15, 15)),
        ("44832", "0.70903935185185185", datetime(2022, 9, 28, 17, 1)),  # serial Excel + pecahan hari
        (44832, 0.5, datetime(2022, 9, 28, 12, 0)),
        ("07.08.2020", time(18, 0), datetime(2020, 8, 7, 18, 0)),  # openpyxl membaca jam sebagai time
        (datetime(2018, 6, 18), time(12, 43), datetime(2018, 6, 18, 12, 43)),
        (datetime(2022, 4, 30), "\u200f\u200e12:36:44 PM", datetime(2022, 4, 30, 12, 36)),  # tanda arah + detik
        (datetime(2022, 5, 2), "4:44 PM\u200f\u200e", datetime(2022, 5, 2, 16, 44)),
        (datetime(2018, 6, 18), datetime(1900, 1, 1, 9, 49), datetime(2018, 6, 18, 9, 49)),
    ],
)
def test_dhaka_datetime_formats(date_val, time_val, expected):
    assert parse_dhaka_datetime(date_val, time_val) == expected


def test_dhaka_datetime_unknown_format_raises():
    with pytest.raises(ValueError):
        parse_dhaka_datetime("23.09.2020", "pagi")


def test_dhaka_missing_date_is_none():
    assert parse_dhaka_datetime(None, "10.03AM") is None


def test_sample_keeps_whole_groups_and_small_groups_can_be_chosen():
    import pandas as pd

    from airlens.data.sources import _sample

    # 50 kelompok kecil (2 gambar) + 1 kelompok besar (100 gambar).
    df = pd.DataFrame({"g": [f"s{i}" for i in range(50) for _ in range(2)] + ["big"] * 100, "x": range(200)})
    out = _sample(df, 0.2, seed=1, by="g")
    assert out["g"].nunique() == round(0.2 * 51)
    assert (out.groupby("g").size() == df[df["g"].isin(out["g"])].groupby("g").size()).all()  # kelompok utuh
    assert out["g"].str.startswith("s").any()  # kelompok kecil ikut terpilih
    assert _sample(df, 1.0, seed=1, by="g").equals(df)
