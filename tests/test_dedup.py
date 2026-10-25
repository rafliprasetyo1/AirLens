import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance

from airlens.data.dedup import assign_duplicate_clusters, perceptual_hashes, sha256_file


def _scene(seed):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, size=(8, 8, 3)).astype(np.uint8)
    return Image.fromarray(base).resize((256, 256), Image.BILINEAR)


def _row(path, location, rank=0):
    p, d = perceptual_hashes(path)
    return {"image_path": str(path), "sha256": sha256_file(path), "phash": p, "dhash": d, "location_id": location, "quality_rank": rank}


def test_exact_near_and_distinct(tmp_path):
    a = tmp_path / "a.png"; _scene(1).save(a)
    a_copy = tmp_path / "a_copy.png"; a_copy.write_bytes(a.read_bytes())
    a_jpeg = tmp_path / "a.jpg"; ImageEnhance.Brightness(_scene(1)).enhance(1.05).save(a_jpeg, quality=70)
    b = tmp_path / "b.png"; _scene(2).save(b)
    df = pd.DataFrame([_row(a, "L1", 0), _row(a_copy, "L1", 1), _row(a_jpeg, "L2", 2), _row(b, "L1", 3)])
    out = assign_duplicate_clusters(df).set_index("image_path")
    assert out.loc[str(a), "is_duplicate"] == False  # noqa: E712  wakil (quality_rank terkecil)
    assert out.loc[str(a_copy), "dup_kind"] == "exact"
    assert out.loc[str(a_jpeg), "dup_kind"] == "near"  # lokasi beda pun tetap terdeteksi (ambang global)
    assert out.loc[str(b), "is_duplicate"] == False  # noqa: E712
    assert out.loc[str(a), "dup_cluster"] == out.loc[str(a_jpeg), "dup_cluster"] != out.loc[str(b), "dup_cluster"]


def test_transitive_clusters_keep_one():
    # a~b dan b~c (lokasi sama) => satu kelompok walau a dan c berjauhan.
    df = pd.DataFrame({
        "image_path": ["a", "b", "c"], "sha256": ["1", "2", "3"],
        "phash": [0b0, 0b1111111, 0b11111111111111], "dhash": [0, 0, 0],
        "location_id": ["L", "L", "L"], "quality_rank": [0, 1, 2],
    })
    out = assign_duplicate_clusters(df)
    assert out["dup_cluster"].nunique() == 1
    assert out["is_duplicate"].sum() == 2
