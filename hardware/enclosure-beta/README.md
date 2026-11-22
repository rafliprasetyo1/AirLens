# Kotak versi Beta

Kotak cetak 3D untuk ESP32 DevKit V1 di breadboard 400 lubang + empat modul MQ (MQ-2, MQ-3, MQ-7, MQ-135; revisi Beta SHAP). Ukuran luarnya 150 × 112 × 42 mm dan terdiri dari dua bagian: nampan dan tutup jepit.

| Wrapped | Unwrapped |
|---|---|
| ![Beta tertutup](../../docs/assets/beta_wrapped.png) | ![Beta terbuka](../../docs/assets/beta_unwrapped.png) |

- Ruang sensor dipisah sekat dari ESP32, karena empat pemanas MQ (±600 mA) menghangatkan udara di sekitarnya.
- Empat MQ berjajar di ruang sensor, masing-masing di atas dua penyangga M3. Ada kisi di ujung (satu kelompok di depan
  tiap modul), kisi di dua sisi, dan empat kelompok kisi di tutup, supaya udara ruangan sampai ke setiap sensor.
- Celah micro-USB ada di ujung ESP32.
- Rusuk penahan breadboard dan penyangga MQ setinggi 9 mm memberi ruang untuk pin di bawah papan.
- Cetak dengan PETG atau PLA, 0,2 mm, dinding 3, isi 20%, tanpa support.

## Membuat ulang

Tanpa memasang Python di host, di container sekali pakai (cadquery 2.5.2, trimesh 4.5.3; unduhan ±400 MB):

```bash
docker run --rm -u 0 -v "$PWD:/w" -w /w/hardware/enclosure-beta python:3.12.14-slim-bookworm sh -c '
  apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libglib2.0-0 libxrender1 fonts-dejavu-core fontconfig
  pip install -q "cadquery==2.5.2" "trimesh==4.5.3"
  python beta_case.py && python beta_assemble.py
  chown -R 1000:1000 /w/hardware/enclosure-beta /w/web/static/product/models'
```

`beta_case.py` menulis STL + STEP; `beta_assemble.py` menulis `web/static/product/models/airlens_beta.glb` (dua
tampilan). Font DejaVu dibutuhkan untuk tulisan timbul di tutup.
