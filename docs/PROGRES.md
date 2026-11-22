# Progres AirLens

Target: semua siap sebelum sesi lab, sehingga di lab tinggal **merakit alat Beta dan menguji** (lihat
`AirLens_perintah_lab.txt`). Diperbarui di setiap checkpoint.

## Lingkup (ditegaskan 2026-11-22)

1. **Proyek utama:** foto pengguna → tingkat kualitas udara (Low / Elevated / High) + pembanding IQAir.
2. **Tambahan:** alat IoT AirLens Beta (ESP32 + MQ-2, MQ-3, MQ-7, MQ-135) + model gas + **SHAP** + notifikasi HP.
3. Tidak dipakai: Grad-CAM++, kamera live, model asap, ESP32-CAM. Konsep versi lengkap (Raspberry Pi) dibiarkan apa adanya.

## Checkpoint 2026-11-22

| Bagian | Status |
|---|---|
| Pembatalan 9 commit lokal (berkas tetap) | Selesai |
| Hapus Live camera, model asap, ESP32-CAM, Grad-CAM++ (kode, web, tes, firmware, Makefile) | Selesai |
| PyTorch keluar dari image API | Selesai |
| Kelas alkohol hanya ditampilkan (tidak memicu peringatan) | Selesai |
| Kernel Kaggle v2: model foto AQI tiga tingkat + model gas Beta | Selesai (16:13–17:49 WIB), arsip 64 berkas, MANIFEST cocok |
| Dokumen disesuaikan (README, DECISIONS, DATA_CARD, EXPO, EXPO_HARI_H, perintah lab, modul Beta, hardware, firmware) | Selesai |
| `make test` (tes unit, tanpa pelatihan) | Selesai: 296 lulus; uji UI Beta 14/14, notifikasi 14/14 |
| Impor hasil Kaggle → periksa metrik → `models-publish` | Selesai: production + dataset privat `airlens-models`, `models-pull` sha256 cocok |
| Uji akhir `make expo-setup` (doctor 0 catatan, ngrok, QR; lewat ngrok: tools/docs 403, sensor tanpa token 401) | Selesai |
| Commit ulang yang rapi | Selesai (`a71cf60`, lokal, belum di-push) |

## Model final (Kaggle, 2026-11-22)

| Model | Test | Metrik |
|---|---|---|
| Foto → tingkat (EfficientNet-B0, 3 kelas) | 1.686 foto, kota disisihkan | macro-F1 0,564 · balanced acc 0,560 · ECE 0,025 · recall Low/Elevated/High 0,81/0,44/0,42 · 39% "belum pasti", akurasi yang lolos 0,68 |
| Pembanding foto | test yang sama | kelas mayoritas 0,211 · GBM fitur kabut 0,403 · MobileNetV3 0,548 |
| Gas Beta (LightGBM, dataset publik) | 1.100 sampel | macro-F1 0,865 · recall asap 0,989 (clean air ↔ alcohol saling tertukar, ±27%) |

Catatan jujur: kelas High di Dhaka hanya 33 foto (recall 0,21). Model gas belum melihat data dari alat sendiri; dilatih
ulang setelah rekaman lab (`make beta-recordings-push` + `make kaggle-push`).

## Perombakan tampilan website (2026-11-22, sore)

| Bagian | Status |
|---|---|
| Satu tema untuk semua halaman (`shared/theme.css`, huruf Archivo lokal) | Selesai |
| Halaman Foto: lembar hasil + bidang warna AQI resmi, tanpa tumpukan kartu | Selesai |
| Halaman Beta, panduan perakitan, alat operator: tema yang sama | Selesai |
| Halaman Product: kini AirLens Beta, model 3D modul seperti aslinya (ESP32, MQ, breadboard, resistor, kabel, casing STL) | Selesai |
| gzip di nginx (hemat kuota ngrok) | Selesai |
| `make test` 296 lulus, `make ui-test` 39/39 | Selesai |

## Casing Beta siap cetak (2026-11-22, malam)

| Bagian | Status |
|---|---|
| Tema website gelap (biru tua + hitam), overlay 3D di laptop dan HP | Selesai |
| Casing: port USB dekat dinding, ventilasi ruang ESP32, tulisan diukir | Selesai, STL/STEP dibuat ulang |
| File cetak: `hardware/enclosure-beta/stl/airlens_beta_base.stl` + `airlens_beta_lid.stl` (tutup dicetak terbalik) | Siap; ukur modul MQ dan breadboard asli dulu |
| Uji buka dari HP lewat ngrok (laptop): halaman 200, STL ter-gzip, `/tools` 403, sensor tanpa token 401 | Siap diuji pemilik |

## Gladi Wokwi (2026-11-23 dini hari)

| Bagian | Status |
|---|---|
| ESP32 simulasi -> ngrok -> AirLens -> halaman Beta di HP (`post 200`, clean air 97 %) | **Berhasil** |
| Bug firmware ditemukan saat gladi: sinkron jam NTP diulang terus (alat tidak pernah mengirim di jaringan lambat) | Diperbaiki, `beta-4mq-1.1.1`; `1.1.2` mencetak galat TLS bila HTTPS gagal |
| Batasan Wokwi: pembagi resistor analog tidak disimulasikan; HTTPS terlalu lambat | Diagram Wokwi AOUT langsung ke GPIO; jalur HTTP khusus gladi |
| `make gladi` / `make gladi-stop` (bisa kapan saja, juga di lab sebelum merakit) | Selesai; token diganti setelah gladi |

## Yang dikerjakan di lab (tanpa pelatihan)

`make doctor` → `make expo-setup PROFILE=lab` → rakit Beta → flash + Set WiFi (`tools/flash.html`) → pemanasan →
rekam kalibrasi (`tools/recorder.html`) → uji ujung ke ujung dari HP → unggah CSV ke Google Drive.
Setelah lab (di laptop): `make import-beta-recordings CSV=…` (evaluasi) dan `make beta-recordings-push CSV=…` +
`make kaggle-push` (latih ulang model Beta di Kaggle dengan rekaman alat).
