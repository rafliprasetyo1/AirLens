"""Split berdasarkan kelompok lokasi (bukan acak per gambar).

- Lokasi yang berdekatan (< GROUP_RADIUS_KM) digabung menjadi satu kelompok, sehingga stasiun di kota yang sama
  tidak terpecah ke dua split.
- Kelompok yang ditetapkan sebagai test penuh (mis. kota Dhaka) selalu masuk test.
- Kelompok lain diacak dengan seed lalu diisi ke test, validation, dan train sesuai porsi jumlah gambar.
Split dijalankan setelah dedup dan hanya pada wakil tiap kelompok duplikat. Dua gambar yang near-duplicate selalu
satu kelompok (union-find bersifat transitif), jadi paling banyak satu yang tersisa dan tidak ada duplikat lintas split.
"""


import numpy as np
import pandas as pd

from airlens.data.dedup import UnionFind

GROUP_RADIUS_KM = 25.0


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def location_groups(df: pd.DataFrame, radius_km: float = GROUP_RADIUS_KM) -> pd.Series:
    """Kelompok lokasi per baris. Butuh location_id, lat, lon, dan opsional group_hint (dipakai apa adanya)."""
    locs = df.groupby("location_id").agg(lat=("lat", "first"), lon=("lon", "first"))
    if "group_hint" in df:
        hints = df.groupby("location_id")["group_hint"].first()
    else:
        hints = pd.Series(None, index=locs.index, dtype=object)
    ids = locs.index.to_list()
    uf = UnionFind(len(ids))
    has_coord = locs["lat"].notna().to_numpy() & locs["lon"].notna().to_numpy()
    idx = np.flatnonzero(has_coord)
    lat, lon = locs["lat"].to_numpy()[idx], locs["lon"].to_numpy()[idx]
    for k, i in enumerate(idx):
        close = idx[k + 1 :][haversine_km(lat[k], lon[k], lat[k + 1 :], lon[k + 1 :]) < radius_km]
        for j in close:
            uf.union(i, j)
    hint_first: dict[str, int] = {}
    for i, loc in enumerate(ids):
        h = hints.get(loc)
        if isinstance(h, str):
            if h in hint_first:
                uf.union(hint_first[h], i)
            else:
                hint_first[h] = i
    group_of = {loc: f"g{uf.find(i):05d}" for i, loc in enumerate(ids)}
    return df["location_id"].map(group_of)


def assign_splits(
    df: pd.DataFrame,
    seed: int,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    forced_test_groups: frozenset[str] = frozenset(),
    label_col: str = "label",
) -> pd.Series:
    """Split per baris; seluruh kelompok `split_group` selalu masuk satu split.

    Penempatan terstratifikasi dan serakah: kelompok diurutkan dari terbesar (urutan seri diacak dengan seed),
    lalu tiap kelompok masuk ke split yang paling "kekurangan" kelas-kelas yang dibawanya, relatif terhadap target
    (porsi split x jumlah per kelas). Ini menghindari satu kota besar membuat suatu kelas hanya ada di satu split.
    Kelompok di forced_test_groups selalu masuk test dan dihitung lebih dulu.
    """
    fracs = {"train": 1.0 - val_frac - test_frac, "val": val_frac, "test": test_frac}
    counts = pd.crosstab(df["split_group"], df[label_col])
    target = {s: f * counts.sum(axis=0) for s, f in fracs.items()}
    filled = {s: pd.Series(0.0, index=counts.columns) for s in fracs}

    split_of: dict[str, str] = {}
    for g in counts.index:
        if g in forced_test_groups:
            split_of[g] = "test"
            filled["test"] += counts.loc[g]

    rng = np.random.default_rng(seed)
    rest = [g for g in counts.index if g not in forced_test_groups]
    tiebreak = dict(zip(rest, rng.permutation(len(rest))))
    rest.sort(key=lambda g: (-int(counts.loc[g].sum()), tiebreak[g]))
    for g in rest:
        c = counts.loc[g]

        def need(s: str) -> float:
            # Kekurangan relatif yang tersisa pada kelas-kelas milik kelompok ini (dibobot jumlahnya).
            deficit = ((target[s] - filled[s]) / target[s].clip(lower=1.0)).clip(lower=-1.0)
            return float((deficit * c).sum() / c.sum())

        best = max(fracs, key=lambda s: (need(s), fracs[s]))
        split_of[g] = best
        filled[best] += c
    return df["split_group"].map(split_of)
