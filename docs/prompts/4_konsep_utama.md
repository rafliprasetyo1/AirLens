Kita menerapkan konsep utama AirLens yang baru. Ada empat bagian:

- **A.** Aturan dua pemicu di server.
- **B.** API dan simulator untuk node lengkap.
- **C.** Model asap (data, pelatihan, ekspor, registry).
- **D.** Halaman **Live camera** dengan Grad-CAM++ live dari kamera HP atau webcam.

Perangkat keras konsep utama tidak dibangun untuk pameran. Yang didemokan sungguhan adalah Beta, kamera live di website, dan simulator.

Sebelum menulis kode, baca:
- `CLAUDE.md`, `README.md`, `DECISIONS.md`, `ARCHITECTURE.md`
- `docs/AIRLENS_KONSEP_UTAMA.md` (sumber kebenaran: aturan pemicu di bagian 5, kamera live di 6, model asap di 7, privasi di 9)
- `hardware/README.md`
- folder `api/`, `trainer/`, `config/`, `web/`, serta `compose.yaml` dan `Makefile`
- hasil pekerjaan sebelumnya: sensor Beta, Grad-CAM++ foto, dan notifikasi bila sudah ada

Gunakan skill frontend-design untuk halaman web. Tunjukkan rencanamu untuk A–D dulu, lalu tunggu persetujuanku. Rencana berisi: berkas yang dibuat/diubah, migrasi, endpoint, skema data, cara Grad-CAM++ live dihitung, sumber data asap beserta lisensinya, perkiraan waktu latih, dan urutan kerja. Kerjakan satu bagian sampai tesnya lulus sebelum pindah. Jangan push.

## Aturan umum

- Ikuti pola repo: config di `config/*.yaml` dan `.env`, migrasi alembic, tes pytest, keputusan dicatat di `DECISIONS.md`.
- Jangan mengubah perilaku fitur yang ada (unggah foto, shadow/promote/rollback model AQI, Beta, monitoring) selain yang diminta.
- Klaim harus jujur:
  - SEN66 memberi indeks VOC/NOx, bukan ppm.
  - Data simulasi selalu berlabel "Simulated".
  - Model asap dilatih dengan data yang didominasi luar ruangan; tulis batasannya di halaman.
- Nama tampilan: "Full version (concept)" untuk node lengkap, "Beta" untuk ESP32 + MQ-2, "Live camera" untuk halaman kamera.

## A. Aturan dua pemicu (satu sumber kebenaran)

1. Buat `config/triggers.yaml` berisi ambang masuk/keluar, jumlah bacaan berturut-turut, jendela waktu, dan jeda anti-spam. Nilai awalnya sesuai tabel di dokumen bagian 5: kamera, CO, VOC, NOx, dan Beta (MQ-2 rasio < 0,6 / > 0,8).
2. Modul `trigger engine` di API dengan masukan per sumber (`node:<id>`, `beta:<id>`, `live:<sesi>`) dan keluaran kejadian: `smoke_confirmed`, `invisible_gas`, `visible_smoke`, `back_to_normal`, dengan prioritas.
   - **Gas naik:** pemicu CO, VOC, NOx, atau Beta aktif.
   - **Kamera:** pemicu kamera node atau kamera live aktif.
   - Kamera live dan gas dari node/Beta dalam satu "ruangan" boleh digabung. Buat konsep `room` sederhana di config (default satu ruangan "booth") supaya kamera HP + Beta di booth bisa menghasilkan `smoke_confirmed`.
3. Simpan kejadian di tabel `events` (migrasi): waktu, ruangan, jenis, prioritas, sumber yang terlibat, nilai pemicu, `simulated`.
4. `GET /events/latest`, `GET /events?minutes=60`, dan SSE `GET /events/stream` untuk website, memakai pola SSE yang sudah ada.
5. Hubungkan ke jalur notifikasi yang sudah ada atau sedang dibuat (notifikasi sistem + Web Push). Teks notifikasi menyebut jenis dan sumbernya, misalnya "Camera + gas sensor agree".
6. Tes: setiap kombinasi pada tabel kejadian, histeresis, jeda anti-spam, `back_to_normal`, penggabungan ruangan, dan label simulasi.

## B. Node lengkap: API dan simulator

1. Tabel `node_readings` (migrasi), lalu `POST /node/readings` (menjadi `/api/node/readings` lewat nginx). Skemanya persis seperti `hardware/README.md`: `node_id`, `uptime_s`, `smoke_prob`, `co_ppm` (boleh null), `pm25`, `pm10`, `co2_ppm`, `voc_index`, `nox_index`, `temp_c`, `rh`.
   - Validasi rentang wajar.
   - Token `X-Node-Token` wajib bila `NODE_TOKEN` di `.env` terisi.
   - Status `offline` bila lebih dari 20 detik tanpa data.
2. `GET /node/latest?node_id=` dan `GET /node/history?node_id=&minutes=30`.
3. `scripts/node_sim.py`: mengirim data seperti node lengkap dengan `node_id` `sim-full-01` dan `simulated: true`. Skenarionya dipilih lewat argumen: `normal`, `smoke` (kamera + VOC/PM naik), `invisible_gas` (CO naik, kamera bersih), `visible_smoke` (kamera saja), dan `cycle` (bergiliran setiap ±1 menit).
4. Panel kecil "Full version (concept): simulated node" di halaman Beta atau halaman Live camera. Isinya angka terbaru dan grafik 30 menit, selalu dengan label "Simulated".
5. Tes: validasi, token, offline, dan bahwa tiap skenario simulator menghasilkan kejadian yang benar.

## C. Model asap

1. **Data.** Tambahkan sumber `smoke` ke `make data`.
   - Kandidat utama: D-Fire. Klasifikasikan gambar berlabel asap sebagai `smoke`, gambar tanpa label sebagai `no_smoke`, dan buang gambar yang hanya berisi api atau tandai sebagai `no_smoke` (jelaskan pilihanmu).
   - Periksa lisensinya. Kalau tidak jelas, cari dataset lain dengan lisensi jelas. Catat sumber dan lisensi di berkas lisensi data yang sudah ada di repo (atau buat `DATA_LICENSES.md`).
   - Sumbernya harus bisa diunduh otomatis di lab lewat terminal: Kaggle API (kredensial `KAGGLE_*` sudah ada di `.env` lab) atau URL langsung. Sediakan juga jalur manual: zip disalin ke `data/raw/smoke/`.
   - Uji unduhan dan pemrosesan di laptop dengan subset kecil.
2. **Pelatihan.** Pakai ulang trainer yang ada sebisa mungkin (arsitektur EfficientNet yang sama, MLflow tracking). Konfigurasi terpisah `config/smoke.yaml`:
   - input 224 × 224, normalisasi ImageNet, 2 kelas `[no_smoke, smoke]`;
   - augmentasi yang wajar untuk dalam ruangan (kecerahan, blur, crop);
   - laporan F1, recall asap, presisi, kurva PR, dan confusion matrix.
3. **Ekspor.** ONNX (input `image` 1 × 3 × 224 × 224, keluaran logit 2 kelas), sama dengan yang dipakai `docs/modules/merakit-node-lengkap.html` langkah 13. Simpan juga bobot PyTorch untuk Grad-CAM++.
4. **Registry.** Model terdaftar sebagai `airlens-smoke` dengan alias `production`/`challenger` sendiri. Promote/rollback model asap terpisah dari model AQI, dan `promote.py` tidak mencampurkan keduanya.
5. **Model dev di laptop.** `make train-smoke PROFILE=laptop SMOKE=1` melatih model kecil dan cepat (subset, sedikit epoch, CPU) supaya halaman Live camera bisa diuji sebelum sesi lab. UI menampilkan badge "dev model". Model sungguhan dilatih di lab (lihat prompt 5).
6. Tes: pemrosesan label D-Fire → biner, bentuk input/output ONNX, dan konsistensi kelas ONNX vs PyTorch.

## D. Halaman Live camera (`web/static/live.html`)

1. Bahasa Inggris, gaya yang sama dengan halaman produk dan Beta. Masuk ke header navigasi: Photo demo, **Live camera**, Beta sensor, Product, Build guides.
2. Tombol "Start camera". Izin kamera hanya diminta saat tombol ditekan. Ada pilihan kamera depan/belakang (`facingMode`) dan tombol "Stop camera". Video tampil langsung dari `getUserMedia`. Halaman ini butuh HTTPS atau localhost; tampilkan pesan jelas bila tidak tersedia.
3. Sekitar setiap 1 detik, kirim satu frame kecil (JPEG ±320 px, kualitas sedang) ke `POST /live/frame`. Jangan mengirim frame baru sebelum respons sebelumnya datang.
4. API menjalankan model asap (ONNX untuk peluang asap) dan Grad-CAM++ (PyTorch CPU untuk kelas `smoke`). Pakai ulang kode Grad-CAM++ dari fitur foto bila ada. Respons berisi `smoke_prob`, peta panas kecil (misalnya 14 × 14 atau 28 × 28, nilai 0..1), waktu proses, dan status pemicu kamera.
5. Browser menggambar peta panas di kanvas di atas video: diperhalus, colormap biru → merah, slider transparansi. Tampilkan juga legenda, angka peluang asap, badge kejadian, dan "Updating every N s".
6. **Privasi.** Frame dan peta panas hanya diproses di memori lalu dibuang. Tidak ada yang disimpan dan tidak ada log berisi gambar. Tulis kalimatnya di halaman: "Frames are analysed and discarded. Nothing is stored." Batasi ukuran unggahan dan laju per sesi.
7. Hasil kamera live masuk ke trigger engine sebagai `live:<sesi>` di ruangan "booth". Kalau Beta atau simulator node sedang memberi gas naik, kejadiannya menjadi `smoke_confirmed`.
8. **Batasan di halaman:** model dilatih dengan data publik yang didominasi luar ruangan; peta panas menunjukkan bagian gambar yang paling memengaruhi tebakan model, bukan bukti adanya asap; ini bukan alarm kebakaran.
9. Target waktu: di bawah ±1,5 detik per frame di laptop tanpa GPU. Bila lebih lambat, perlebar interval secara otomatis.
10. Tes: validasi ukuran unggahan, bentuk dan rentang peta panas, hasil deterministik untuk input yang sama, tidak ada berkas tersimpan setelah permintaan, dan batas laju.

## Selesai bila

1. `make test` lulus, termasuk tes baru A–D.
2. `python scripts/node_sim.py cycle` menghasilkan ketiga jenis kejadian dan `back_to_normal` di website, dengan label "Simulated".
3. Halaman Live camera berjalan di laptop dengan webcam memakai model dev: peta panas tampil dan bergerak mengikuti objek. Dupa atau video asap di layar HP menaikkan peluang asap.
4. Kamera live + simulator gas di ruangan yang sama menghasilkan `smoke_confirmed`.
5. Halaman rapi di lebar 390 px, bisa dipakai dengan keyboard, dan menghormati `prefers-reduced-motion`.
6. Ringkas berkas yang dibuat/diubah, cara menjalankan, dan keputusan penting di `DECISIONS.md`. Jangan push sebelum aku memeriksa.
