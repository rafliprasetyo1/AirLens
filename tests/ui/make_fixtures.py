"""Siapkan berkas uji UI dari set TEST data laptop: foto asli, versi gelap, file palsu, dan file > 10 MB."""

import sys
from pathlib import Path

import pandas as pd
from PIL import Image, ImageEnhance

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
d = pd.read_parquet("/app/data/processed/laptop/dataset.parquet")
row = d[(d.split == "test") & (d.source == "pm25vision")].sort_values("image_path").iloc[0]
img = Image.open(f"/app/data/{row.image_path}").convert("RGB")
img.save(out / "test_photo.jpg", quality=92)
ImageEnhance.Brightness(img).enhance(0.12).save(out / "dark.jpg", quality=92)
(out / "palsu.jpg").write_bytes(b"ini teks biasa, bukan gambar\n" * 50)
(out / "besar.jpg").write_bytes((out / "test_photo.jpg").read_bytes() + b"\0" * (10 * 2**20 + 1))
print(f"fixture dari {row.image_path} (label {row.label})")
