# Casing AirLens Node (konsep v0.2)

Menara silinder Ø100 mm setinggi ±205 mm untuk node sensor AirLens, dicetak 3D dan bisa dibongkar-pasang tanpa alat
(kunci putar 22°). Penjelasan lengkap: [docs/AIRLENS_V2_DETAIL.md, bagian 14](../../docs/AIRLENS_V2_DETAIL.md#14-casing-cetak-3d).

- `stl/` berkas siap cetak untuk slicer.
- `step/` berkas CAD untuk Fusion 360 / FreeCAD.
- `enclosure_v2.py` skrip CadQuery parametrik. Ubah ukuran komponen di bagian `COMPONENTS`, lalu jalankan
  `pip install cadquery && python3 enclosure_v2.py` untuk membuat ulang semua berkas di `out_v2/`.

Cetak `airlens_joint_test.stl` lebih dulu untuk memastikan celah sambungan pas di printer yang dipakai.
Bahan yang disarankan: PETG (ASA bila node lama di bawah matahari).

Ukuran komponen di model ini masih perkiraan dari modul yang umum dijual. Ukur komponen asli dengan jangka sorong
sebelum mencetak versi final.
