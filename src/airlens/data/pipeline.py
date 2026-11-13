"""Pipeline data lengkap. Jalankan di container trainer: `make data PROFILE=laptop|lab`.

Urutan: unduh -> normalisasi -> statistik kualitas + hash -> dedup -> filter kualitas -> distribusi -> split
-> manifest + laporan. Penggabungan kelas hanya diterapkan bila `data.class_merge` di config diisi (butuh persetujuan).
"""

import argparse
import json
import logging
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from airlens.aqi import AQI_TABLE_VERSION, CATEGORIES
from airlens.config import load_profile
from airlens.data import download, sources
from airlens.data.dedup import assign_duplicate_clusters, perceptual_hashes, sha256_file
from airlens.data.grids import save_grid
from airlens.data.manifest import write_manifest
from airlens.data.paths import DATA_DIR, RESULTS_DIR, processed_dir
from airlens.data.quality import assess
from airlens.data.split import assign_splits, location_groups

logger = logging.getLogger("airlens.data.pipeline")

DOWNLOADERS = {
    "pm25vision": download.download_pm25vision,
    "india_nepal": download.download_india_nepal,
    "dhaka": download.download_dhaka,
}
LOADERS = {
    "pm25vision": sources.load_pm25vision,
    "india_nepal": sources.load_india_nepal,
    "dhaka": sources.load_dhaka,
}


def _image_features(args: tuple[str, int | None]) -> dict:
    rel, hour = args
    path = DATA_DIR / rel
    out = assess(path, hour)
    if out["reject_reason"] == "rusak":
        out.update(sha256=sha256_file(path) if path.exists() else None, phash=None, dhash=None)
    else:
        p, d = perceptual_hashes(path)
        out.update(sha256=sha256_file(path), phash=p, dhash=d)
    return out


def compute_features(df: pd.DataFrame, workers: int) -> pd.DataFrame:
    hours = [None if pd.isna(h) else int(h) for h in df["hour"]]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        feats = list(pool.map(_image_features, zip(df["image_path"], hours), chunksize=64))
    feats = pd.DataFrame(feats, index=df.index)
    # pHash/dHash 64-bit tak bertanda; simpan sebagai uint64.
    for col in ("phash", "dhash"):
        feats[col] = feats[col].astype("UInt64")
    return df.join(feats)


def count_by(df: pd.DataFrame, *cols: str) -> dict:
    return {" / ".join(map(str, k)) if isinstance(k, tuple) else str(k): int(v) for k, v in df.groupby(list(cols)).size().items()}


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def run(profile_name: str | None, skip_download: bool) -> dict:
    cfg = load_profile(profile_name)
    profile, dcfg = cfg["profile"], cfg["data"]
    seed, fraction = dcfg["seed"], cfg["training"]["data_fraction"]
    # Darurat: AIRLENS_DATA_SOURCES=pm25vision,india_nepal (mis. unduhan Dhaka terlalu lambat di lab). Sumber yang
    # benar-benar dipakai tercatat di report.json dan MLflow, jadi tidak tersembunyi.
    override = [n.strip() for n in os.environ.get("AIRLENS_DATA_SOURCES", "").split(",") if n.strip()]
    unknown = set(override) - set(DOWNLOADERS)
    if unknown:
        raise ValueError(f"AIRLENS_DATA_SOURCES berisi sumber tak dikenal: {sorted(unknown)}")
    names = override or dcfg["sources"]
    if override:
        logger.warning("sumber data diganti lewat AIRLENS_DATA_SOURCES: %s (config: %s)", names, dcfg["sources"])
    out_dir = processed_dir(profile)
    grid_dir = RESULTS_DIR / "data" / profile
    report: dict = {"profile": profile, "sources": names, "data_fraction": fraction, "aqi_table": AQI_TABLE_VERSION}

    if not skip_download:
        for name in names:
            logger.info("unduh %s", name)
            DOWNLOADERS[name]()

    frames = []
    report["dibuang_saat_normalisasi"] = {}
    for name in names:
        logger.info("normalisasi %s", name)
        frame = LOADERS[name](fraction=fraction, seed=seed)
        report["dibuang_saat_normalisasi"][name] = frame.attrs.get("dibuang", {})
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    report["n_raw"] = count_by(df, "source")

    logger.info("statistik kualitas + hash untuk %d gambar", len(df))
    df = compute_features(df, workers=cfg["training"]["num_workers"])

    # Dedup di antara gambar yang bisa dibaca. Wakil kelompok = yang lolos filter kualitas, lalu resolusi terbesar.
    readable = df[df["reject_reason"] != "rusak"].copy()
    readable["quality_rank"] = readable["reject_reason"].notna().astype(int) * 10**9 - (
        readable["width"].fillna(0) * readable["height"].fillna(0)
    )
    deduped = assign_duplicate_clusters(readable)
    df = df.merge(deduped[["image_path", "dup_cluster", "is_duplicate", "dup_kind"]], on="image_path", how="left")
    df["is_duplicate"] = df["is_duplicate"].fillna(False).astype(bool)
    report["dedup"] = {
        name: {
            "sebelum": int((g["reject_reason"] != "rusak").sum()),
            "duplikat_persis": int((g["dup_kind"] == "exact").sum()),
            "near_duplicate": int((g["dup_kind"] == "near").sum()),
            "sesudah": int(((g["reject_reason"] != "rusak") & ~g["is_duplicate"]).sum()),
        }
        for name, g in df.groupby("source")
    }
    dup_pairs = df[df["is_duplicate"]].merge(
        df[~df["is_duplicate"]][["dup_cluster", "image_path"]], on="dup_cluster", suffixes=("", "_wakil")
    )
    save_grid(
        [(DATA_DIR / r.image_path_wakil, DATA_DIR / r.image_path, f"{r.dup_kind}") for r in dup_pairs.sample(
            min(24, len(dup_pairs)), random_state=seed).itertuples()],
        grid_dir / "dedup_pasangan.jpg", pairs=True,
    )

    # Filter kualitas pada wakil (bukan duplikat). "rusak" dihitung di sini juga.
    unique = df[~df["is_duplicate"]]
    report["kualitas_ditolak"] = {
        name: {str(k): int(v) for k, v in g["reject_reason"].value_counts().items()} for name, g in unique.groupby("source")
    }
    for reason, g in unique[unique["reject_reason"].notna() & (unique["reject_reason"] != "rusak")].groupby("reject_reason"):
        save_grid([(DATA_DIR / p, None, reason) for p in g["image_path"].sample(min(24, len(g)), random_state=seed)],
                  grid_dir / f"ditolak_{reason}.jpg")
    kept = unique[unique["reject_reason"].isna()].copy()
    save_grid([(DATA_DIR / p, None, lab) for p, lab in kept[["image_path", "label"]].sample(
        min(24, len(kept)), random_state=seed).itertuples(index=False)], grid_dir / "lolos_sampel.jpg")

    merge = dcfg.get("class_merge") or {}
    kept["label_final"] = kept["label"].map(lambda c: merge.get(c, c))
    report["class_merge"] = merge
    report["distribusi_kelas"] = {
        "per_dataset": count_by(kept, "source", "label_final"),
        "per_kota_atau_lokasi": count_by(kept, "source", "city", "label_final") if kept["city"].notna().any() else {},
        "total": {c: int((kept["label_final"] == c).sum()) for c in dict.fromkeys(merge.get(c, c) for c in CATEGORIES)},
    }
    if "label_alt" in kept and kept["label_alt"].notna().any():
        alt = kept[kept["label_alt"].notna()]
        report["sensitivitas_pm25vision"] = {
            "label_berubah": int((alt["label"] != alt["label_alt"]).sum()),
            "total": int(len(alt)),
            "perpindahan": count_by(alt[alt["label"] != alt["label_alt"]], "label_alt", "label"),
        }

    kept["split_group"] = location_groups(kept)
    forced = frozenset(kept.loc[kept["group_hint"].isin(dcfg["test_groups"]), "split_group"])
    kept["split"] = assign_splits(kept, seed=seed, val_frac=dcfg["val_frac"], test_frac=dcfg["test_frac"],
                                  forced_test_groups=forced, label_col="label_final")
    report["split"] = {
        "gambar": count_by(kept, "split"),
        "kelompok_lokasi": {s: int(g["split_group"].nunique()) for s, g in kept.groupby("split")},
        "per_kelas": count_by(kept, "split", "label_final"),
        "per_sumber": count_by(kept, "split", "source"),
    }

    kept["label"] = kept["label_final"]
    out_dir.mkdir(parents=True, exist_ok=True)
    kept.drop(columns=["label_final"]).to_parquet(out_dir / "dataset.parquet", index=False)
    df.to_parquet(out_dir / "all_images.parquet", index=False)  # termasuk yang ditolak/duplikat, untuk audit
    version = write_manifest(kept, out_dir)
    report["data_version"] = version
    report["n_final"] = int(len(kept))
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log_to_mlflow(report, out_dir)
    return report


def log_to_mlflow(report: dict, out_dir: Path) -> None:
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        logger.warning("MLFLOW_TRACKING_URI kosong; data_version tidak dicatat ke MLflow")
        return
    import mlflow

    mlflow.set_experiment("airlens-data")
    with mlflow.start_run(run_name=f"data-{report['profile']}"):
        mlflow.set_tags({"data_version": report["data_version"], "git_commit": git_commit() or "tidak diketahui",
                         "profile": report["profile"]})
        mlflow.log_params({"sources": ",".join(report["sources"]), "data_fraction": report["data_fraction"],
                           "aqi_table": report["aqi_table"]})
        mlflow.log_metric("n_final", report["n_final"])
        for split, n in report["split"]["gambar"].items():
            mlflow.log_metric(f"n_{split}", n)
        mlflow.log_artifact(str(out_dir / "report.json"))
        mlflow.log_artifact(str(out_dir / "manifest.csv"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    report = run(args.profile, args.skip_download)
    print(json.dumps({k: report[k] for k in ("n_raw", "dedup", "kualitas_ditolak", "split", "data_version")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
