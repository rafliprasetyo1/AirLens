# web/static/vendor

Pustaka pihak ketiga untuk halaman produk (`product.html`) dan halaman alat (`tools/flash.html`). Disimpan lokal karena booth bisa offline: halaman tidak
memanggil CDN saat dibuka. Diunduh sekali pada 2026-11-21 dari jsDelivr (cermin paket npm), tanpa proses build.

| Berkas | Paket npm | Versi | URL sumber | Lisensi |
|---|---|---|---|---|
| `three/build/three.module.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js | MIT |
| `three/examples/jsm/loaders/GLTFLoader.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js | MIT |
| `three/examples/jsm/utils/BufferGeometryUtils.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/utils/BufferGeometryUtils.js (diimpor GLTFLoader) | MIT |
| `three/examples/jsm/environments/RoomEnvironment.js` | `three` | 0.160.0 | https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/environments/RoomEnvironment.js | MIT |
| `fonts/inter-latin-400-normal.woff2` | `@fontsource/inter` | 5.1.0 | https://cdn.jsdelivr.net/npm/@fontsource/inter@5.1.0/files/inter-latin-400-normal.woff2 | OFL-1.1 |
| `fonts/inter-latin-500-normal.woff2` | `@fontsource/inter` | 5.1.0 | https://cdn.jsdelivr.net/npm/@fontsource/inter@5.1.0/files/inter-latin-500-normal.woff2 | OFL-1.1 |
| `fonts/space-grotesk-latin-300-normal.woff2` | `@fontsource/space-grotesk` | 5.1.0 | https://cdn.jsdelivr.net/npm/@fontsource/space-grotesk@5.1.0/files/space-grotesk-latin-300-normal.woff2 | OFL-1.1 |
| `fonts/space-grotesk-latin-400-normal.woff2` | `@fontsource/space-grotesk` | 5.1.0 | https://cdn.jsdelivr.net/npm/@fontsource/space-grotesk@5.1.0/files/space-grotesk-latin-400-normal.woff2 | OFL-1.1 |
| `esptool-js-0.7.0/bundle.js` | `esptool-js` | 0.7.0 | https://cdn.jsdelivr.net/npm/esptool-js@0.7.0/bundle.js (ESM satu berkas, dipakai `tools/flash.html`) | Apache-2.0 (`esptool-js-0.7.0/LICENSE`) |

SHA-256:

```
76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495  three/build/three.module.js
d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3  three/examples/jsm/loaders/GLTFLoader.js
9be041e96308775d00e2695cc607645b9a9b64fd7c0e759dd8f7c00a8d92becb  three/examples/jsm/utils/BufferGeometryUtils.js
e21f41b7ef2016f2984a5d27850b42dffa797a6a194a138e288b06576d765a7b  three/examples/jsm/environments/RoomEnvironment.js
dd05e326cf8eac3b55acecf29c842ed73e6e6dd06491cf47f7e8800680ab3e33  fonts/inter-latin-400-normal.woff2
b0e7558f4710a1e255b93e3deefe3aebb19f3bb41c150f685a74d3b1a1c79e87  fonts/inter-latin-500-normal.woff2
b56a4e1e977d13b508461183ad2fd6cf4f5d782c0e151a78366b077f8cfb3659  fonts/space-grotesk-latin-300-normal.woff2
f814e7b61cb34cc4cb53bb31bbae0308336aec9cfb080dc5673d5ac267b24f14  fonts/space-grotesk-latin-400-normal.woff2
00ebe6fb0b202976d3e2a3c6b9a6bd438c26a81d2af6739c95ac276a64c1a84e  esptool-js-0.7.0/bundle.js
```

Periksa: `cd web/static/vendor && sha256sum -c` dengan blok di atas.

GLTFLoader dan RoomEnvironment mengimpor `'three'` sebagai nama polos; `product.html` memetakannya ke `three/build/three.module.js`, dan
`three/addons/` ke `three/examples/jsm/`, lewat import map. Jadi semua berkas dibiarkan persis seperti di paket.

## Mengganti model komponen (`web/static/product/models/components/`)

GLB komponen (±190 KB total) dibuat oleh `build_components.py` di folder itu (trimesh; mm, Y ke atas, alas papan di
y = 0). Setelah komponen asli diukur: ubah ukuran di skrip, jalankan `python3 build_components.py` (hasil di `glb/`),
salin GLB dengan nama yang sama. Posisi di casing, titik label, dan titik pin kabel ada di `product/parts.js`
(`ELECTRONICS`, `WIRES`). Skrip menulis warna sRGB ke `baseColorFactor`; `scene.js` mengonversinya ke linear.

## Mengganti model (`web/static/product/models/`)

- `airlens_node_concept.glb` + `placements.json`: dibuat ulang oleh `hardware/enclosure-concept/assemble.py`
  (setelah `enclosure_concept.py` dan `build_concept_components.py`). Nama node harus tetap: `enclosure_*` dan
  `comp_<modul>__*`.
- `airlens_beta.glb`: dibuat ulang oleh `hardware/enclosure-beta/beta_assemble.py`; node `beta_case_base`,
  `beta_case_lid`, dan `comp_*`.
- Bila posisi modul berubah, hitung ulang titik label dan ujung kabel di `product/parts.js` (`LABELS`, `WIRES`) dari
  koordinat lokal komponen lewat transformasi di `assemble.py`.
- Bangun ulang image: `docker compose up -d --build web`.

Berkas ini tidak ikut ke image karena `.dockerignore` mengecualikan `*.md`; itu disengaja.
