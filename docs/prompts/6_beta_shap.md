Ada revisi dari dosen: versi Beta juga harus punya **SHAP**, karena menurut dosen itu nilai terpenting dan menarik untuk demo. Agar SHAP bermakna, Beta sekarang memakai empat sensor MQ dan sebuah model AI kecil. Model ini dilatih dengan dataset publik yang dibuat dengan sensor MQ yang sama, karena alat fisiknya hanya ada di lab.

Simpan prompt ini sebagai `docs/prompts/6_beta_shap.md`. Kerjakan setelah tahap yang sedang berjalan selesai, sebelum tahap dokumentasi dan sebelum uji dari HP (bila urutannya masih memungkinkan). Tunjukkan rencana dulu dan tunggu persetujuanku. Kerjakan bagian demi bagian sampai tesnya lulus. Jangan push.

Konteks yang tidak berubah:
- Semua pekerjaan di laptop ini. Lab hanya dipakai lewat terminal WSL (pelatihan GPU) dan, untuk revisi ini, browser Chrome di komputer lab.
- Alat Beta (ESP32 + sensor) hanya ada di lab; aku tidak punya alat di rumah.
- Laptop tanpa GPU, RAM 8 GB.

Sebelum menulis kode, baca:
- `CLAUDE.md`, `DECISIONS.md`, `docs/AIRLENS_KONSEP_UTAMA.md`, `hardware/README.md`
- `docs/modules/merakit-node-lite.html`
- kode sensor Beta yang sudah ada (API, `scripts/sensor_sim.py`, `web/static/beta.html`)
- trigger engine dan notifikasi bila sudah ada
- pola trainer dan MLflow registry

## Keputusan perangkat Beta (revisi)

| Komponen | Pin ESP32 |
|---|---|
| MQ-2 (asap) | GPIO34 lewat pembagi 10k/20k |
| MQ-3 (alkohol) | GPIO35 lewat pembagi 10k/20k |
| MQ-7 (indikasi CO) | GPIO32 lewat pembagi 10k/20k |
| MQ-135 (kualitas udara/VOC) | GPIO33 lewat pembagi 10k/20k |
| Daya | Adaptor 5 V 2 A ke VIN/USB (empat pemanas MQ ±600 mA; port USB laptop tidak cukup) |

Semua MQ tersambung ke VIN (5 V) dan GND. Hanya pin ADC1 yang dipakai, karena ADC2 tidak bisa dipakai bersamaan dengan WiFi. Tidak ada BME280.

## A. Data publik dan model Beta

1. **Sumber data.** MultimodalGasData (Narkhede dkk., *Data* 2022, 7(8):112; Mendeley Data `zkwgkjkjn9` versi 2; lisensi CC BY 4.0).
   - Isinya 6.400 baris (1.600 per kelas: NoGas, Perfume, Smoke, Mixture), direkam setiap 2 detik.
   - Kolom MQ2, MQ3, MQ5, MQ6, MQ7, MQ8, MQ135 berisi nilai ADC 10-bit.
   - Asap berasal dari dupa; Perfume dari deodoran semprot beralkohol.
   - Ambil **hanya berkas CSV**; arsip gambar termal tidak perlu.
   - Tambahkan ke `make data` sebagai sumber `beta_gas`. Pakai URL unduhan langsung bila tersedia (periksa sendiri), dengan jalur manual `data/raw/multimodal_gas/`.
   - Catat sitasi dan lisensinya di berkas lisensi data repo.
2. **Fitur.** Hanya MQ2, MQ3, MQ7, MQ135 (sensor yang ada di Beta). Pakai **rasio terhadap udara bersih**, bukan nilai mentah, karena dataset memakai ADC 10-bit tanpa pembagi sedangkan Beta memakai ADC 12-bit ESP32 lewat pembagi. Rasio tidak terpengaruh perbedaan skala itu.
   - **Dataset:** penyebut = median kelas NoGas.
   - **Alat:** penyebut = median bacaan setelah masa pemanasan (pola baseline yang sudah ada).
   - **Boleh** menambah 1–2 fitur turunan yang masuk akal (misalnya MQ3/MQ2), asal tetap mudah dijelaskan. Jelaskan pilihanmu di rencana.
   - **Jangan** memakai urutan baris sebagai fitur waktu sebelum memeriksa apakah dataset benar-benar berurutan.
3. **Model.** Model pohon yang didukung `shap.TreeExplainer` secara tepat, misalnya LightGBM, XGBoost, atau RandomForest. Pilih yang paling ringan dan stabil dan jelaskan alasannya.
   - Kelas tampilan: `clean_air` (NoGas), `alcohol` (Perfume), `smoke` (Smoke), `smoke_alcohol` (Mixture).
   - Split latih/validasi/uji yang jujur. Bila ada kemungkinan baris berdekatan saling bocor, pakai split per blok waktu dan jelaskan.
   - Laporkan F1 per kelas, confusion matrix, dan perbandingan dengan baseline sederhana (aturan rasio MQ-2 lama).
4. **MLOps.** `make train-beta` berjalan di laptop (CPU, hitungan menit) dan dicatat di MLflow sebagai `airlens-beta-gas` dengan alias `production`/`challenger` sendiri.
   - Artefak yang disimpan: model, daftar fitur, baseline dataset, plot ringkasan SHAP global (beeswarm/bar) sebagai PNG, dan metrik.
   - Ikut alur shadow → promote → rollback yang ada, terpisah dari model AQI dan model asap.
5. Tes: pemrosesan dataset, bentuk fitur, kelas, model bisa dimuat ulang, dan SHAP menghasilkan nilai yang jumlahnya cocok dengan keluaran model (properti additivity).

## B. API, firmware, dan simulator

1. **Skema bacaan Beta yang baru** (tetap menerima format lama `mq2_rs_kohm` agar tidak rusak):
   `{"node_id": "lite-01", "uptime_s": 125, "mq2_mv": 812, "mq3_mv": 640, "mq7_mv": 905, "mq135_mv": 701}`
   Migrasi kolom baru. Baseline per sensor dihitung setelah pemanasan.
2. **Inferensi per bacaan.** Peluang tiap kelas, kelas terpilih, dan nilai SHAP untuk kelas terpilih dari model `production` `airlens-beta-gas`.
   - `GET /beta/explain/latest?node_id=` mengembalikan fitur, nilai dasar (expected value), nilai SHAP per fitur, dan kalimat alasan.
   - Bila model belum ada, kembali ke aturan rasio MQ-2 dan tampilkan "model not available".
3. **Trigger engine.** Pemicu gas dari Beta menjadi:
   - `smoke` atau `smoke_alcohol` dengan peluang ≥ 0,7 dua kali berturut-turut → gas naik (asap);
   - `alcohol` → gas naik dengan label "alcohol/VOC".
   Ambang ada di `config/triggers.yaml`. Kalimat alasan notifikasi diambil dari 2–3 fitur dengan nilai SHAP terbesar, misalnya: "Smoke likely: MQ-2 at 2.1× clean air (+0.45), MQ-135 at 1.6× (+0.18)." Gabungan dengan kamera live tetap menghasilkan `smoke_confirmed`.
4. **Firmware** `firmware/beta/beta.ino` (Arduino, ESP32):
   - Baca empat ADC (rata-rata beberapa sampel, `analogReadMilliVolts`) setiap 2 detik.
   - Cetak satu baris JSON di serial. Bila WiFi tersimpan, kirim POST JSON ke URL AirLens.
   - WiFi SSID/kata sandi dan URL server **tidak ditulis di kode**. Semuanya dikirim lewat serial dari halaman alat (lihat C), lalu disimpan di NVS (`Preferences`).
   - Kompilasi di laptop dengan `arduino-cli` (`make firmware-beta`). Hasil `.bin` gabungan siap flash (bootloader + partisi + aplikasi, offset 0x0) disimpan di `web/static/tools/firmware/` agar bisa di-flash dari browser.
   - Laptop tidak punya alat, jadi cukup pastikan kompilasi berhasil.
5. **Simulator.** `scripts/sensor_sim.py --replay dataset` memutar ulang baris dataset per kelas dalam format skema baru, bergiliran setiap ±1 menit (clean → smoke → clean → alcohol → clean → mixture), berlabel "Simulated". Konversi nilai ADC dataset ke mV dengan cara yang masuk akal dan jelaskan. Dengan ini SHAP bisa didemokan tanpa alat.
6. Tes: skema lama dan baru, baseline per sensor, inferensi, endpoint explain, pemicu, dan replay simulator.

## C. Alat browser untuk lab: flash dan rekam (opsional di lab)

Komputer lab punya Chrome. Di lab aku hanya menyalin perintah, jadi alat ini harus bisa dipakai tanpa instal apa pun selain menjalankan web AirLens di lab.

1. `web/static/tools/flash.html`: flash firmware Beta lewat Web Serial memakai esptool-js. Simpan pustakanya lokal di `web/static/vendor/` dengan versi tetap; catat di README vendor.
   - Setelah flash, formulir **Set WiFi** (SSID, kata sandi, URL server) mengirim pengaturan lewat serial.
   - Kata sandi tidak disimpan di browser dan tidak dikirim ke server.
2. `web/static/tools/recorder.html`: perekam data kalibrasi lewat Web Serial.
   - Membaca baris JSON dari ESP32 dan menampilkan grafik empat sensor.
   - Tombol label skenario: Clean air, Incense smoke, Hand sanitizer, Smoke + sanitizer; label aktif ditempel ke setiap baris.
   - Penghitung durasi per label, lalu tombol **Download CSV**.
   - Bila aksesnya lewat `http://localhost:8080`, Chrome mengizinkan Web Serial.
   - Teks keselamatan: hanya dupa dan hand sanitizer di ruangan berventilasi, jangan pernah membuat CO.
3. `make import-beta-recordings CSV=<path>` di laptop:
   - Mengevaluasi model terhadap data rekaman alat sendiri dan melaporkan seberapa jauh akurasinya turun (domain shift).
   - Opsi melatih ulang dengan gabungan dataset publik + rekaman sendiri (dengan bobot).
   - Daftarkan hasilnya sebagai challenger bila lebih baik.
4. Halaman alat tidak masuk header navigasi pengunjung. Taruh tautannya di Build guides → Beta.

## D. Halaman Beta dan dokumen

1. **`web/static/beta.html`:**
   - Empat sensor (rasio terhadap udara bersih, grafik 30 menit) dan kelas terpilih beserta peluangnya.
   - **Grafik SHAP waterfall** yang hidup untuk bacaan terbaru: SVG buatan sendiri, merah mendorong ke kelas terpilih, biru menjauhkan, dengan nilai dasar dan nilai akhir.
   - Bagian "How the model decides": gambar SHAP global dari MLflow, sumber dataset beserta sitasinya, dan batasan dalam bahasa sederhana:
     - model dilatih dengan data alat lain;
     - MQ tidak selektif;
     - MQ-7 tanpa siklus pemanas bersifat indikatif;
     - ini bukan alarm CO.
   - Label "Simulated" tetap muncul untuk data simulator.
2. **`docs/modules/merakit-node-lite.html`** (salin juga ke `web/static/modules/`):
   - Perbarui ke empat MQ: daftar komponen, peta pin, diagram, adaptor 5 V 2 A, dan langkah uji per sensor.
   - Ganti langkah upload Arduino dengan dua cara: Arduino IDE atau flash dari browser (`/tools/flash.html`).
   - Tambahkan langkah rekam kalibrasi dengan `recorder.html`.
   - Kode lengkap dengan penjelasan per baris, sesuai gaya modul yang sudah ada.
3. **`hardware/README.md`:** bagian Beta (komponen, sambungan, daya ±600 mA, biaya sekitar Rp180–300 rb, data yang dikirim, batasan).
4. **`docs/AIRLENS_KONSEP_UTAMA.md`:**
   - Bagian 11 (Beta): empat MQ + model + SHAP + dataset.
   - Bagian 5: pemicu gas Beta berbasis model.
   - Bagian 14: batasan baru.
5. **Kotak dan model 3D Beta:** ubah `hardware/enclosure-beta/beta_case.py` agar ruang sensor memuat empat modul MQ berjajar di balik sekat panas dengan kisi samping dan atas. Ubah `beta_assemble.py` agar memasang empat MQ (MQ-3 boleh memakai bentuk `mq_2.glb`) dan kabelnya. Jalankan ulang keduanya (pasang `cadquery` dan `trimesh` di venv terpisah bila perlu) dan perbarui `airlens_beta.glb`. Halaman produk bagian Beta menyesuaikan label: "4 MQ gas sensors", "Explained with SHAP".
6. **`DECISIONS.md`:** catat revisi ini (permintaan dosen, alasan dataset publik, empat MQ, model pohon + TreeExplainer).

## Selesai bila

1. `make test` lulus, termasuk tes baru A–D.
2. `make train-beta` menghasilkan model `airlens-beta-gas` di MLflow beserta metrik dan plot SHAP global.
3. `python scripts/sensor_sim.py --replay dataset` membuat halaman Beta berpindah kelas, waterfall SHAP berubah sesuai kelas, dan notifikasi memuat kalimat alasan dari SHAP.
4. `make firmware-beta` berhasil mengompilasi `.bin`. Halaman flash dan recorder terbuka di Chrome lewat `http://localhost:8080/tools/...` (tanpa alat, cukup cek tampilan dan pesan "connect a device").
5. Modul perakitan Beta, `hardware/README.md`, dan dokumen konsep sudah diperbarui; kotak dan GLB Beta sudah memuat empat MQ.
6. Perbarui `AirLens_perintah_lab.txt` dengan bagian **opsional** "Rekam kalibrasi Beta". Bagian ini dikerjakan sambil menunggu `make lab-all`:
   - nyalakan web (`docker compose up -d web`);
   - buka `http://localhost:8080/tools/flash.html` di Chrome, flash, lalu buka `recorder.html`;
   - pemanasan sensor ±15 menit, rekam ±10 menit per label;
   - unduh CSV dan unggah ke Google Drive.

   Tambahkan juga catatan driver USB (CP210x atau CH340) bila ESP32 tidak terdeteksi.
7. Laporan ringkas: berkas yang berubah, hasil metrik model, cara menjalankan, dan keputusan. Jangan push sebelum aku memeriksa.

## Tambahan dari pengguna (2026-11-21): proyek Wokwi siap pakai

Siapkan juga proyek Wokwi yang bisa langsung dibuka dan dijalankan (klik Run) tanpa instalasi:
- `diagram.json`: rangkaian ESP32 DevKit dengan empat sensor gas (MQ-2, MQ-3, MQ-7, MQ-135) di GPIO34/35/32/33, sesuai tabel pin di atas.
- Sketch yang sama perilakunya dengan `firmware/beta/beta.ino` (baca empat ADC setiap 2 detik, cetak JSON di serial, kirim POST bila WiFi tersimpan).
- Petunjuk singkat cara membukanya di wokwi.com dan apa yang terlihat saat dijalankan.
