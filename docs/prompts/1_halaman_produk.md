Kita membuat atau memperbarui halaman produk AirLens (`web/static/product.html`). Halaman ini bergaya scrollytelling seperti halaman produk Apple. Isinya menampilkan **konsep utama** (versi lengkap) dan **versi Beta**, beserta bagian-bagian, desain casing, dan fungsinya. Saat pengunjung menggulir, model 3D berputar, terurai, dan menyorot satu bagian demi satu bagian, sementara teks penjelasan muncul di sampingnya.

Kalau `web/static/product.html` sudah ada dari pekerjaan sebelumnya (berisi konsep lama ESP32 + PMS5003 + 3 MQ), jangan mulai dari nol. Ganti isi dan modelnya sesuai prompt ini, lalu pakai ulang kerangka, vendor, dan gaya yang sudah ada.

Sebelum menulis kode, baca berkas-berkas ini:
- `CLAUDE.md`, `README.md`, `DECISIONS.md`
- `docs/AIRLENS_KONSEP_UTAMA.md` (sumber kebenaran isi halaman)
- `hardware/README.md`
- `web/static/product/models/placements.json`
- folder `web/`

Gunakan skill frontend-design untuk arah visual. Tunjukkan rencanamu dulu: struktur berkas, daftar bagian gulir, cara animasi, dan cara memuat model. Tunggu persetujuanku sebelum menulis kode.

## Aturan

- Hanya ubah berkas di `web/static/` ditambah tautan di header. Jangan ubah `api/` atau `trainer/` di prompt ini.
- Tanpa proses build dan tanpa CDN saat runtime, karena booth bisa offline. Simpan lokal di `web/static/vendor/`:
  - three@0.160.0: `build/three.module.js`, `examples/jsm/loaders/GLTFLoader.js`, `examples/jsm/environments/RoomEnvironment.js`, dan dependensinya;
  - font Inter dan Space Grotesk (woff2, subset latin, @fontsource 5.1.0).

  Catat versi dan sumbernya di `web/static/vendor/README.md`.
- Bahasa halaman: Inggris.
- Model yang dipakai, semuanya dalam satuan mm dengan sumbu Y ke atas:
  - `web/static/product/models/airlens_node_concept.glb`: rakitan konsep. Node casing bernama `enclosure_base`, `enclosure_spine`, `enclosure_sleeve`, `enclosure_cap`, `enclosure_shutter`. Node modul berawalan `comp_<nama>__`, dengan nama `rpi5`, `ai_hat_plus`, `cam3_wide`, `sen66`, `co_b4_isb`, `ads1115`.
  - `web/static/product/models/placements.json`: label, arah tarik keluar, dan posisi tiap modul.
  - `web/static/product/models/airlens_beta.glb`: rakitan Beta. Node `beta_case_base`, `beta_case_lid`, serta `comp_breadboard__*`, `comp_esp32__*`, `comp_mq2__*`, `comp_resistors`, `comp_wire_red`, `comp_wire_black`, `comp_wire_yellow`.
  - `web/static/product/models/components/*.glb`: komponen satuan untuk sorotan, bila perlu.

  Kalau berkas-berkas itu tidak ada, BERHENTI dan beri tahu aku. Jangan membuat ulang modelnya.
- Semua teks dan angka harus sesuai `docs/AIRLENS_KONSEP_UTAMA.md`. Jangan mengarang spesifikasi atau angka akurasi.
- Konsep utama selalu diberi label jelas **"Full version · concept design"**. Beta diberi label **"Running at this booth"**.
- Setelah `web/static` berubah, bangun ulang image web: `docker compose up -d --build web`.

## Arah visual

Gelap, elegan, dan tenang, tidak berlebihan. Yang menonjol hanya model 3D-nya; sisanya diam dan rapi. Kalau halaman sudah ada, pertahankan gaya yang sudah dibuat.

- Latar biru-hitam pekat dengan rona biru tipis. Satu warna aksen biru langit `#2BA8E0`. Oranye `#F2994A` hanya untuk penutup lensa dan titik "lokasimu".
- Space Grotesk untuk judul, Inter untuk teks. Paragraf maksimal ±60 karakter per baris.
- Hindari glow di mana-mana, gradien ungu-biru, kartu berbayang seragam, label huruf kapital di atas setiap judul, emoji, dan fade-in di setiap blok.
- Material matte lembut. Pakai RoomEnvironment sebagai environment map agar logam terlihat mengkilap. Pencahayaan key + rim tipis, bayangan halus di lantai.

## Alur gulir

Kanvas 3D menempel (sticky). Teks bergulir di sisi kiri di desktop, atau di bawah model di ponsel. Animasi dihitung dari progres gulir tiap bagian dan dihaluskan (lerp per frame), sehingga menggulir mundur memutar balik animasinya.

| # | Bagian | Model 3D | Teks |
|---|---|---|---|
| 1 | Hero | Menara konsep utuh, berputar sangat pelan | "AirLens Node" + "Hyperlocal air, explained." + label "Full version · concept design" |
| 2 | Design | Kamera mengitari menara; penutup lensa bergeser menutup lalu membuka | Menara dalam ruangan 120 × 90 × 205 mm, PETG, kisi miring, kepala kamera miring 15°, penutup lensa geser untuk privasi (tanpa LED) |
| 3 | Two senses | Kantong kamera dan zona sensor disorot bergantian | Mata (kamera live) dan hidung (sensor gas) sama-sama bisa memicu notifikasi |
| 4 | Exploded view | Cap naik, selubung terangkat lalu meredup, modul tertarik keluar sesuai `placements.json`; kabel terlihat | Rangka memegang semua modul; selubung diangkat setelah melepas 4 sekrup |
| 5 | Raspberry Pi 5 + AI HAT+ | Sorotan; bagian lain meredup ±25% | Otak dan AI di alat; model asap berjalan langsung pada video kamera |
| 6 | Camera Module 3 Wide | Sorotan + penutup lensa | 120° diagonal, HDR, autofokus; frame tidak disimpan |
| 7 | Sensirion SEN66 | Sorotan + corong bergasket | Satu sensor: PM1–PM10, CO₂, indeks VOC, indeks NOx, suhu, kelembapan |
| 8 | CO-B4 + ISB + ADS1115 | Sorotan; sel CO menghadap ke bawah | Gas tak terlihat (CO) yang mematikan; ADC di dekatnya agar derau rendah |
| 9 | Thermal zones | Sekat ganda disorot; zona bawah biru, zona atas oranye tipis | Panas Pi tidak boleh lewat sensor |
| 10 | Airflow | Dua aliran partikel terpisah: udara ruangan ke sensor (bawah dan samping), udara Pi masuk belakang-tengah lalu keluar atas-belakang | Jalur udara terpisah |
| 11 | Triggers | Model tetap; tiga kartu kasus pemicu | Smoke confirmed / Invisible gas / Visible smoke, sesuai tabel dokumen |
| 12 | Explainable | Model tetap | Grad-CAM++ live (tautan ke Live camera) dan contoh SHAP (ditandai "example") |
| 13 | Beta | Model berganti ke `airlens_beta.glb`; tombol **Wrapped / Unwrapped** | "Running at this booth: ESP32 + one MQ-2 gas sensor → website alerts" |
| 14 | Try it | Model konsep menyatu kembali | Tombol ke Live camera, Beta sensor, Photo demo, Build guides |

### Komponen dan label penunjuk

Saat satu modul disorot, tarik modul itu keluar ke depan kamera dan putar pelan. Redupkan casing ±10%. Tampilkan 2–3 label penunjuk, misalnya:
- **Pi 5:** "Active Cooler", "GPIO header", "PCIe to AI HAT+".
- **Kamera:** "120° wide lens", "22-pin camera cable".
- **SEN66:** "Air inlet", "Air outlet".
- **CO-B4:** "Electrochemical cell", "ISB amplifier".

Saat masuk bagian berikutnya, modul kembali ke posisinya.

### Kabel

Gambarkan kabel sebagai tabung tipis berwarna (TubeGeometry di sepanjang kurva). Warnanya: oranye 3,3 V, hitam GND, biru SDA, kuning SCL, hijau/ungu WE/AE. Jalurnya: dari SEN66 dan ADS1115 naik lewat celah grommet sekat ganda ke GPIO di atas AI HAT+, dan dari ISB ke ADS1115. Kabel terlihat di tampilan terurai dan saat sorotan.

### Beta: dua tampilan

- **Wrapped:** kotak tertutup (`beta_case_base` + `beta_case_lid`).
- **Unwrapped:** `beta_case_lid` dan `beta_case_base` disembunyikan atau dianimasikan keluar. Tampak breadboard, ESP32, MQ-2, resistor, dan kabel.
- Tombol memakai `aria-pressed` dan bisa dipakai dengan keyboard. Menggulir di bagian Beta juga membuka tutup secara bertahap.
- Label penunjuk tampilan Unwrapped: "ESP32 DevKit V1", "MQ-2 gas sensor", "10 kΩ / 20 kΩ voltage divider".
- Satu kalimat batasan: MQ-2 bereaksi ke banyak gas sekaligus, jadi peringatannya berarti "gas or smoke", bukan jenis gas tertentu.

## Kualitas

- Lebar ponsel 390 px dan desktop sama-sama rapi, tanpa gulir horizontal.
- `prefers-reduced-motion`: tanpa animasi berkelanjutan; tiap bagian langsung menampilkan keadaan akhirnya.
- Tanpa WebGL: tampilkan daftar bagian dan teksnya saja, ditambah gambar diam `docs/assets/concept_*.png` yang disalin ke `web/static/product/`.
- Indikator progres saat memuat model. Pixel ratio maksimal 2. Bayangan dimatikan di perangkat lemah.
- Keyboard, fokus terlihat, kontras WCAG AA.
- Tidak ada permintaan ke domain luar.

## Selesai bila

1. Setelah `docker compose up -d --build web`, http://localhost:8080/product.html terbuka tanpa galat di console.
2. Ke-14 bagian berjalan maju dan mundur dengan mulus. Tombol Wrapped/Unwrapped bekerja.
3. Lebar 390 px, reduced motion, dan tanpa WebGL sudah dicek (jelaskan caranya).
4. `make test` tetap lulus.
5. Laporan ringkas: berkas yang ditambah atau diubah, ukuran total aset di `web/static/product/` dan `web/static/vendor/`, serta catatan di `DECISIONS.md`.

Jangan commit atau push sebelum aku memeriksa.
