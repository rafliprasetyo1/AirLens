"""Normalisasi tiap sumber ke satu skema.

Kolom wajib: image_path (relatif terhadap DATA_DIR), source, city, lat, lon, timestamp, pm25, aqi_asli, skala_asli,
license, attribution. Kolom tambahan: location_id, group_hint, hour, pm25_derived, label, label_alt.
- pm25 dalam ug/m3. pm25_derived=True bila konsentrasi dihitung balik dari nilai AQI.
- label: kategori AQI US EPA 2024 dari pm25.
- label_alt: label pada asumsi alternatif (hanya PM25Vision), untuk analisis sensitivitas.
"""

import logging
import re
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from airlens.aqi import aqi_to_category, aqi_to_pm25, pm25_to_aqi, pm25_to_category
from airlens.data.download import PM25VISION_REVISION
from airlens.data.paths import DATA_DIR, IMAGES_DIR, RAW_DIR

logger = logging.getLogger("airlens.data.sources")

SCHEMA = [
    "image_path", "source", "city", "lat", "lon", "timestamp", "pm25", "aqi_asli", "skala_asli", "license",
    "attribution", "location_id", "group_hint", "hour", "pm25_derived", "label", "label_alt",
]


def _sample(df: pd.DataFrame, fraction: float, seed: int, by: str) -> pd.DataFrame:
    """Subset untuk profil laptop: ambil sebagian KELOMPOK `by` (mis. stasiun) beserta semua gambarnya.

    Tidak mengambil persentase gambar per kelompok: pembulatan per kelompok membuang kelompok kecil seluruhnya,
    sehingga subset condong ke stasiun besar (terbukti: kelas 'good' nyaris hilang). Minimal satu kelompok diambil.
    """
    if fraction >= 1.0:
        return df
    groups = pd.Series(df[by].unique())
    n = max(1, round(fraction * len(groups)))
    chosen = set(groups.sample(n=n, random_state=seed))
    return df[df[by].isin(chosen)]


# --------------------------------------------------------------------------- PM25Vision
def load_pm25vision(fraction: float, seed: int) -> pd.DataFrame:
    """Label asli = AQI PM2.5 harian dari WAQI. Asumsi: dihitung dengan tabel EPA 2012 (lihat DATA_CARD.md)."""
    raw = RAW_DIR / "pm25vision"
    out_dir = IMAGES_DIR / "pm25vision"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for part in ("train", "test"):
        table = pq.read_table(raw / f"{part}.parquet", columns=[
            "image_id", "station_id", "captured_at", "latitude", "longitude", "pm25", "filename", "quality",
        ])
        meta = table.to_pandas()
        meta["source_split"] = part
        frames.append(meta)
    meta = pd.concat(frames, ignore_index=True)
    meta = meta.dropna(subset=["pm25"]).drop_duplicates(subset=["image_id"])
    meta = _sample(meta, fraction, seed, by="station_id")
    wanted = set(meta["filename"])

    # Ekstrak hanya gambar terpilih (kolom image berupa struct bytes).
    for part in ("train", "test"):
        pf = pq.ParquetFile(raw / f"{part}.parquet")
        for batch in pf.iter_batches(columns=["filename", "image"], batch_size=256):
            for name, img in zip(batch.column("filename").to_pylist(), batch.column("image").to_pylist()):
                if name in wanted:
                    dest = out_dir / name
                    if not dest.exists():
                        data = img["bytes"] if isinstance(img, dict) else img
                        dest.write_bytes(data)

    aqi = meta["pm25"].astype(float)
    pm25 = aqi.map(lambda v: aqi_to_pm25(v, table=2012))
    return pd.DataFrame({
        "image_path": "images/pm25vision/" + meta["filename"],
        "source": "pm25vision",
        "city": None,
        "lat": meta["latitude"].astype(float),
        "lon": meta["longitude"].astype(float),
        "timestamp": pd.to_datetime(meta["captured_at"]).dt.strftime("%Y-%m-%d"),
        "pm25": pm25.round(1),
        "aqi_asli": aqi,
        "skala_asli": "AQI US EPA harian (WAQI), dibalik dengan tabel 2012",
        "license": "Gambar: Mapillary CC BY-SA 4.0; dataset PM25Vision: CC BY 4.0; label: WAQI",
        "attribution": (
            "Mapillary image " + meta["image_id"].astype(str) + " (https://www.mapillary.com/app/?pKey="
            + meta["image_id"].astype(str) + "); WAQI station " + meta["station_id"].astype(str)
            + "; PM25Vision (Han, 2025, arXiv:2509.16519) rev " + PM25VISION_REVISION[:7]
        ),
        "location_id": "pm25vision:" + meta["station_id"].astype(str),
        "group_hint": None,
        "hour": None,
        "pm25_derived": True,
        "label": pm25.map(pm25_to_category),
        # Bila WAQI ternyata sudah memakai tabel 2024, kategori = kategori indeks apa adanya.
        "label_alt": aqi.map(aqi_to_category),
        "pm25vision_quality": meta["quality"],
        "source_split": meta["source_split"],
    }).reset_index(drop=True)


# --------------------------------------------------------------------------- Dhaka
def parse_dhaka_datetime(date_val, time_val) -> datetime | None:
    """Kolom tanggal/jam Dhaka bercampur. Tanggal: '23.09.2020', serial Excel 44832, atau datetime dari openpyxl.
    Jam: '10.03AM', '11.37 AM', pecahan hari (0.709...), atau objek time/datetime dari openpyxl."""
    if date_val is None or (isinstance(date_val, float) and np.isnan(date_val)):
        return None
    if isinstance(date_val, datetime):
        day = date_val.replace(hour=0, minute=0, second=0, microsecond=0)
    elif isinstance(date_val, (int, float)) or re.fullmatch(r"\d{5}(\.0+)?", str(date_val).strip()):
        day = datetime(1899, 12, 30) + timedelta(days=int(float(date_val)))
    else:
        day = datetime.strptime(str(date_val).strip(), "%d.%m.%Y")
    if time_val is None or (isinstance(time_val, float) and np.isnan(time_val)):
        return day
    if isinstance(time_val, (time, datetime)):
        return day.replace(hour=time_val.hour, minute=time_val.minute)
    if isinstance(time_val, float) or re.fullmatch(r"0?\.\d+", str(time_val).strip()):
        minutes = round(float(time_val) * 24 * 60)
        return day.replace(hour=minutes // 60 % 24, minute=minutes % 60)
    text = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", str(time_val)).strip()  # tanda arah teks tak terlihat
    m = re.fullmatch(r"(\d{1,2})[.:](\d{2})(?:[.:]\d{2})?\s*([AaPp]\.?[Mm]\.?)", text)
    if not m:
        raise ValueError(f"format jam Dhaka tidak dikenal: {time_val!r}")
    hour, minute = int(m.group(1)) % 12, int(m.group(2))
    return day.replace(hour=hour + (12 if m.group(3).upper().startswith("P") else 0), minute=minute)


# --------------------------------------------------------------------------- India-Nepal
INDIA_NEPAL_CSV = "Air Pollution Image Dataset/Air Pollution Image Dataset/Combined_Dataset/IND_and_Nep_AQI_Dataset.csv"
INDIA_NEPAL_IMG_DIR = "Air Pollution Image Dataset/Air Pollution Image Dataset/Combined_Dataset/All_img/"
# Hanya Biratnagar: nilai PM2.5-nya desimal dan konsisten sebagai konsentrasi ug/m3. Di 7 lokasi India, arti kolom
# PM2.5 tidak bisa dipastikan (bilangan bulat, maksimum tepat 500, tidak cocok rumus EPA) -> dibuang. Lihat DATA_CARD.md.
INDIA_NEPAL_KEEP = {"Biratnagar, Nepal": ("biratnagar", "Biratnagar", 26.4525, 87.2718)}  # koordinat pusat kota (perkiraan)


def load_india_nepal(fraction: float, seed: int) -> pd.DataFrame:
    import zipfile

    from airlens.data.download import INDIA_NEPAL_ZIP

    out_dir = IMAGES_DIR / "india_nepal"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(RAW_DIR / "india_nepal" / INDIA_NEPAL_ZIP) as z:
        meta = pd.read_csv(z.open(INDIA_NEPAL_CSV))
        dropped = {"lokasi_india_label_tidak_jelas": int((~meta["Location"].isin(INDIA_NEPAL_KEEP)).sum())}
        meta = meta[meta["Location"].isin(INDIA_NEPAL_KEEP)].copy()
        hm = meta["Hour"].astype(str).str.split(":", expand=True).astype(int)
        meta["ts"] = pd.to_datetime(dict(year=meta["Year"], month=meta["Month"], day=meta["Day"], hour=hm[0], minute=hm[1]))
        meta["slot"] = meta["Location"] + " " + meta["ts"].dt.strftime("%Y-%m-%d %H:%M")
        meta = _sample(meta, fraction, seed, by="slot")
        for name in meta["Filename"]:
            dest = out_dir / name
            if not dest.exists():
                dest.write_bytes(z.read(INDIA_NEPAL_IMG_DIR + name))

    info = meta["Location"].map(INDIA_NEPAL_KEEP)
    pm25 = meta["PM2.5"].astype(float)
    out = pd.DataFrame({
        "image_path": "images/india_nepal/" + meta["Filename"],
        "source": "india_nepal",
        "city": info.map(lambda t: t[1]),
        "lat": info.map(lambda t: t[2]),
        "lon": info.map(lambda t: t[3]),
        "timestamp": meta["ts"].dt.strftime("%Y-%m-%d %H:%M"),  # waktu lokal Nepal
        "pm25": pm25,
        "aqi_asli": meta["AQI"].astype(float),
        "skala_asli": "PM2.5 ug/m3 per jam; kelas asli skala Taiwan EPA (tidak dipakai)",
        "license": "CC BY-NC-SA 3.0 IGO",
        "attribution": "Rouniyar et al. (2023), Air Pollution Image Dataset from India and Nepal, Kaggle, doi:10.34740/KAGGLE/DS/3152196",
        "location_id": "india_nepal:" + info.map(lambda t: t[0]),
        "group_hint": None,
        "hour": meta["ts"].dt.hour,
        "pm25_derived": False,
        "label": pm25.map(pm25_to_category),
        "label_alt": None,
        "measurement_id": meta["slot"],
    }).reset_index(drop=True)
    out.attrs["dibuang"] = dropped
    return out


DHAKA_CENTER = (23.8103, 90.4125)  # pusat kota (perkiraan); semua lokasi Dhaka satu kelompok "dhaka"


def load_dhaka(fraction: float, seed: int) -> pd.DataFrame:
    """Label: konsentrasi NowCast PM2.5 dari stasiun Konsulat AS (sesuai paper). -999 = data hilang.

    Baris yang AQI-nya tidak cocok dengan NowCast (selisih > 2 pada tabel 2012, tabel yang berlaku saat data diambil)
    dibuang: Dhaka hanya dipakai sebagai test, jadi labelnya harus bisa dipertanggungjawabkan.
    """
    import subprocess

    raw = RAW_DIR / "dhaka"
    extracted = raw / "extracted"
    if not extracted.exists():
        tmp = raw / "extracted.tmp"
        subprocess.run(["unar", "-q", "-f", "-o", str(tmp), str(raw / "dataset.rar")], check=True)
        tmp.rename(extracted)
    files = {f.stem: f for f in extracted.rglob("*") if f.suffix.lower() in {".jpg", ".jpeg", ".png"}}

    meta = pd.read_excel(raw / "dataset.xlsx", header=0, dtype=object)
    meta.columns = [str(c).strip() for c in meta.columns]
    meta = meta[meta["Image no."].notna()].copy()
    num = lambda col: pd.to_numeric(meta[col], errors="coerce").where(lambda x: x >= 0)  # noqa: E731
    meta["nowcast"], meta["aqi"] = num("NowCastConc. Unit"), num("PM2.5")
    meta["stem"] = meta["Image no."].map(lambda v: str(int(float(v))) if re.fullmatch(r"[\d.]+", str(v)) else str(v).strip())
    meta["dt"] = [parse_dhaka_datetime(d, t) for d, t in zip(meta["Date"], meta["Time"])]
    meta["place"] = meta["Place"].astype(str).str.strip()

    dropped = {
        "pm25_hilang": int(meta["nowcast"].isna().sum()),
        "gambar_tidak_ada": int((meta["nowcast"].notna() & ~meta["stem"].isin(files)).sum()),
    }
    meta = meta[meta["nowcast"].notna() & meta["stem"].isin(files)].copy()
    consistent = (meta["aqi"] - meta["nowcast"].map(lambda c: pm25_to_aqi(c, table=2012))).abs() <= 2
    dropped["aqi_tidak_konsisten"] = int((~consistent).sum())
    meta = meta[consistent]
    meta = _sample(meta, fraction, seed, by="place")

    pm25 = meta["nowcast"].astype(float)
    out = pd.DataFrame({
        "image_path": meta["stem"].map(lambda k: str(files[k].relative_to(DATA_DIR))),
        "source": "dhaka",
        "city": "Dhaka",
        "lat": DHAKA_CENTER[0],
        "lon": DHAKA_CENTER[1],
        "timestamp": pd.to_datetime(meta["dt"]).dt.strftime("%Y-%m-%d %H:%M"),  # waktu lokal Dhaka
        "pm25": pm25,
        "aqi_asli": meta["aqi"].astype(float),
        "skala_asli": "NowCast PM2.5 ug/m3 (Konsulat AS Dhaka); AQI US EPA 2012",
        "license": "CC BY 4.0",
        "attribution": "Mondal et al. (2023), Zenodo doi:10.5281/zenodo.7878371; PM2.5: US Consulate Dhaka (AirNow)",
        "location_id": "dhaka:" + meta["place"].str.lower().str.replace(r"\s+", "_", regex=True),
        "group_hint": "dhaka",
        "hour": pd.to_datetime(meta["dt"]).dt.hour,
        "pm25_derived": False,
        "label": pm25.map(pm25_to_category),
        "label_alt": None,
    }).reset_index(drop=True)
    out.attrs["dibuang"] = dropped
    logger.info("dhaka: dibuang %s", dropped)
    return out
