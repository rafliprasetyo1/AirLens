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

## Yang dikerjakan di lab (tanpa pelatihan)

`make doctor` → `make expo-setup PROFILE=lab` → rakit Beta → flash + Set WiFi (`tools/flash.html`) → pemanasan →
rekam kalibrasi (`tools/recorder.html`) → uji ujung ke ujung dari HP → unggah CSV ke Google Drive.
Setelah lab (di laptop): `make import-beta-recordings CSV=…` (evaluasi) dan `make beta-recordings-push CSV=…` +
`make kaggle-push` (latih ulang model Beta di Kaggle dengan rekaman alat).
