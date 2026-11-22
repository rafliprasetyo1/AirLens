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
| Kernel Kaggle v2: model foto AQI tiga tingkat + model gas Beta (+ rekaman alat bila ada) | Berjalan di Kaggle |
| Dokumen disesuaikan (README, DECISIONS, DATA_CARD, EXPO, EXPO_HARI_H, perintah lab, modul Beta, hardware, firmware) | Selesai |
| `make test` (tes unit, tanpa pelatihan) | Berjalan |
| Impor hasil Kaggle → periksa metrik → `models-publish` | Menunggu kernel |
| Commit ulang yang rapi | Setelah tes lulus |

## Yang dikerjakan di lab (tanpa pelatihan)

`make doctor` → `make expo-setup PROFILE=lab` → rakit Beta → flash + Set WiFi (`tools/flash.html`) → pemanasan →
rekam kalibrasi (`tools/recorder.html`) → uji ujung ke ujung dari HP → unggah CSV ke Google Drive.
Setelah lab (di laptop): `make import-beta-recordings CSV=…` (evaluasi) dan `make beta-recordings-push CSV=…` +
`make kaggle-push` (latih ulang model Beta di Kaggle dengan rekaman alat).
