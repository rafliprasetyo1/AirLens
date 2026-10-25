import pandas as pd

from airlens.data.split import assign_splits, location_groups


def _df():
    rows = []
    # Dua stasiun berdekatan (~5 km) di kota A, satu stasiun jauh di kota B, banyak stasiun lain.
    coords = {"A1": (28.60, 77.20), "A2": (28.64, 77.22), "B1": (19.0, 72.8)}
    coords.update({f"S{i}": (i * 1.0, 10.0 + i) for i in range(30)})
    for loc, (lat, lon) in coords.items():
        for k in range(10):
            rows.append({"image_path": f"{loc}_{k}", "location_id": loc, "lat": lat, "lon": lon, "label": ("good", "usg")[k % 2]})
    rows += [{"image_path": f"D_{k}", "location_id": f"dhaka:{k % 3}", "lat": None, "lon": None, "group_hint": "dhaka",
              "label": "unhealthy"} for k in range(30)]
    return pd.DataFrame(rows)


def test_nearby_locations_grouped_and_hint_respected():
    df = _df()
    g = location_groups(df).set_axis(df["location_id"]).groupby(level=0).first()
    assert g["A1"] == g["A2"] != g["B1"]
    assert g["dhaka:0"] == g["dhaka:1"] == g["dhaka:2"]


def test_no_group_in_two_splits_and_forced_test():
    df = _df()
    df["split_group"] = location_groups(df)
    dhaka_group = df.loc[df["location_id"] == "dhaka:0", "split_group"].iloc[0]
    df["split"] = assign_splits(df, seed=42, forced_test_groups=frozenset({dhaka_group}))
    assert (df.groupby("split_group")["split"].nunique() == 1).all()
    assert set(df.loc[df["split_group"] == dhaka_group, "split"]) == {"test"}
    assert set(df["split"]) == {"train", "val", "test"}


def test_split_deterministic():
    df = _df()
    df["split_group"] = location_groups(df)
    a = assign_splits(df, seed=7)
    b = assign_splits(df, seed=7)
    assert a.equals(b)


def test_stratified_assignment_spreads_rare_class():
    # Satu kota besar penuh kelas "hazardous" + kota kecil lain yang juga memuat hazardous:
    # kelas itu tidak boleh menumpuk di satu split saja.
    rows = []
    for i in range(40):
        lab = "hazardous" if i % 8 == 0 else ("good" if i % 2 else "moderate")
        for k in range(10):
            rows.append({"image_path": f"S{i}_{k}", "split_group": f"g{i}", "label": lab})
    rows += [{"image_path": f"BIG_{k}", "split_group": "gbig", "label": "hazardous"} for k in range(60)]
    df = pd.DataFrame(rows)
    df["split"] = assign_splits(df, seed=3)
    per = df[df["label"] == "hazardous"].groupby("split").size()
    assert set(per.index) == {"train", "val", "test"}
    assert per["train"] >= per.drop("train").max()
    assert (df.groupby("split_group")["split"].nunique() == 1).all()
