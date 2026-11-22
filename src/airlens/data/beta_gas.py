"""Data model gas Beta: MultimodalGasData (CC BY 4.0) -> fitur rasio empat MQ -> split per blok waktu.

    python -m airlens.data.beta_gas          (dipanggil `make data` dan `make data-beta`)

Temuan saat memeriksa dataset (2026-11-21), dicatat juga di DATA_CARD.md:
- Setiap kelas adalah SATU sesi rekaman berurutan (Serial Number 0..1599 per kelas, ±2 s per baris). Karena itu
  split acak per baris akan bocor; dipakai split per blok waktu dengan purge di batas.
- Nilai sensor bergeser di dalam sesi (MQ-2 NoGas naik 660 -> 784 tanpa gas: pemanasan/drift).
- Asap MENURUNKAN nilai MQ-2/MQ-3/MQ-135 (±20–35%), searah dengan resistansi sensor Rs (Rs turun saat ada gas),
  bukan dengan tegangan keluaran modul (yang naik). Fitur alat karenanya adalah Rs/R0 (lihat `device_features`).
- MQ-3 (sensor alkohol) hampir tidak bereaksi pada Perfume (median 528 vs 530 NoGas).

Fitur: rasio tiap sensor terhadap udara bersih (median NoGas seluruh dataset) + rasio turunan MQ-3/MQ-2.
Rasio tidak bergantung skala (ADC 10-bit dataset vs mV ESP32 lewat pembagi), sehingga dataset dan alat sebanding.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import yaml

# pandas hanya diimpor di fungsi pemrosesan dataset: API memakai modul ini (device_features, rs_from_mv) tanpa pandas.

from airlens.config import CONFIG_DIR, load_profile
from airlens.data.paths import RAW_DIR, RESULTS_DIR, processed_dir

logger = logging.getLogger("airlens.data.beta_gas")
CITATION = ("Narkhede, P., Walambe, R., Chandel, P., Mandaokar, S., & Kotecha, K. (2022). MultimodalGasData: "
            "Multimodal Dataset for Gas Detection and Classification. Data, 7(8), 112. Mendeley Data "
            "doi:10.17632/zkwgkjkjn9.2. CC BY 4.0")


def load_beta_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "beta_gas.yaml").read_text(encoding="utf-8"))


def feature_names(cfg: dict) -> list[str]:
    return [f"r_{s.lower()}" for s in cfg["sensors"]] + list(cfg.get("derived", []))


def class_names(cfg: dict) -> list[str]:
    return list(cfg["classes"])


# ------------------------------------------------------------------ unduhan
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_csv(cfg: dict, raw: Path | None = None) -> Path:
    """CSV di jalur manual dipakai bila ada; selain itu diunduh. Hash selalu diperiksa (berkas rusak ditolak)."""
    d = cfg["data"]
    raw = raw or RAW_DIR / "multimodal_gas"
    path = raw / d["filename"]
    if not path.exists():
        import requests

        raw.mkdir(parents=True, exist_ok=True)
        logger.info("mengunduh %s (±330 KB) dari Mendeley Data", d["filename"])
        r = requests.get(d["url"], timeout=60)
        r.raise_for_status()
        tmp = path.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.rename(path)
    got = sha256_bytes(path.read_bytes())
    if got != d["sha256"]:
        raise ValueError(f"sha256 {path.name} tidak cocok ({got[:12]}… ≠ {d['sha256'][:12]}…). Hapus berkasnya lalu "
                         "unduh ulang, atau periksa apakah dataset di Mendeley sudah berganti versi.")
    return path


# ------------------------------------------------------------------ fitur
def clean_air_reference(df: pd.DataFrame, cfg: dict) -> dict[str, float]:
    """Penyebut rasio dataset: median tiap sensor di kelas NoGas."""
    nogas = df[df["Gas"] == cfg["classes"]["clean_air"]]
    return {s: float(nogas[s].median()) for s in cfg["sensors"]}


def ratio_features(values: pd.DataFrame, reference: dict[str, float], cfg: dict) -> pd.DataFrame:
    """values: kolom nama sensor (MQ2, ...). Hasil: kolom r_mq2.. + fitur turunan."""
    import pandas as pd

    out = pd.DataFrame({f"r_{s.lower()}": values[s].astype(float) / reference[s] for s in cfg["sensors"]},
                       index=values.index)
    if "mq3_over_mq2" in cfg.get("derived", []):
        out["mq3_over_mq2"] = out["r_mq3"] / out["r_mq2"]
    return out[feature_names(cfg)]


def rs_from_mv(mv: float, vc_mv: float = 5000.0, rl_kohm: float = 1.0, divider: float = 1.5) -> float:
    """Rs (kΩ) dari tegangan pin ADC ESP32. Modul MQ: Vout = Vc·RL/(RL+Rs); pembagi 10k/20k membuat pin = Vout/1,5.
    Rs = RL·(Vc − Vout)/Vout. Hanya rasionya yang dipakai, jadi RL tidak perlu tepat."""
    vout = max(float(mv) * divider, 1.0)
    return rl_kohm * max(vc_mv - vout, 0.0) / vout


def device_features(mv: dict[str, float], baseline_rs: dict[str, float], cfg: dict) -> dict[str, float]:
    """Fitur dari bacaan alat (mV per sensor) dan baseline Rs udara bersih per sensor: Rs/R0 + turunan.
    Searah dengan dataset: nilai turun saat ada gas."""
    vals = {s: rs_from_mv(mv[s]) / baseline_rs[s] for s in cfg["sensors"]}
    feats = {f"r_{s.lower()}": v for s, v in vals.items()}
    if "mq3_over_mq2" in cfg.get("derived", []):
        feats["mq3_over_mq2"] = feats["r_mq3"] / feats["r_mq2"] if feats["r_mq2"] > 0 else float("nan")
    return {k: feats[k] for k in feature_names(cfg)}


# ------------------------------------------------------------------ split
def block_split(n: int, blocks: int, pattern: list[str], purge: int) -> np.ndarray:
    """Label split per baris untuk satu sesi berurutan sepanjang n; '' = dibuang (purge di batas antar-split)."""
    if len(pattern) != blocks:
        raise ValueError("panjang pattern harus sama dengan jumlah blok")
    edges = np.linspace(0, n, blocks + 1).round().astype(int)
    out = np.empty(n, dtype=object)
    for b in range(blocks):
        out[edges[b]:edges[b + 1]] = pattern[b]
    keep = out.copy()
    for b in range(1, blocks):
        if pattern[b] != pattern[b - 1]:
            e = edges[b]
            keep[max(0, e - purge):min(n, e + purge)] = ""
    return keep


def build(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Tabel fitur + split dari CSV mentah. Sesi = kelas; urutan baris di dalam sesi = Serial Number."""
    import pandas as pd

    inv = {v: k for k, v in cfg["classes"].items()}
    unknown = set(df["Gas"]) - set(inv)
    if unknown:
        raise ValueError(f"kelas tak dikenal di dataset: {sorted(unknown)}")
    ref = clean_air_reference(df, cfg)
    parts = []
    sp = cfg["split"]
    for gas, g in df.groupby("Gas", sort=False):
        g = g.sort_values("Serial Number")
        if not g["Serial Number"].is_monotonic_increasing or g["Serial Number"].diff().dropna().ne(1).any():
            raise ValueError(f"Serial Number sesi {gas} tidak berurutan; split per blok butuh urutan waktu")
        part = pd.DataFrame({"session": gas, "t_index": g["Serial Number"].to_numpy(), "label": inv[gas],
                             "split": block_split(len(g), sp["blocks"], sp["pattern"], sp["purge_rows"])},
                            index=g.index)
        part = part.join(g[cfg["sensors"]]).join(ratio_features(g, ref, cfg))
        parts.append(part)
    out = pd.concat(parts)
    dropped = int((out["split"] == "").sum())
    out = out[out["split"] != ""].reset_index(drop=True)
    return out, {"clean_air_reference": ref, "purged_rows": dropped}


# ------------------------------------------------------------------ alur
def run(profile_name: str | None = None) -> dict:
    profile = load_profile(profile_name)["profile"]
    cfg = load_beta_config()
    import pandas as pd

    csv_path = fetch_csv(cfg)
    raw = pd.read_csv(csv_path)
    table, info = build(raw, cfg)
    out_dir = processed_dir(profile) / "beta_gas"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "features.csv", index=False, lineterminator="\n")
    (out_dir / "reference.json").write_text(json.dumps(info["clean_air_reference"], indent=2) + "\n")
    # data_version = hash CSV sumber + aturan fitur/split (berubah bila salah satunya berubah)
    recipe = json.dumps({"csv": cfg["data"]["sha256"], "sensors": cfg["sensors"], "derived": cfg.get("derived", []),
                         "split": cfg["split"], "classes": cfg["classes"]}, sort_keys=True)
    version = hashlib.sha256(recipe.encode() + (out_dir / "features.csv").read_bytes()).hexdigest()
    (out_dir / "data_version.txt").write_text(version + "\n")
    counts = table.groupby(["split", "label"]).size()
    report = {"source": "MultimodalGasData (Mendeley Data zkwgkjkjn9 v2)", "citation": CITATION,
              "license": cfg["data"]["license"], "rows_raw": int(len(raw)), "rows_used": int(len(table)),
              "purged_rows": info["purged_rows"], "clean_air_reference_adc": info["clean_air_reference"],
              "counts": {f"{s} / {lbl}": int(n) for (s, lbl), n in counts.items()}, "data_version": version}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"data_report_beta_gas_{profile}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    logger.info("beta_gas %s: %d baris (%d dibuang purge), data_version %s", profile, len(table), info["purged_rows"],
                version[:12])
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
