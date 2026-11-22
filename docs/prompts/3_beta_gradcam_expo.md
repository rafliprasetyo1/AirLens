Kita menambahkan empat hal ke AirLens: (A) fitur sensor versi Beta (ESP32 + satu sensor MQ-2 mengirim data ke API), (B) halaman Beta di website, (C) navigasi yang menghubungkan semua halaman, (D) Grad-CAM++ di halaman utama, lalu (E) mode expo agar semuanya bisa dijalankan di booth pameran.

Sebelum menulis kode, baca CLAUDE.md, README.md, DECISIONS.md, ARCHITECTURE.md, docs/AIRLENS_V2_DETAIL.md, docs/modules/merakit-node-lite.html (format data yang dikirim ESP32 ada di langkah 5 modul itu), lalu folder api/, web/, trainer/, config/, compose.yaml, dan Makefile. Gunakan skill frontend-design untuk halaman web. Tunjukkan rencanamu dulu untuk A–E (berkas yang dibuat/diubah, migrasi database, endpoint, cara Grad-CAM++ dihitung, dan urutan kerja), lalu tunggu persetujuanku. Kerjakan satu bagian sampai tesnya lulus sebelum pindah ke bagian berikutnya. Jangan push.

## Aturan umum

- Ikuti pola yang sudah ada di repo: konfigurasi lewat config/*.yaml dan .env, migrasi lewat alembic, tes dengan pytest, catat keputusan di DECISIONS.md.
- Jangan mengubah perilaku fitur yang sudah ada (unggah foto, shadow, promote, rollback, monitoring) selain yang diminta di sini.
- Semua teks dan klaim di halaman harus jujur: MQ-2 bereaksi terhadap banyak gas sekaligus (asap, LPG, alkohol, metana), jadi peringatannya berarti "ada gas atau asap", bukan jenis gas tertentu. Data simulasi selalu diberi label "Simulated".
- Nama versi: "Beta" (bukan "Lite") di semua halaman dan kode baru. Modul perakitannya tetap bernama merakit-node-lite.html.

## A. Sensor Beta di API

ESP32 mengirim POST JSON setiap 5 detik, persis seperti ini:
`{"node_id": "lite-01", "mq2_rs_kohm": 17.92, "uptime_s": 125}`
(`mq2_rs_kohm` bernilai -1 bila kabel sensor lepas.)

1. Tabel baru `sensor_readings` (migrasi alembic): id, node_id, received_at (UTC, dari server), mq2_rs_kohm, uptime_s, ratio, state, simulated.
2. `POST /sensor/readings` (lewat nginx menjadi `/api/sensor/readings`). Validasi isi; nilai ≤ 0 disimpan tetapi ditandai tidak valid dan tidak dipakai menghitung baseline. Bila `SENSOR_TOKEN` di .env terisi, wajibkan header `X-Node-Token`; bila kosong, terima tanpa token (jaringan booth tertutup).
3. Baseline per node: median dari N bacaan valid pertama setelah masa pemanasan. Nilai awal di config: pemanasan 180 detik, N = 24. `ratio = rs / baseline`.
4. Status per node: `warming_up` → `normal` → `alert`. Masuk `alert` bila ratio < 0,6 dua kali berturut-turut; kembali `normal` bila ratio > 0,8 (histeresis agar tidak berkedip). Ambang ada di config.
5. `GET /sensor/latest?node_id=...` (bacaan terakhir, status, baseline, detik sejak bacaan terakhir; `offline` bila > 20 detik) dan `GET /sensor/history?node_id=...&minutes=30`. `POST /sensor/baseline/reset` untuk mengulang baseline (dipakai bila node dipindah).
6. `scripts/sensor_sim.py`: simulator yang mengirim data seperti ESP32 dengan node_id `sim-01` dan `simulated: true`, termasuk lonjakan asap setiap beberapa menit, supaya halaman Beta bisa diuji dan didemokan tanpa perangkat.
7. Tes: validasi, baseline, histeresis status, offline, token.

## B. Halaman Beta (`web/static/beta.html`)

Bahasa Inggris, gaya gelap yang elegan dan tenang, konsisten dengan halaman produk bila sudah ada (lihat web/static/product.html); kalau belum ada, tetapkan gaya itu di sini dan pakai ulang nanti.
- Judul "AirLens Beta" dan satu kalimat: one ESP32 and one MQ-2 gas sensor that warn you about local smoke or gas.
- Panel status besar: Warming up / Normal / Alert, dengan rasio terhadap baseline. Alert menampilkan notifikasi "Possible local smoke or gas" beserta saran singkat (open windows, check the source).
- Grafik 30 menit terakhir (SVG buatan sendiri, tanpa library), garis ambang 0,6 terlihat.
- Info node: online/offline, terakhir terlihat, label "Simulated" bila datanya dari simulator.
- Data diperbarui dengan polling setiap 3 detik.
- Bagian "How it works" singkat (MQ-2 → ESP32 → WiFi → AirLens) dan tautan ke panduan perakitan.
- Bagian "Limitations" berisi batasan MQ-2 di atas.

## C. Navigasi

- Header yang sama di semua halaman web (index.html, beta.html, dan product.html bila ada): Photo demo (/), Beta sensor (/beta.html), Product (/product.html, hanya bila halamannya ada), Build guides.
- Salin docs/modules/merakit-node-lengkap.html dan docs/modules/merakit-node-lite.html ke web/static/modules/ agar bisa dibuka dari website, lalu buat web/static/modules/index.html sederhana yang menautkan keduanya (Full version dan Beta version). Catat di README bahwa sumbernya di docs/modules/.
- Halaman utama tetap berbahasa Indonesia; cukup tambahkan header navigasi tanpa mengubah alur unggah foto.

## D. Grad-CAM++ di halaman utama

Setelah hasil prediksi foto tampil, pengguna bisa menampilkan peta panas Grad-CAM++ di atas fotonya.
1. Periksa dulu bagaimana model disajikan: API memakai ONNX (onnxruntime) dari MLflow registry, sedangkan Grad-CAM++ butuh gradien. Cek apa saja yang disimpan trainer di bundle/MLflow (bobot PyTorch, arsitektur, layer konvolusi terakhir). Usulkan cara paling sederhana yang benar dan jelaskan di rencana. Pilihan yang wajar: API memuat bobot PyTorch dari bundle yang sama dan menghitung Grad-CAM++ di CPU (requirements/torch-cpu.txt sudah ada), dengan memastikan kelas yang dijelaskan sama dengan kelas prediksi ONNX. Bila bobot PyTorch belum tersimpan, ubah trainer agar menyimpannya untuk model berikutnya, dan tampilkan "explanation not available for this model version" untuk model lama.
2. Endpoint terpisah (misalnya `GET /jobs/{id}/gradcam`) supaya prediksi tetap cepat; peta panas dihitung hanya saat diminta.
3. UI: tombol "Tampilkan Grad-CAM++", slider transparansi, legenda warna (merah = paling berpengaruh), dan satu kalimat penjelasan bahwa peta panas menunjukkan bagian foto yang paling memengaruhi tebakan model foto, bukan bukti adanya polusi.
4. Peta panas tidak disimpan kecuali pengguna sudah setuju foto disimpan (aturan privasi yang sudah ada).
5. Target waktu: di bawah ±3 detik di laptop tanpa GPU. Tes: ukuran dan rentang nilai peta panas, hasil tetap sama untuk input yang sama, kelas sama dengan prediksi ONNX.

## E. Mode expo

Booth memakai satu laptop/PC yang menjalankan semuanya dengan Docker; Vercel tidak dipakai karena API, Postgres, model ONNX, dan MLflow tidak bisa berjalan di sana.
1. `make expo PROFILE=...`: menyalakan hanya layanan yang perlu untuk demo (db, mlflow, api, web; tanpa trainer dan scheduler), menunggu semuanya sehat, lalu mencetak alamat yang dibuka: http://localhost:8080 dan http://<IP-LAN>:8080, serta URL yang harus diisi di ESP32 (`http://<IP-LAN>:8080/api/sensor/readings`).
2. Cek perilaku saat internet putus: halaman tetap jalan; baseline IQAir menampilkan nilai terakhir yang tersimpan beserta waktunya, atau pesan jelas bila belum ada. Tambahkan bila belum ada.
3. `docs/EXPO.md`: runbook hari pameran: hotspot ponsel 2,4 GHz, cara mencari IP laptop, mengisi URL di ESP32, izin Windows Firewall untuk port 8080, catatan WSL (Docker Desktop meneruskan port ke jaringan; bila Docker berjalan langsung di WSL, pakai `networkingMode=mirrored`), menjalankan simulator sebagai cadangan bila node rusak, dan langkah darurat.
4. Bagian opsional di EXPO.md: ngrok untuk alamat HTTPS publik agar pengunjung bisa membuka website dari ponsel lewat QR. Pakai domain dev gratis ngrok yang tetap (tidak berubah saat agen dijalankan ulang), sehingga QR bisa dicetak sebelum hari pameran. Tulis juga: cara memasang authtoken (disimpan di konfigurasi ngrok, jangan di repo), pengunjung melihat halaman peringatan ngrok sekali sebelum masuk, batas paket gratis (sekitar 1 GB data keluar dan 20.000 permintaan per bulan), dan bahwa SSE progres analisis foto harus tetap jalan lewat ngrok (uji sekali). Karena batas data, halaman yang berat (misalnya model 3D di product.html) sebaiknya dibuka di layar booth saja. Cloudflare Quick Tunnel tidak dipakai karena alamatnya berubah setiap dijalankan dan tidak mendukung SSE.

## Selesai bila

1. `make test` lulus, termasuk tes baru untuk A dan D.
2. `make expo` menyalakan layanan dan mencetak alamatnya; `python scripts/sensor_sim.py` membuat halaman Beta berpindah Warming up → Normal → Alert → Normal.
3. Navigasi bekerja di semua halaman; modul perakitan terbuka dari menu Build guides.
4. Grad-CAM++ tampil untuk foto contoh dan menjelaskan kelas yang sama dengan hasil prediksi.
5. Halaman Beta dan header rapi di lebar 390 px, bisa dipakai dengan keyboard, dan menghormati prefers-reduced-motion.
6. Ringkas berkas yang dibuat/diubah, cara menjalankan, dan keputusan penting; tambahkan catatan di DECISIONS.md. Jangan push sebelum aku memeriksa.
