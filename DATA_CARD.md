# DATA_CARD — data AirLens

Data untuk melatih dan menguji model kategori AQI dari foto luar ruangan. Semua gambar berasal dari dataset publik
berlisensi jelas; pemilik proyek tidak memotret sendiri. Data **tidak** di-commit; jalankan `make data PROFILE=...`.

- Kode: `src/airlens/data/` (unduh, normalisasi, kualitas, dedup, split, manifest), `src/airlens/aqi.py` (konversi).
- Keluaran: `data/processed/<profil>/` berisi `dataset.parquet` (gambar terpakai + split), `all_images.parquet`
  (semua gambar termasuk yang ditolak, untuk audit), `manifest.csv`, `data_version.txt`, `report.json`.
  Grid sampel untuk cek visual: `results/data/<profil>/`.
- `data_version` = sha256 dari `manifest.csv` (sha256 tiap file + split + label). Dicatat di MLflow (eksperimen
  `airlens-data`) dan nanti di log prediksi. Pipeline deterministik: dua run beruntun menghasilkan versi yang sama.

## 1. Sumber

| Sumber | Dipakai untuk | Lisensi | Atribusi | Unduhan dan verifikasi |
|---|---|---|---|---|
| **PM25Vision** (Hugging Face `DeadCardassian/PM25Vision`) | train, val, test | Kartu dataset: CC BY 4.0. Gambar dari Mapillary (CC BY-SA 4.0). Label dari WAQI (aqicn.org) | Han (2025), arXiv:2509.16519; tiap gambar: `https://www.mapillary.com/app/?pKey=<image_id>`; stasiun WAQI | Otomatis; revisi dipin `578bc7c1`; sha256 tiap parquet dicocokkan dengan oid LFS |
| **Air Pollution Image Dataset from India and Nepal** (Kaggle) | train, val, test (**hanya Biratnagar**) | CC BY-NC-SA 3.0 IGO (file LICENSE di repo GitHub resmi). Non-komersial, cocok untuk tugas kuliah; model turunan tidak untuk penggunaan komersial | Rouniyar et al. (2023), doi:10.34740/KAGGLE/DS/3152196 | Kaggle API, atau zip diletakkan manual di `data/raw/india_nepal/`. Kaggle tidak memberi checksum; sha256 zip yang dipakai: `44ab21a56ef30600015e8f261cefa0eeb8619ff3bdbd62234759588e510e8668` |
| **Dhaka** (Zenodo 7878371, v2.0) | **test saja** (kota disisihkan penuh) | CC BY 4.0 | Mondal et al. (2023), doi:10.5281/zenodo.7878371; PM2.5: Konsulat AS Dhaka (AirNow) | Otomatis, **hanya profil lab** (4,5 GB; dari laptop ~0,15 MB/s); MD5 dari Zenodo dicocokkan |

Dilewati:
- **KHI-AQI (Karachi)**: tidak ditemukan tautan unduhan publik.
- **Mizoram (IEEE DataPort)**: butuh langganan dan lisensinya tidak dicantumkan.
- **Google Images atau situs tanpa lisensi jelas**: dilarang sejak awal.

Lisensi Mapillary (CC BY-SA) dan India–Nepal (NC-SA) mewajibkan atribusi. Kolom `attribution` di setiap baris
`dataset.parquet` menyimpan atribusi per gambar. Gambar tidak didistribusikan ulang oleh proyek ini.

## 2. Skema dan label

Kolom: `image_path, source, city, lat, lon, timestamp, pm25, aqi_asli, skala_asli, license, attribution`, ditambah
`location_id, split_group, split, label, label_alt, pm25_derived, sha256, phash, dhash`, statistik kualitas, dan
kolom dedup.

**Label = kategori AQI US EPA dari konsentrasi PM2.5**, memakai tabel **EPA-454/B-24-002 (Mei 2024), Table 6**,
berlaku 6 Mei 2024. Tabel ini diverifikasi langsung dari PDF EPA dan fact sheet EPA (Feb 2024). Konsentrasi dipotong
ke 1 desimal dan indeks dibulatkan. Setiap batas kategori diuji di `tests/test_aqi.py`.

| Kategori | PM2.5 (ug/m3) | Indeks |
|---|---|---|
| good | 0,0–9,0 | 0–50 |
| moderate | 9,1–35,4 | 51–100 |
| usg (tidak sehat bagi kelompok sensitif) | 35,5–55,4 | 101–150 |
| unhealthy | 55,5–125,4 | 151–200 |
| very_unhealthy | 125,5–225,4 | 201–300 |
| hazardous | ≥225,5 | 301+ |

**Penggabungan kelas (disetujui 2026-10-25): `hazardous` → `very_unhealthy`**, menjadi 5 kelas. Alasannya: hazardous
hanya berasal dari 36 stasiun PM25Vision (602 foto di skala penuh). Dengan split berbasis lokasi, val dan test hanya
akan berisi segelintir kota, sehingga recall-nya tidak bisa diukur dengan andal. Secara visual dan dari segi saran ke
pengguna, kedua kelas ini serupa. Website menampilkan kelas ini sebagai "Sangat tidak sehat / Berbahaya".

### Konversi per sumber

| Sumber | Nilai asli | Cara mendapatkan PM2.5 | Risiko |
|---|---|---|---|
| PM25Vision | AQI PM2.5 **rata-rata harian** dari WAQI (paper: "konsisten dengan US EPA") | Indeks dibalik ke konsentrasi dengan **tabel EPA 2012**, lalu dikategorikan dengan tabel 2024 (`pm25_derived=True`) | (1) Tabel yang dipakai WAQI untuk data historis tidak terdokumentasi; (2) label harian, padahal foto diambil pada jam tertentu; (3) koordinat adalah koordinat stasiun (radius pencarian foto sekitar 5 km); (4) dataset sudah "diseimbangkan" penyusunnya |
| Biratnagar | PM2.5 ug/m3 per jam (desimal; konsisten sebagai konsentrasi) | Langsung | Hanya sekitar 10 pengukuran untuk sekitar 2.170 foto |
| Dhaka | NowCast PM2.5 ug/m3 (kolom `NowCastConc. Unit`), AQI 2012 | Langsung dari NowCast, sesuai paper. AQI cocok dengan NowCast pada 72% baris (89% untuk 2020), dan hanya 40% dengan kolom Raw | `-999` = data hilang. Baris yang AQI-nya tidak cocok dengan NowCast (selisih > 2) **dibuang**, karena Dhaka adalah set test |

**Analisis sensitivitas PM25Vision** (kolom `label_alt` = kategori bila WAQI ternyata sudah memakai tabel 2024):
pada subset laptop, 67 dari 1.073 label (6,2%) berubah, hampir semuanya **good → moderate** (63). Penyebabnya: AQI
≤50 pada tabel 2012 berarti PM2.5 ≤12, padahal batas good di tabel 2024 adalah 9,0. Kelas yang lebih tinggi hampir
tidak terpengaruh.

### India–Nepal: hanya Biratnagar
Di 7 lokasi India (10.069 dari 12.240 foto), arti kolom "PM2.5" **tidak bisa dipastikan**: nilainya bilangan bulat,
maksimumnya tepat 500, dan 0–5% cocok dengan rumus EPA. Dugaan bahwa angka itu sub-indeks per polutan sudah diuji dan
tidak terbukti (AQI total ≠ maksimum kolom polutan). Daripada memakai label yang mungkin salah satu kelas, lokasi itu
dibuang. Seluruh dataset juga hanya memuat sekitar 115 pengukuran unik untuk 12.240 foto.

## 3. Pembersihan (angka dari `report.json`)

### Deduplikasi (sebelum split)
- Duplikat persis: sha256 isi file.
- Near-duplicate: pHash ≤ 4 **dan** dHash ≤ 6 secara global, atau pHash ≤ 10 **dan** dHash ≤ 12 untuk gambar dari
  **lokasi yang sama** (frame hampir sama dari kamera yang sama).
- Pasangan dikelompokkan dengan union-find. Satu wakil dipertahankan: yang lolos filter kualitas, lalu yang
  resolusinya terbesar. Ambang diperiksa visual lewat `dedup_pasangan.jpg`: pasangan yang ditandai memang frame
  hampir identik.

| Profil laptop (subset 10% lokasi) | Sebelum | Duplikat persis | Near-duplicate | Sesudah |
|---|---:|---:|---:|---:|
| PM25Vision | 1.093 | 1 | 16 | 1.076 |
| Biratnagar | 218 | 0 | 181 | **37** (83% duplikat) |

### Filter kualitas (setelah dedup)
Alasan penolakan, diperiksa berurutan: `rusak` (gagal dibuka PIL), `terlalu_kecil` (sisi < 100 px), `malam`
(jam lokal 19:00–05:59, bila jam diketahui), `terlalu_gelap` (luminance rata-rata < 45), `terlalu_terang`
(rata-rata > 235 atau > 50% piksel jenuh), `langit_tidak_terlihat` (porsi piksel terang dan halus di 40% atas
gambar < 0,05).

| Profil laptop | Ditolak |
|---|---|
| PM25Vision | langit_tidak_terlihat: 3 |
| Biratnagar | 0 |

Heuristik langit versi pertama (tekstur rata-rata sepertiga atas) **salah menolak sekitar 18% foto yang jelas
berlangit**: ranting dan gedung berlatar langit dihitung sebagai tekstur. Versi itu diganti setelah cek visual, dan
ambang 0,05 dipilih dari grid kalibrasi. PM25Vision sudah difilter penyusunnya (foto malam, tanpa langit,
overexposed), jadi angka penolakan rendah memang wajar. Heuristik ini tetap kasar dan tidak mendeteksi foto dalam
ruangan secara khusus.

## 4. Split

- **Kelompok lokasi:** lokasi yang berjarak < 25 km digabung (union-find, haversine), sehingga stasiun di satu kota
  tidak terpecah ke dua split. Semua lokasi Dhaka adalah satu kelompok.
- **Dhaka disisihkan penuh sebagai test** (kota yang tidak pernah dilihat model saat latih; profil lab).
- **Kelompok lain** ditempatkan secara serakah dan terstratifikasi: kelompok terbesar lebih dulu, masuk ke split yang
  paling kekurangan kelas-kelas yang dibawanya. Target porsi 70/15/15 berdasarkan jumlah gambar. Versi awal yang acak
  murni membuat satu kota hazardous menumpuk di val (train hanya 4, val 93).
- Split dijalankan setelah dedup: dua gambar near-duplicate selalu satu kelompok, jadi paling banyak satu yang tersisa.
- Waktu: data PM25Vision mencakup 2014-03 sampai 2025-07. Pemisahan utama berbasis lokasi, dan pemisahan waktu
  tidak diterapkan sebagai aturan tersendiri. Foto dari satu kelompok lokasi (termasuk semua harinya) selalu berada
  di satu split, sehingga hari yang sama di kota yang sama tidak bisa bocor. Kota yang berbeda (> 25 km) pada hari
  yang sama bisa berada di split berbeda. Itu bukan kebocoran gambar, tetapi pola cuaca regional bisa saja berkorelasi
  (keterbatasan).
- Ambang keyakinan dan hyperparameter hanya disetel di **val**. Test tidak disentuh sampai evaluasi akhir.

Bukti otomatis (`tests/test_data_leakage.py`, dijalankan pada split yang sebenarnya): setiap gambar ada di tepat satu
split; tidak ada sha256 ganda; tidak ada `location_id` atau `split_group` di dua split; **tidak ada near-duplicate
lintas split** (jarak hash dihitung ulang langsung, tidak bergantung pada clustering pipeline); Dhaka hanya ada di
test; semua label adalah kategori EPA.

### Profil laptop — hasil `make data PROFILE=laptop`
`data_version = 2274b55690d16455e4432cc071c2f8d44c767816e59c057f3450d01a14485744`

| Split | Gambar | Kelompok lokasi | good | moderate | usg | unhealthy | very_unhealthy (+hazardous) |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 751 | 175 | 103 | 224 | 223 | 96 | 105 |
| val | 170 | 36 | 23 | 49 | 48 | 29 | 21 |
| test | 189 | 36 | 23 | 49 | 48 | 37 | 32 |
| **total** | **1.110** | 247 | 149 | 322 | 319 | 162 | 158 |

Subset laptop = 10% **lokasi** (stasiun) beserta semua fotonya, bukan 10% foto per lokasi. Versi awal (persentase
per stasiun) membuang stasiun kecil seluruhnya dan menyisakan hanya 1 foto "good". Subset ini untuk menguji alur,
bukan untuk angka akhir.

### Profil lab (skala penuh) — perkiraan sebelum dedup dan filter
| Kelas | PM25Vision | Biratnagar | Dhaka (test) | Stasiun PM25Vision |
|---|---:|---:|---:|---:|
| good | 1.722 | 0 | 11 | 1.281 |
| moderate | 3.092 | 518 | 473 | 1.827 |
| usg | 2.388 | 500 | 305 | 547 |
| unhealthy | 2.154 | 1.153 | 432 | 199 |
| very_unhealthy + hazardous | 1.740 | 0 | 48 | 107 |

Angka akhir diisi setelah `make data PROFILE=lab` dijalankan di lab.

## 5. Batasan yang diketahui

- **Label PM25Vision bersifat harian dan diturunkan dari indeks**, bukan pengukuran pada saat foto diambil. Ini
  sumber derau label terbesar.
- **Domain:** sebagian besar foto PM25Vision adalah foto jalan Mapillary (sering dashcam), terutama dari Tiongkok,
  Eropa, dan Amerika. Foto unggahan pengguna (ponsel, Indonesia) bisa berbeda. Uji Indonesia ada di Fase 2b (opsional).
- **Biratnagar:** satu kamera, satu lokasi, sekitar 10 pengukuran. Setelah dedup hanya sedikit foto yang unik.
- **Dhaka (test):** kelas good hanya 11 foto, dan very_unhealthy+hazardous 48. Recall kelas-kelas itu di test
  Dhaka akan punya ketidakpastian besar.
- Koordinat Biratnagar dan Dhaka adalah perkiraan pusat kota (dataset tidak memuat koordinat).
- Filter "langit terlihat" bersifat heuristik.
- Lisensi NC-SA (India–Nepal) dan BY-SA (Mapillary) membatasi penggunaan ulang. Proyek ini hanya untuk keperluan akademik.
