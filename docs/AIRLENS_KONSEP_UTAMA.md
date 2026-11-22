# AirLens: Konsep Utama (versi lengkap) dan Beta

Dokumen ini menggantikan rancangan node lama di `AIRLENS_V2_DETAIL.md`, yaitu bagian 4–8, 12, dan 14. Rancangan lama memakai ESP32 + tiga MQ + PMS5003 + kamera kejadian. Bagian lain dokumen v2 tetap berlaku: hasil lab, revisi kelas, MLOps, dan langkah unggah.

Tanggal keputusan: 21 November 2026.

---

## Daftar isi

1. [Ringkasan](#1-ringkasan)
2. [Tiga tingkat AirLens](#2-tiga-tingkat-airlens)
3. [Konsep utama: modul](#3-konsep-utama-modul)
4. [Alur dua pemicu](#4-alur-dua-pemicu)
5. [Aturan pemicu](#5-aturan-pemicu)
6. [Kamera live + Grad-CAM++](#6-kamera-live--grad-cam)
7. [Model asap](#7-model-asap)
8. [Notifikasi](#8-notifikasi)
9. [Privasi](#9-privasi)
10. [Casing konsep utama](#10-casing-konsep-utama)
11. [Versi Beta](#11-versi-beta)
12. [Halaman produk](#12-halaman-produk)
13. [Video booth v3](#13-video-booth-v3)
14. [Batasan dan kejujuran klaim](#14-batasan-dan-kejujuran-klaim)
15. [Berkas terkait](#15-berkas-terkait)

---

## 1. Ringkasan

Konsep utama AirLens punya **dua indra yang sama-sama bisa memicu notifikasi**:

- **Mata:** kamera live yang mengenali asap. Grad-CAM++ menunjukkan bagian gambar yang membuat model yakin.
- **Hidung:** sensor gas yang merasakan gas tak terlihat, seperti CO.

Ini mengganti alur lama, yaitu "sensor gas memicu kamera untuk mengambil satu foto". Kini kedua indra bekerja sendiri-sendiri, dan gabungan keduanya menentukan tingkat notifikasi.

Perangkat keras konsep utama **tidak dibangun untuk pameran**. Yang benar-benar didemokan:

1. **Versi Beta** (ESP32 + 4 MQ + model AI kecil yang dijelaskan dengan SHAP) untuk peringatan gas.
2. **Kamera live + Grad-CAM++ di website**, memakai kamera HP atau webcam pengunjung.

---

## 2. Tiga tingkat AirLens

| Tingkat | Isi | Status di pameran |
|---|---|---|
| **Konsep utama** (versi lengkap) | Raspberry Pi 5 + AI HAT+, Camera Module 3 Wide, Sensirion SEN66, Alphasense CO-B4 + ISB + ADS1115, casing cetak 3D | Ditampilkan di video dan halaman produk sebagai **konsep**. Modul perakitan dan casing tersedia di repo |
| **Beta** | ESP32 DevKit V1 + 4 MQ (MQ-2, MQ-3, MQ-7, MQ-135) + model gas + SHAP, kotak cetak 3D; opsional ESP32-CAM | **Berjalan sungguhan**, mengirim data ke website dan memicu notifikasi |
| **Demo website** | Unggah foto (model AQI 3 tingkat + Grad-CAM++), kamera live + Grad-CAM++ dari HP atau webcam, simulator node | **Berjalan sungguhan**, bisa dibuka pengunjung lewat QR (ngrok) |

---

## 3. Konsep utama: modul

Modul dipilih dengan kriteria "terbaik untuk fungsinya", tanpa memikirkan harga.

| Peran | Modul | Alasan |
|---|---|---|
| Otak + AI di alat | **Raspberry Pi 5 (8 GB)** + Active Cooler | Cukup kuat untuk kamera live, model asap, dan pengiriman data sekaligus |
| Akselerator AI | **AI HAT+ (Hailo, 26 TOPS)** | Menjalankan model asap di alat tanpa membebani prosesor |
| Kamera live | **Camera Module 3 Wide**: IMX708 12 MP, HDR, autofokus, 120° diagonal (102° × 67°), 25 × 24 × 12,4 mm | Satu titik pandang mencakup satu ruangan dan tetap jelas di pencahayaan sulit |
| Satu sensor untuk banyak hal | **Sensirion SEN66**: PM1/2.5/4/10, CO₂ (NDIR), indeks VOC, indeks NOx, suhu, kelembapan. Ukuran 55 × 26 × 21 mm, 3,3 V, I2C 0x6B | Jawaban profesional untuk "satu sensor banyak gas": keluarannya terpisah per besaran, bukan satu angka campuran seperti MQ |
| Gas tak terlihat yang mematikan | **Alphasense CO-B4** (elektrokimia 4 elektroda, 0–1000 ppm, T90 < 30 s) di papan **ISB** | Kelas jaringan pemantau udara; jauh lebih selektif dan stabil daripada MQ-7 |
| ADC | **ADS1115** 16-bit, I2C 0x48 | Raspberry Pi tidak punya pin analog; kabel analog dibuat pendek agar derau rendah |
| Daya | Adaptor resmi USB-C 27 W (5 V 5 A) | Pi 5 + AI HAT+ + kamera butuh daya stabil |

Peta sambungan:

- **Kamera:** ke CAM/DISP 0 lewat kabel 22 ke 15 pin.
- **AI HAT+:** lewat kabel PCIe dan header susun.
- **SEN66 dan ADS1115:** berbagi I2C (SDA GPIO2, SCL GPIO3, 3,3 V).
- **ISB:** keluaran WE ke A0 dan AE ke A1.

Detail ada di `docs/modules/merakit-node-lengkap.html`.

---

## 4. Alur dua pemicu

```
Kamera live ──> model asap (di alat) ──> smoke_prob ─┐
                                                      ├─> aturan pemicu (server) ──> notifikasi website + HP
SEN66 + CO-B4 ──> co_ppm, voc_index, nox_index, pm25 ┘
```

| Kamera | Gas | Kejadian | Prioritas | Pesan |
|---|---|---|---|---|
| asap | naik | `smoke_confirmed` | tinggi | "Smoke confirmed: camera and gas sensor agree" |
| tidak | naik | `invisible_gas` | tinggi | "Invisible gas detected, likely CO. Ventilate now" (bila pemicunya CO); "Gas detected" (bila VOC/NOx) |
| asap | normal | `visible_smoke` | sedang | "Visible smoke, check the room" |

Node lengkap hanya mengirim angka mentah ke `POST /api/node/readings`. **Keputusan diambil di server** dengan satu aturan (`config/triggers.yaml`), dipakai untuk semua sumber data:

- node lengkap;
- simulator node;
- kamera live dari website.

---

## 5. Aturan pemicu

Nilai awal disimpan di config dan bisa diubah.

| Pemicu | Masuk | Keluar (histeresis) | Catatan |
|---|---|---|---|
| Kamera | median `smoke_prob` ≥ 0,70 pada ≥ 3 dari 5 penilaian terakhir | median < 0,40 selama 30 s | Meredam kedipan satu frame |
| CO | `co_ppm` ≥ 30 dua kali berturut-turut | < 20 selama 60 s | 30 ppm ≈ pedoman WHO untuk paparan 1 jam |
| VOC | `voc_index` ≥ 250 dua kali berturut-turut | < 180 selama 60 s | Skala indeks Sensirion: 100 = kondisi biasa ruangan |
| NOx | `nox_index` ≥ 150 dua kali berturut-turut | < 100 selama 60 s | |
| Beta (model) | peluang `smoke` + `smoke_alcohol` ≥ 0,70, atau `alcohol` ≥ 0,70, dua kali berturut-turut | peluang `clean_air` ≥ 0,60 | Revisi Beta SHAP; tanpa model: aturan rasio MQ-2 (< 0,6 masuk, > 0,8 keluar) |

**Gas naik** berarti salah satu pemicu gas (CO, VOC, NOx, atau Beta) aktif. Kejadian dari Beta memuat kalimat alasan dari 2–3 nilai SHAP terbesar, misalnya "Smoke likely: MQ-135 at 0.72× clean air (+4.74), …". Pemicu Beta digabung dengan kamera live tetap menghasilkan `smoke_confirmed`. Jeda anti-spam per jenis kejadian minimal 60 detik. Notifikasi "Back to normal" dikirim satu kali saat semua pemicu keluar.

---

## 6. Kamera live + Grad-CAM++

### 6.1 Di website (yang didemokan)

1. Halaman **Live camera** meminta izin kamera hanya saat tombol "Start camera" ditekan. Tersedia pilihan kamera depan/belakang di HP. Kamera bisa diakses karena halaman memakai HTTPS (lewat ngrok) atau localhost.
2. Browser mengambil satu frame sekitar setiap 1 detik (JPEG kecil, misalnya 320 px). Frame dikirim ke `POST /api/live/frame`.
3. API menjalankan model asap: peluang asap dan peta Grad-CAM++. API membalas angka dan peta panas (PNG semi-transparan, atau array kecil yang diwarnai di browser).
4. Browser menampilkan video langsung dari kamera. Di atasnya ada lapisan peta panas yang diperbarui setiap respons, slider transparansi, legenda warna, dan angka peluang asap.
5. Hasil kamera masuk ke aturan pemicu sebagai sumber `live-<id sesi>`. Asap yang terlihat memicu `visible_smoke`. Bila simulator node atau Beta sedang memberi gas naik, hasilnya menjadi `smoke_confirmed`.
6. Target waktu: respons di bawah sekitar 1,5 detik per frame di laptop tanpa GPU. Bila lambat, kirim frame lebih jarang. Pengguna melihat "Updating every N s".

### 6.2 Di node lengkap (konsep)

- Model asap berjalan di alat: prosesor Pi lewat ONNX Runtime, atau AI HAT+ setelah dikonversi ke HEF.
- Node hanya mengirim `smoke_prob`.
- Grad-CAM++ untuk node lengkap dihitung di server bila ada kejadian. Frame kejadian dikirim hanya bila pengguna mengaktifkan "save event frames".

---

## 7. Model asap

- **Tugas:** klasifikasi biner, `no_smoke` atau `smoke`. Input 1 × 3 × 224 × 224 dengan normalisasi ImageNet. Keluaran berupa logit 2 kelas.
- **Arsitektur:** sama dengan model AQI yang sudah ada (EfficientNet ringan), supaya Grad-CAM++ dan pipeline MLflow dipakai ulang.
- **Data:**
  - Dataset asap publik dengan lisensi jelas. Kandidat: D-Fire, 21.000+ gambar dengan label YOLO: asap saja 5.867, asap + api 4.658, tanpa keduanya 9.838.
  - Gambar dengan kotak asap dihitung `smoke`. Gambar tanpa label dihitung `no_smoke`.
  - Lisensi diperiksa dan dicatat sebelum dipakai.
- **Bias yang perlu diakui:** D-Fire didominasi pemandangan luar ruangan. Uji di dalam ruangan (dupa di depan kamera HP) mungkin kurang akurat. Keterbatasan ini ditulis di halaman Live camera dan di laporan.
- **Pelatihan:** di lab dengan GPU, satu sesi bersama model AQI 3 tingkat (`make lab-all PROFILE=lab`).
- **Keluaran pelatihan:** ONNX (untuk API dan node), bobot PyTorch (untuk Grad-CAM++), dan metrik (F1, recall asap, kurva PR).
- **Registry:** model asap didaftarkan di MLflow dengan nama terpisah (misalnya `airlens-smoke`) dan alias `production`/`challenger` sendiri. Model ini tidak mencampuri promote/rollback model AQI.

---

## 8. Notifikasi

Kelanjutan dari bagian notifikasi Beta.

- Tingkat 1: notifikasi sistem saat website terbuka (service worker), banner, getar, dan bunyi.
- Tingkat 2: Web Push saat website tertutup (VAPID).
- Semua sumber memakai satu jalur notifikasi: Beta, simulator node, node lengkap, dan kamera live. Isi notifikasi menyebut sumbernya (misalnya "Camera + gas sensor agree"). Data simulasi selalu diberi label "Simulated".

---

## 9. Privasi

- **Kamera live di website:** frame diproses di memori lalu dibuang. Tidak ada frame atau peta panas yang disimpan, kecuali pengguna mencentang "Save this frame" (aturan privasi yang sudah ada).
- **Node lengkap:** ada penutup lensa geser fisik. Tidak memakai LED status, sesuai arahan dosen bahwa peringatan lewat website. Frame tidak dikirim terus-menerus, hanya `smoke_prob`.
- **Di booth:** papan kecil "Camera demo: frames are analysed and discarded, nothing is stored".

---

## 10. Casing konsep utama

Untuk dalam ruangan. Bentuknya menara persegi membulat 120 × 90 × 205 mm, bahan PETG. File: `hardware/enclosure-concept/`.

| Prinsip | Wujud di desain |
|---|---|
| Zona dingin di bawah, zona panas di atas | Sensor di bawah. Pi 5 + AI HAT+ di atas **sekat ganda** (dua pelat dengan rongga 3 mm berisi busa EPDM) |
| Jalur udara terpisah | Udara sensor masuk dari kisi bawah dan samping. Udara Pi masuk dari kisi belakang-tengah dan keluar dari atas-belakang, sehingga panas tidak lewat sensor dan tidak mengarah ke pengguna |
| SEN66 sesuai panduan desain mekanik Sensirion | Corong bergasket di dinding depan. Lubang masuk dan keluar dipisah sekat, sehingga tidak ada sirkulasi ulang |
| Sensor CO terlindung | Sel CO-B4 menghadap ke bawah, sehingga debu dan cipratan tidak mengendap. Ruangnya berkisi miring gaya Stevenson screen |
| Derau analog rendah | ADS1115 di sebelah ISB, kabel WE/AE di bawah 10 cm |
| Kamera | Kantong kamera dengan dasar miring 15° ke bawah. Rel penutup lensa geser di muka depan |
| Mudah dirawat | Rangka (spine) memegang semua modul. Selubung diangkat setelah melepas 4 sekrup M3 dari bawah ke heat-set insert |
| Cetak tanpa banyak support | Kisi miring 35°, dinding 2,5 mm, sudut membulat |

Bagian cetak: `base`, `spine`, `sleeve`, `cap`, `shutter`, `wall_bracket`. Pengaturan cetak dan urutan pasang ada di modul perakitan langkah 11.

Ukuran modul diambil dari lembar data dan toko resmi. Ukur komponen asli sebelum mencetak final. Skrip CadQuery bersifat parametrik.

---

## 11. Versi Beta

Revisi dosen (2026-11-21, `docs/prompts/6_beta_shap.md`): Beta harus punya **SHAP**, karena itu nilai terpenting dan
menarik untuk demo. Agar SHAP bermakna, Beta memakai empat sensor MQ dan model AI kecil.

- **Perangkat:** ESP32 DevKit V1 + MQ-2 (GPIO34), MQ-3 (GPIO35), MQ-7 (GPIO32), MQ-135 (GPIO33), masing-masing lewat
  pembagi 10k/20k; hanya ADC1. Adaptor 5 V 2 A (empat pemanas ±600 mA). Tanpa BME280. Opsional ESP32-CAM sebagai papan
  kedua untuk kamera asap (`POST /api/beta/camera/frame`).
- **Data:** tegangan pin (mV) tiap 2 detik lewat HTTPS ke alamat ngrok (`POST /api/sensor/readings`). WiFi, URL, dan
  token disimpan di NVS lewat `tools/flash.html`, tidak di kode. Format lama `mq2_rs_kohm` tetap diterima.
- **Fitur:** Rs/R0 tiap sensor (baseline = median Rs 24 bacaan setelah 3 menit pemanasan) + MQ-3/MQ-2.
- **Model:** `airlens-beta-gas`, LightGBM 4 kelas (clean_air, alcohol, smoke, smoke_alcohol), dilatih di laptop (CPU,
  detik) dengan **MultimodalGasData** (Narkhede dkk., *Data* 2022, 7(8):112; CC BY 4.0), dataset publik yang direkam
  dengan sensor MQ yang sama, karena alat fisik hanya ada di lab. Split per blok waktu (satu sesi per kelas). Test
  macro-F1 0,865 (aturan MQ-2 lama: 0,10). Registry dengan production/challenger, shadow, promote, rollback sendiri.
- **SHAP:** TreeSHAP persis dari LightGBM (`pred_contrib`) untuk setiap bacaan; halaman Beta menampilkan peluang
  kelas, waterfall SHAP, kalimat alasan, dan plot SHAP global dari MLflow.
- **Kalibrasi:** `tools/recorder.html` merekam bacaan berlabel (dupa, hand sanitizer, udara bersih) di lab;
  `make import-beta-recordings` mengukur domain shift dan bisa melatih ulang (hasilnya challenger).
- **Kotak cetak 3D** (`hardware/enclosure-beta/`): 150 × 112 × 42 mm, nampan + tutup jepit; empat MQ berjajar di ruang
  sensor di balik sekat panas, dengan kisi di ujung, di dua sisi, dan di tutup; celah micro-USB; tulisan timbul.

---

## 12. Halaman produk

- **Konsep utama:** model GLB `airlens_node_concept.glb` (casing + modul pada posisi aslinya, node bernama), dengan animasi tarik-keluar per modul memakai `placements.json`. Diberi label jelas "Full version: concept design".
- **Beta, dua tampilan:**
  - **Wrapped:** kotak Beta tertutup.
  - **Unwrapped:** tanpa kotak, tampak breadboard, ESP32, empat MQ, delapan resistor, dan kabel berwarna.
  - Satu GLB `airlens_beta.glb`; node `beta_case_base` dan `beta_case_lid` disembunyikan atau dianimasikan untuk tampilan unwrapped.
- Model komponen satuan (GLB) tetap tersedia untuk sorotan: `rpi5`, `ai_hat_plus`, `cam3_wide`, `sen66`, `co_b4_isb`, `ads1115`, `breadboard_half`, `esp32_devkit_v1`, `mq_2`.

---

## 13. Video booth v3

Tema gelap. Durasi sekitar 92 detik, 16:9, tanpa narasi, bahasa Inggris. Musik sama dengan sebelumnya. Sumber video: `media/video/source-v3/`.

| # | Adegan | Isi |
|---|---|---|
| 1 | Kamar Pak Dengklek | Aplikasi kota bilang udara baik, kamarnya tidak |
| 2 | Kamera live | Node konsep di ambang jendela; lensa menyala; badge "LIVE · smoke 0.93 → Grad-CAM++" |
| 3 | Grad-CAM++ live | Tampilan kamera dengan peta panas, slider, legenda, "frames never stored" |
| 4 | Dasbor + HP | Notifikasi "Smoke confirmed · high priority", notifikasi di layar kunci HP |
| 5 | Jendela ditutup | Udara pulih |
| 6 | Gas tak terlihat | Kamera bersih, CO-B4 naik ke 48 ppm, notifikasi "Invisible gas" |
| 7 | Dua pemicu | Tabel tiga kasus pemicu |
| 8 | Kota | Stasiun 18 km vs node 2 m |
| 9 | Perangkat keras | Model GLB konsep terurai; label "Full version · concept design" |
| 10 | SHAP | CO-B4, kamera, VOC, PM2.5, baseline kota |
| 11 | Beta | "Running at this booth: ESP32 + 4 MQ gas sensors → AI model, explained with SHAP" |
| 12 | Website | Placeholder rekaman layar (diisi di tahap akhir) |
| 13 | MLOps | Siklus data, latih, shadow, promote, pantau |
| 14 | Penutup | QR (diisi di tahap akhir) + "Full version shown is a concept design · AirLens Beta runs at this booth" |

---

## 14. Batasan dan kejujuran klaim

- Konsep utama belum dirakit. Semua angka di video adalah ilustrasi ("Illustrative animation · Generated with Claude AI").
- SEN66 memberi **indeks** VOC dan NOx, bukan ppm gas tertentu. CO-B4 memberi ppm CO setelah kalibrasi.
- AirLens bukan alarm CO bersertifikat.
- Model asap dilatih dengan data dominan luar ruangan. Akurasi di dalam ruangan perlu diuji dan dilaporkan apa adanya.
- Model gas Beta dilatih dengan data **alat lain**, satu sesi rekaman per gas. Angka test-nya batas atas; uji
  sebenarnya adalah rekaman alat sendiri di lab. Sensor MQ tidak selektif, dan di dataset itu MQ-3 hampir tidak
  bereaksi pada parfum, sehingga kelas "alcohol" lemah (F1 ±0,74) dan bisa muncul palsu pada udara bersih; SHAP
  memperlihatkan model bersandar pada drift MQ-7 untuk kelas itu.
- MQ-7 tanpa siklus pemanas hanya indikatif. **Beta bukan alarm CO.**

---

## 15. Berkas terkait

| Berkas | Isi |
|---|---|
| `docs/modules/merakit-node-lengkap.html` | Panduan perakitan konsep utama (Raspberry Pi 5), 15 langkah dengan kode Python lengkap |
| `docs/modules/merakit-node-lite.html` | Panduan perakitan Beta (ESP32 + 4 MQ, flash dari browser, rekam kalibrasi) |
| `firmware/`, `wokwi/` | Firmware Beta + kamera Beta (HTTPS ke ngrok), proyek Wokwi latihan |
| `hardware/README.md` | Ringkasan perangkat keras tiga tingkat, peta pin, daya, batasan |
| `hardware/enclosure-concept/` | Casing konsep utama: STL, STEP, CadQuery, rakitan GLB |
| `hardware/enclosure-beta/` | Kotak Beta: STL, STEP, CadQuery |
| `web/static/product/models/` | GLB rakitan konsep, rakitan Beta, dan komponen satuan |
| `media/video/AirLens_booth_video_v3.mp4` | Video booth tema gelap versi konsep baru |
