# Perangkat keras AirLens

Dokumen ini merangkum dua versi node AirLens: **konsep utama** (versi lengkap) dan **Beta**. Isinya meliputi komponen, sambungan, daya, casing, dan batasan masing-masing. Panduan perakitan langkah demi langkah ada di modul HTML; tautannya di bagian [Dokumen terkait](#dokumen-terkait). Alasan desainnya ada di [docs/AIRLENS_KONSEP_UTAMA.md](../docs/AIRLENS_KONSEP_UTAMA.md).

> Ukuran modul diambil dari lembar data dan toko resmi (November 2026). Sebelum mencetak casing final, ukur komponen asli dengan jangka sorong.

---

## Dua versi node

| | **Konsep utama** (versi lengkap) | **Beta** |
|---|---|---|
| Status | Konsep: tampil di video dan halaman produk, belum dirakit | **Berjalan di pameran** |
| Ide | Dua pemicu: **kamera live** melihat asap, **sensor gas** merasakan gas tak terlihat | Empat sensor gas + model AI kecil (asap/alkohol) yang dijelaskan dengan **SHAP** |
| Otak | Raspberry Pi 5 + AI HAT+ (Hailo) | ESP32 DevKit V1 |
| Kamera | Camera Module 3 Wide (live, model asap di alat) | Tidak ada |
| Sensor | Sensirion SEN66 (PM1–10, CO₂, VOC, NOx, suhu, kelembapan) + Alphasense CO-B4 | MQ-2, MQ-3, MQ-7, MQ-135 |
| Data | `POST /api/node/readings` setiap 2 detik | `POST /api/sensor/readings` setiap 2 detik, HTTPS lewat ngrok |
| Daya | Adaptor USB-C 27 W | Adaptor 5 V 2 A (empat pemanas MQ ±600 mA) |
| Casing | Menara 120 × 90 × 205 mm, 6 bagian cetak, zona panas terpisah | Kotak 150 × 112 × 42 mm, 2 bagian cetak |
| Panduan | [merakit-node-lengkap.html](../docs/modules/merakit-node-lengkap.html) | [merakit-node-lite.html](../docs/modules/merakit-node-lite.html) |

---

## Konsep utama

### Komponen

| Komponen | Peran | Mendeteksi / fungsi | Ukuran (mm) |
|---|---|---|---|
| Raspberry Pi 5 (8 GB) + Active Cooler | Otak | Membaca sensor, menjalankan kamera, mengirim data | 85 × 56 |
| AI HAT+ (Hailo, 26 TOPS) | Akselerator AI | Menjalankan model asap di alat | 65 × 56,5 |
| Camera Module 3 Wide | Kamera live | Asap yang terlihat; 120° diagonal (102° × 67°) | 25 × 24 × 12,4 |
| Sensirion SEN66 | Satu sensor, banyak besaran | PM1, PM2.5, PM4, PM10, CO₂ (NDIR), indeks VOC, indeks NOx, suhu, kelembapan | 55 × 26 × 21 |
| Alphasense CO-B4 + papan ISB | Gas tak terlihat | Karbon monoksida 0–1000 ppm, T90 < 30 s | Ø32 sel + papan |
| ADS1115 | ADC 16-bit | Mengubah tegangan WE/AE dari ISB menjadi angka | 28 × 17,5 |
| Adaptor USB-C 27 W (5 V 5 A) | Daya | – | – |

### Peta sambungan

| Dari | Ke | Lewat |
|---|---|---|
| Camera Module 3 Wide | Pi 5 CAM/DISP 0 | Kabel pita 22 ke 15 pin (kabel khusus Pi 5) |
| AI HAT+ | Pi 5 PCIe + GPIO | Kabel pita PCIe + header susun |
| SEN66 (breakout SEN6x) | 3V3 pin 1, SDA pin 3, SCL pin 5, GND pin 9 | STEMMA QT ke jumper; I2C 0x6B |
| ADS1115 | 3V3 pin 17, SDA pin 3, SCL pin 5, GND pin 14 | Berbagi jalur I2C; alamat 0x48 |
| ISB WE / AE | ADS1115 A0 / A1 | Kabel di bawah 10 cm; catu ISB sesuai lembar datanya |

SEN66 dan ADS1115 dicatu **3,3 V**. Tegangan keluaran ISB harus diperiksa di bawah 3,3 V sebelum disambung ke ADS1115.

### Data yang dikirim

```json
{"node_id": "full-01", "uptime_s": 125, "smoke_prob": 0.912, "co_ppm": 3.1,
 "pm25": 6.2, "pm10": 8.0, "co2_ppm": 612, "voc_index": 104, "nox_index": 1, "temp_c": 27.9, "rh": 61.0}
```

Node hanya mengirim angka. Server menentukan kejadian dengan satu aturan (`config/triggers.yaml`):

| Kamera | Gas | Kejadian |
|---|---|---|
| asap | naik | Smoke confirmed · prioritas tinggi |
| tidak | naik | Invisible gas · prioritas tinggi |
| asap | normal | Visible smoke · cek ruangan |

### Batasan

- SEN66 memberi **indeks** VOC dan NOx (100 = kondisi biasa ruangan), bukan ppm gas tertentu.
- CO-B4 perlu masa pemanasan dan angka dari lembar kalibrasinya sebelum ppm-nya bisa dipercaya.
- AirLens bukan alarm CO bersertifikat.
- Model asap dilatih dengan data publik yang didominasi pemandangan luar ruangan.

---

## Versi Beta

Revisi dosen (2026-11-21): Beta memakai empat sensor MQ dan model AI kecil yang dijelaskan dengan SHAP. Model dilatih
dengan dataset publik yang direkam memakai sensor MQ yang sama (MultimodalGasData, CC BY 4.0), karena alat fisiknya
hanya ada di lab. Detail: [docs/prompts/6_beta_shap.md](../docs/prompts/6_beta_shap.md), `DECISIONS.md`, `DATA_CARD.md`.

### Komponen

| Barang | Jumlah | Perkiraan harga |
|---|---|---|
| ESP32 DevKit V1 (30 pin) | 1 | Rp55–90 rb |
| Modul MQ-2 (asap), MQ-3 (alkohol), MQ-7 (indikasi CO), MQ-135 (kualitas udara/VOC); pin VCC, GND, DO, AO | 1 + 1 + 1 + 1 | Rp65–105 rb |
| Resistor 10 kΩ dan 20 kΩ | 4 + 4 | Rp5–10 rb |
| Adaptor 5 V 2 A + kabel USB data | 1 | Rp25–40 rb |
| Breadboard besar + 20 kabel jumper | 1 | Rp25–40 rb |
| **Total** | | **±Rp180–300 rb** |

### Sambungan

| Sensor | VCC | GND | AO → 10 kΩ → titik tengah → | titik tengah → 20 kΩ → |
|---|---|---|---|---|
| MQ-2 | VIN (5 V) | GND | GPIO34 | GND |
| MQ-3 | VIN (5 V) | GND | GPIO35 | GND |
| MQ-7 | VIN (5 V) | GND | GPIO32 | GND |
| MQ-135 | VIN (5 V) | GND | GPIO33 | GND |

Pin DO tidak dipakai. Hanya pin ADC1 (GPIO32–39) yang dipakai, karena ADC2 tidak bisa dibaca saat WiFi menyala.
Pembagi 10 kΩ / 20 kΩ menurunkan keluaran sensor (0–5 V) menjadi paling tinggi 3,33 V. Daya: empat pemanas MQ menarik
±600 mA (±150 mA masing-masing), jadi pakai adaptor 5 V 2 A ke USB ESP32; port USB laptop tidak cukup. Tidak ada BME280.

### Data yang dikirim

```json
{"node_id": "lite-01", "uptime_s": 125, "mq2_mv": 812, "mq3_mv": 640, "mq7_mv": 905, "mq135_mv": 701}
```

Tegangan pin ADC dalam mV, setiap 2 detik, lewat HTTPS ke `https://<NGROK_DOMAIN>/api/sensor/readings` dengan header
`X-Node-Token` dan `ngrok-skip-browser-warning`. Server menghitung Rs tiap sensor, baseline udara bersih (median 24
bacaan setelah 3 menit pemanasan), rasio Rs/R0, lalu menjalankan model `airlens-beta-gas` (4 kelas: clean_air, alcohol,
smoke, smoke_alcohol) dan SHAP. Format lama `{"mq2_rs_kohm": ...}` tetap diterima. Firmware: [firmware/](../firmware/README.md);
flash dan pengaturan WiFi dari browser: `http://localhost:8080/tools/flash.html`.

### Batasan

- Model dilatih dengan data alat lain (satu sesi per gas). Sensor kita bisa berperilaku berbeda; karena itu ada
  perekam kalibrasi (`tools/recorder.html`) dan `make import-beta-recordings`.
- MQ tidak selektif: tiap sensor bereaksi pada banyak gas. "Alcohol" berarti uap mirip alkohol (sanitizer, parfum).
- MQ-7 tanpa siklus pemanas (5 V/1,4 V) hanya indikatif. **Bukan alarm CO.**
- Tidak mengukur PM2.5 atau konsentrasi dalam ppm.

---

## Casing

| Versi | Casing | File |
|---|---|---|
| Konsep utama | Menara 120 × 90 × 205 mm, PETG: `base`, `spine` (rangka), `sleeve` (selubung berkisi), `cap` (kepala kamera miring 15°), `shutter` (penutup lensa geser), `wall_bracket`. Zona sensor di bawah, Pi di atas sekat ganda, jalur udara terpisah, corong SEN66 bergasket, sel CO menghadap ke bawah | [enclosure-concept/](enclosure-concept/README.md) |
| Beta | Kotak 150 × 112 × 42 mm, nampan + tutup jepit: ruang sensor bersekat panas untuk empat MQ berjajar dengan kisi samping dan atas, celah micro-USB | [enclosure-beta/](enclosure-beta/README.md) |
| Rancangan lama (v0.2) | Menara Ø100 untuk ESP32 + 3 MQ + PMS5003; disimpan sebagai arsip | [enclosure/](enclosure/README.md) |

---

## Dokumen terkait

| Dokumen | Isi |
|---|---|
| [docs/modules/merakit-node-lengkap.html](../docs/modules/merakit-node-lengkap.html) | Perakitan konsep utama: persiapan Raspberry Pi OS, uji per komponen, casing, kalibrasi, program utama Python |
| [docs/modules/merakit-node-lite.html](../docs/modules/merakit-node-lite.html) | Perakitan Beta 4 MQ: uji per sensor, flash dari browser atau Arduino IDE, rekam kalibrasi |
| [firmware/](../firmware/README.md) | Firmware Beta (4 MQ), HTTPS ke ngrok |
| [wokwi/](../wokwi/README.md) | Proyek Wokwi untuk latihan tanpa alat |
| [docs/AIRLENS_KONSEP_UTAMA.md](../docs/AIRLENS_KONSEP_UTAMA.md) | Konsep utama, aturan pemicu, kamera live, model asap, privasi |
| `web/static/product/models/` | Model 3D (GLB) rakitan konsep, rakitan Beta, dan komponen satuan untuk halaman produk |

File HTML tidak tampil sebagai halaman di GitHub. Buka lewat website AirLens (menu Build guides), atau unduh file-nya lalu buka di browser.
