"""Deduplikasi sebelum split: duplikat persis (sha256 isi file) dan near-duplicate (pHash + dHash).

Near-duplicate = jarak Hamming pHash <= ambang DAN dHash <= ambang. Ambang lebih longgar berlaku untuk pasangan
di lokasi yang sama (frame hampir sama dari kamera/lokasi sama). Pasangan dikelompokkan dengan union-find;
satu wakil per kelompok dipertahankan.
"""

import hashlib

import imagehash
import numpy as np
import pandas as pd

from airlens.data.quality import load_rgb

PHASH_GLOBAL = 4
DHASH_GLOBAL = 6
PHASH_SAME_LOCATION = 10
DHASH_SAME_LOCATION = 12


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def perceptual_hashes(path) -> tuple[int, int]:
    img = load_rgb(path)
    return int(str(imagehash.phash(img)), 16), int(str(imagehash.dhash(img)), 16)


def hamming_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.bitwise_count(a[:, None] ^ b[None, :])


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def near_duplicate_pairs(phash: np.ndarray, dhash: np.ndarray, location: np.ndarray, block: int = 2048):
    """Semua pasangan (i, j), i < j, yang near-duplicate. Dihitung per blok agar memori tetap kecil."""
    n = len(phash)
    for start in range(0, n, block):
        stop = min(start + block, n)
        dp = hamming_matrix(phash[start:stop], phash)
        dd = hamming_matrix(dhash[start:stop], dhash)
        same_loc = location[start:stop, None] == location[None, :]
        hit = ((dp <= PHASH_GLOBAL) & (dd <= DHASH_GLOBAL)) | (
            same_loc & (dp <= PHASH_SAME_LOCATION) & (dd <= DHASH_SAME_LOCATION)
        )
        rows, cols = np.nonzero(hit)
        rows = rows + start
        keep = rows < cols
        yield from zip(rows[keep].tolist(), cols[keep].tolist())


def assign_duplicate_clusters(df: pd.DataFrame) -> pd.DataFrame:
    """Butuh kolom sha256, phash, dhash, location_id, quality_rank (kecil = lebih baik).

    Menambah kolom dup_cluster (id kelompok) dan is_duplicate (bukan wakil kelompok), dup_kind (exact/near).
    """
    df = df.reset_index(drop=True).copy()
    uf = UnionFind(len(df))
    kind = np.array([None] * len(df), dtype=object)

    for _, idx in df.groupby("sha256").groups.items():
        idx = list(idx)
        for j in idx[1:]:
            uf.union(idx[0], j)
            kind[j] = "exact"

    phash = df["phash"].to_numpy(dtype=np.uint64)
    dhash = df["dhash"].to_numpy(dtype=np.uint64)
    location = df["location_id"].to_numpy()
    for i, j in near_duplicate_pairs(phash, dhash, location):
        uf.union(i, j)

    df["dup_cluster"] = [uf.find(i) for i in range(len(df))]
    order = df.sort_values(["dup_cluster", "quality_rank", "image_path"]).index
    first = df.loc[order].groupby("dup_cluster").head(1).index
    df["is_duplicate"] = ~df.index.isin(first)
    df["dup_kind"] = np.where(df["is_duplicate"], np.where(pd.notna(kind), kind, "near"), None)
    return df
