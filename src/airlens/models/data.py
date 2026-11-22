"""Memuat dataset hasil Fase 2 untuk pelatihan/evaluasi."""

from dataclasses import dataclass

import pandas as pd

from airlens.aqi import CATEGORIES
from airlens.data.manifest import read_data_version
from airlens.data.paths import DATA_DIR, processed_dir


@dataclass
class Dataset:
    frame: pd.DataFrame  # kolom penting: image_path (relatif DATA_DIR), split, label, y
    classes: list[str]
    data_version: str

    def split(self, name: str) -> pd.DataFrame:
        return self.frame[self.frame["split"] == name].reset_index(drop=True)

    @staticmethod
    def abs_path(rel: str) -> str:
        return str(DATA_DIR / rel)


from airlens.tiers import TIER_IDS, TIER_MERGE  # noqa: E402


def class_list(class_merge: dict[str, str]) -> list[str]:
    """Kelas akhir dalam urutan EPA, ditentukan dari config (bukan dari isi data) agar indeks kelas selalu tetap."""
    return list(dict.fromkeys(class_merge.get(c, c) for c in CATEGORIES))


def load_dataset(profile: str, class_merge: dict[str, str]) -> Dataset:
    out = processed_dir(profile)
    df = pd.read_parquet(out / "dataset.parquet")
    classes = class_list(class_merge)
    if "label_epa" in df:
        # dataset baru menyimpan kategori EPA asli: label selalu diturunkan dari situ sesuai skema yang diminta
        df["label"] = df["label_epa"].map(lambda v: class_merge.get(v, v))
    elif set(classes) <= set(TIER_IDS):
        # dataset lama ditulis dengan nama gabungan EPA (moderate/unhealthy/very_unhealthy); artinya sama dengan
        # tingkat baru, jadi cukup diganti nama (data_version tidak berubah). `make data` berikutnya menulis nama baru.
        df["label"] = df["label"].map(lambda v: TIER_MERGE.get(v, v))
    unknown = set(df["label"]) - set(classes)
    if unknown:
        raise ValueError(f"label {unknown} tidak ada di daftar kelas {classes}; jalankan ulang `make data`")
    df["y"] = df["label"].map({c: i for i, c in enumerate(classes)})
    return Dataset(frame=df, classes=classes, data_version=read_data_version(out))
