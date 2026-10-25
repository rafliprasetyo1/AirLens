"""Bukti tidak ada kebocoran pada split yang SEBENARNYA (data/processed/<profil>/dataset.parquet).

Dilewati bila `make data` belum dijalankan untuk profil itu. Pemeriksaan near-duplicate dihitung ulang langsung dari
pHash/dHash, tidak bergantung pada hasil clustering di pipeline.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from airlens.data.dedup import DHASH_GLOBAL, PHASH_GLOBAL, hamming_matrix

PROCESSED = Path("/app/data/processed")
PROFILES = sorted(p.name for p in PROCESSED.glob("*") if (p / "dataset.parquet").exists()) if PROCESSED.exists() else []

pytestmark = pytest.mark.skipif(not PROFILES, reason="belum ada data/processed; jalankan `make data`")


@pytest.fixture(params=PROFILES)
def dataset(request):
    return pd.read_parquet(PROCESSED / request.param / "dataset.parquet")


def test_every_image_in_exactly_one_split(dataset):
    assert dataset["image_path"].is_unique
    assert set(dataset["split"]) <= {"train", "val", "test"}


def test_no_identical_file_in_two_splits(dataset):
    assert (dataset.groupby("sha256")["split"].nunique() == 1).all()
    assert dataset["sha256"].is_unique  # dedup: tidak ada salinan persis sama sekali


def test_no_location_in_two_splits(dataset):
    assert (dataset.groupby("location_id")["split"].nunique() == 1).all()
    assert (dataset.groupby("split_group")["split"].nunique() == 1).all()


def test_no_near_duplicate_across_splits(dataset):
    splits = {s: g for s, g in dataset.groupby("split")}
    names = sorted(splits)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pa, pb = splits[a]["phash"].to_numpy(np.uint64), splits[b]["phash"].to_numpy(np.uint64)
            da, db = splits[a]["dhash"].to_numpy(np.uint64), splits[b]["dhash"].to_numpy(np.uint64)
            for start in range(0, len(pa), 1024):
                hit = (hamming_matrix(pa[start : start + 1024], pb) <= PHASH_GLOBAL) & (
                    hamming_matrix(da[start : start + 1024], db) <= DHASH_GLOBAL
                )
                assert not hit.any(), f"near-duplicate antara {a} dan {b}"


def test_forced_test_city_only_in_test(dataset):
    dhaka = dataset[dataset["source"] == "dhaka"]
    assert set(dhaka["split"]) <= {"test"}


def test_labels_are_epa_2024_categories(dataset):
    from airlens.aqi import CATEGORIES

    assert set(dataset["label"]) <= set(CATEGORIES)
