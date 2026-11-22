# web/static/vendor

Pustaka pihak ketiga untuk halaman produk (`product.html`) dan halaman alat (`tools/flash.html`). Disimpan lokal karena booth bisa offline: halaman tidak
memanggil CDN saat dibuka. Diunduh sekali pada 2026-11-21 dari jsDelivr (cermin paket npm), tanpa proses build.

| Berkas | Paket npm | Versi | URL sumber | Lisensi |
|---|---|---|---|---|
| `three/build/three.module.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js | MIT |
| `three/examples/jsm/loaders/GLTFLoader.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js | MIT |
| `three/examples/jsm/utils/BufferGeometryUtils.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/utils/BufferGeometryUtils.js (dipakai product/parts/bench.js untuk normal casing STL) | MIT |
| `three/examples/jsm/environments/RoomEnvironment.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/environments/RoomEnvironment.js | MIT |
| `fonts/archivo-latin-wdth-normal.woff2` | `@fontsource-variable/archivo` | 5.1.1 | https://cdn.jsdelivr.net/npm/@fontsource-variable/archivo@5.1.1/files/archivo-latin-wdth-normal.woff2 (berat 100–900, lebar 62–125 %; lisensi: `fonts/ARCHIVO-OFL.txt`) | OFL-1.1 |
| `esptool-js-0.7.0/bundle.js` | `esptool-js` | 0.7.0 | https://cdn.jsdelivr.net/npm/esptool-js@0.7.0/bundle.js (ESM satu berkas, dipakai `tools/flash.html`) | Apache-2.0 (`esptool-js-0.7.0/LICENSE`) |

SHA-256:

```
76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495  three/build/three.module.js
d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3  three/examples/jsm/loaders/GLTFLoader.js
9be041e96308775d00e2695cc607645b9a9b64fd7c0e759dd8f7c00a8d92becb  three/examples/jsm/utils/BufferGeometryUtils.js
e21f41b7ef2016f2984a5d27850b42dffa797a6a194a138e288b06576d765a7b  three/examples/jsm/environments/RoomEnvironment.js
12020a6fdc33535bdd7c2c72a76de80955f6f2cbf3a018febf629251fb146bbd  fonts/archivo-latin-wdth-normal.woff2
00ebe6fb0b202976d3e2a3c6b9a6bd438c26a81d2af6739c95ac276a64c1a84e  esptool-js-0.7.0/bundle.js
```

Periksa: `cd web/static/vendor && sha256sum -c` dengan blok di atas.

RoomEnvironment dan BufferGeometryUtils mengimpor `'three'` sebagai nama polos; `product.html` memetakannya ke
`three/build/three.module.js`, dan `three/addons/` ke `three/examples/jsm/`, lewat import map. Jadi semua berkas dibiarkan persis
seperti di paket. GLTFLoader tidak lagi dipakai halaman Product (disimpan untuk alat lama di `hardware/`).

## Model 3D halaman Product (AirLens Beta)

Modul tidak lagi berupa balok GLB: setiap modul dibangun di browser oleh `web/static/product/parts/`
(`esp32.js`, `mq.js`, `bench.js`, alat bantu `kit.js`) dengan ukuran asli dalam mm. Silkscreen, pad emas, lubang breadboard,
jaring baja sensor MQ, dan etsa pelindung WROOM digambar di kanvas saat halaman dibuka (tidak ada berkas tekstur).
Rakitan dan posisi mengikuti `hardware/enclosure-beta/beta_case.py`; lihat `product/beta-scene.js`.

- Casing: `product/models/airlens_beta_base.stl` dan `airlens_beta_lid.stl`, salinan langsung dari
  `hardware/enclosure-beta/stl/` (dibuat `beta_case.py`). Setelah casing diubah: salin ulang kedua STL ke sini.
- Ukuran/posisi komponen: konstanta `ESP32`, `MQ`, `BB` di masing-masing berkas `parts/`, dan `SENSORS`/`FLOOR` di
  `beta-scene.js`. Titik label 3D ada di `assemble()` (objek `A`), teksnya di `product/story.js` (`LABELS`).
- `airlens_beta.glb`, `airlens_node_concept.glb`, `placements.json`, dan `components/*.glb` adalah keluaran skrip lama di
  `hardware/` dan tidak dimuat halaman mana pun.
- Bangun ulang image: `docker compose up -d --build web`.

Berkas ini tidak ikut ke image karena `.dockerignore` mengecualikan `*.md`; itu disengaja.
