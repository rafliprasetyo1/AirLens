"""AirLens Node — casing konsep utama (dalam ruangan), parametrik CadQuery.

Satuan mm, sumbu Z ke atas, bagian depan menghadap -Y. Jalankan: python3 enclosure_concept.py
Prinsip desain (lihat hardware/enclosure-concept/README.md):
  1. Zona dingin di bawah (sensor), zona panas di atas (Raspberry Pi 5 + AI HAT+), dipisah sekat ganda berongga udara.
  2. Udara sensor dan udara pendingin Pi punya jalur sendiri: sensor mengambil udara dari kisi bawah/samping,
     Pi mengambil udara dari kisi belakang-tengah dan membuang ke atas-belakang. Panas Pi tidak lewat sensor.
  3. SEN66 ditempel ke dinding lewat corong bergasket: lubang masuk dan keluar terpisah sekat, tanpa sirkulasi ulang.
  4. CO-B4 menghadap ke bawah (debu dan cipratan tidak mengendap di filternya), di ruang berkisi gaya Stevenson.
  5. ADS1115 dekat papan ISB agar kabel analog pendek (derau rendah).
  6. Kamera di kepala atas, miring 15° ke bawah, dengan tudung dan penutup lensa geser (privasi tanpa LED).
  7. Selubung diangkat dari rangka setelah melepas 4 sekrup M3 ke heat-set insert; semua modul terpasang di rangka.
"""
import math
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).parent          # menulis ke stl/ dan step/ di folder ini
(OUT / "stl").mkdir(parents=True, exist_ok=True)
(OUT / "step").mkdir(parents=True, exist_ok=True)

W, D, RC, WALL, CLR = 120.0, 90.0, 16.0, 2.5, 0.4
Z_BASE, Z_DIV0, Z_DIV1, Z_TOP, Z_CAP = 12.0, 82.0, 90.0, 152.0, 205.0
TILT = 15.0
INSERT_D, INSERT_L = 4.2, 5.7            # heat-set insert M3


def rrect(w, d, r, z0, h):
    return cq.Workplane("XY").workplane(offset=z0).rect(w, d).extrude(h).edges("|Z").fillet(r)


def louvers(face_y, x0, x1, z0, z1, pitch=6.0, slot=2.6, angle=35.0, side=False):
    """Kisi miring ke bawah: udara masuk, cipratan dan pandangan langsung terhalang."""
    cuts = None
    n = int((z1 - z0) // pitch)
    for i in range(n):
        z = z0 + i * pitch + pitch / 2
        b = cq.Workplane("XY").box((x1 - x0) if not side else 12, 12 if not side else (x1 - x0), slot)
        b = b.rotate((0, 0, 0), (1, 0, 0) if not side else (0, 1, 0), angle if not side else -angle)
        b = b.translate(((x0 + x1) / 2, face_y, z) if not side else (face_y, (x0 + x1) / 2, z))
        cuts = b if cuts is None else cuts.union(b)
    return cuts


def base():
    b = rrect(W, D, RC, 0, Z_BASE)
    b = b.cut(rrect(W - 2 * WALL, D - 2 * WALL, RC - WALL, 3.0, Z_BASE))          # nampan
    # lantai berkisi di bawah ruang CO (udara naik dari bawah)
    for i in range(7):
        b = b.cut(cq.Workplane("XY").box(46, 2.4, 10).translate((22, 6 + i * 5.0 - 15, 0)))
    # bibir dudukan selubung
    lip = rrect(W - 2 * WALL - 2 * CLR, D - 2 * WALL - 2 * CLR, RC - WALL, Z_BASE, 4).cut(
        rrect(W - 2 * WALL - 2 * CLR - 4, D - 2 * WALL - 2 * CLR - 4, RC - WALL - 2, Z_BASE, 4))
    b = b.union(lip)
    # boss heat-set untuk 4 sekrup selubung (dari bawah)
    for x in (-W / 2 + 12, W / 2 - 12):
        for y in (-D / 2 + 12, D / 2 - 12):
            b = b.union(cq.Workplane("XY").circle(4.5).extrude(Z_BASE).translate((x, y, 0)))
            b = b.cut(cq.Workplane("XY").circle(1.7).extrude(Z_BASE).translate((x, y, 0)))
            b = b.cut(cq.Workplane("XY").circle(3.0).extrude(3.2).translate((x, y, 0)))   # kepala sekrup
    # kantong kaki karet Ø10
    for x in (-W / 2 + 18, W / 2 - 18):
        for y in (-D / 2 + 22, D / 2 - 22):
            b = b.cut(cq.Workplane("XY").circle(5.2).extrude(1.0).translate((x, y, 0)))
    return b


def spine():
    """Rangka: pelat belakang + nampan sensor + sekat ganda + dudukan Pi 5."""
    yb = D / 2 - WALL - CLR - 3.0
    s = cq.Workplane("XY").box(W - 2 * WALL - 12, 3.0, Z_TOP - Z_BASE - 6).translate((0, yb + 1.5, (Z_BASE + Z_TOP - 6) / 2 + 2))
    # nampan sensor di Z 40 (papan ISB dan ADS1115 di atas, sel CO menggantung ke bawah)
    tray = cq.Workplane("XY").box(W - 2 * WALL - 12, D - 2 * WALL - 14, 2.5).translate((0, 2, 41.25))
    tray = tray.cut(cq.Workplane("XY").circle(17.0).extrude(5).translate((24, 8, 39)))          # lubang sel CO
    tray = tray.cut(cq.Workplane("XY").box(62, 30, 6).translate((-22, -16, 41)))               # ruang SEN66
    for dx, dy in ((-17, -17), (17, -17), (-17, 17), (17, 17)):                                    # ISB 40×40
        tray = tray.union(cq.Workplane("XY").circle(3).extrude(5).translate((24 + dx * 0.9, 8 + dy * 0.9, 42.5)))
    for dx in (-11.4, 11.4):                                                                       # ADS1115
        tray = tray.union(cq.Workplane("XY").circle(2.5).extrude(8).translate((-20 + dx, 22, 42.5)))
    s = s.union(tray)
    # dudukan SEN66: rangka U di depan-kiri, menekan sensor ke corong dinding depan
    cradle = cq.Workplane("XY").box(61, 30, 25).translate((-22, -D / 2 + WALL + CLR + 2 + 15, 54.5))
    cradle = cradle.cut(cq.Workplane("XY").box(55.6, 33.6, 21.6).translate((-22, -28.2, 54.5)))
    s = s.union(cradle)
    # sekat ganda: dua pelat 2.5 mm dengan rongga 3 mm (diisi busa EPDM), celah kabel bergrommet
    for z in (Z_DIV0, Z_DIV1 - 2.5):
        plate = rrect(W - 2 * WALL - 2 * CLR - 1, D - 2 * WALL - 2 * CLR - 1, RC - WALL - 1, z, 2.5)
        plate = plate.cut(cq.Workplane("XY").box(16, 8, 10).translate((W / 2 - 22, D / 2 - 18, z)))
        s = s.union(plate)
    # penyangga Pi 5 (pola lubang 58 × 49, M2.5, tinggi 6)
    for x in (-29.0, 29.0):
        for y in (-24.5, 24.5):
            st = cq.Workplane("XY").circle(3.0).extrude(6).translate((x + 2, y - 4, Z_DIV1))
            st = st.cut(cq.Workplane("XY").circle(1.8).extrude(6).translate((x + 2, y - 4, Z_DIV1)))
            s = s.union(st)
    return s


def sleeve():
    h = Z_TOP - Z_BASE
    sl = rrect(W, D, RC, Z_BASE, h).cut(rrect(W - 2 * WALL, D - 2 * WALL, RC - WALL, Z_BASE, h))
    yf, yr = -D / 2, D / 2
    # zona sensor: kisi samping kiri-kanan dan depan bawah
    sl = sl.cut(louvers(-W / 2, -25, 25, 18, 76, side=True))
    sl = sl.cut(louvers(W / 2, -25, 25, 18, 76, side=True))
    sl = sl.cut(louvers(yf, 8, 46, 18, 40))
    # corong SEN66: jendela masuk (kiri) dan keluar (kanan) dipisah sekat 6 mm
    for x0, w in ((-5.0, 16.0), (-38.0, 14.0)):   # masuk (kanan), keluar (kiri)
        sl = sl.cut(cq.Workplane("XY").box(w, 10, 12).translate((x0, yf, 54.5)))
        for k in range(3):
            sl = sl.union(cq.Workplane("XY").box(w, WALL, 1.2).translate((x0, yf + WALL / 2, 50.5 + k * 4)))
    sl = sl.union(cq.Workplane("XY").box(44, 4.0, 18).translate((-22.5, yf + WALL + 2, 54.5))
                  .cut(cq.Workplane("XY").box(16.6, 6, 12.6).translate((-5, yf + WALL + 2, 54.5)))
                  .cut(cq.Workplane("XY").box(14.6, 6, 12.6).translate((-38, yf + WALL + 2, 54.5))))
    # zona panas: kisi masuk belakang-tengah, tanpa kisi di depan (udara panas tidak mengarah ke pengguna)
    sl = sl.cut(louvers(yr, -40, 40, 96, 124, angle=-35))
    # USB-C panel dan lubang gantung dinding
    sl = sl.cut(cq.Workplane("XY").box(13, 10, 6.5).translate((38, yr, 134)))
    for x in (-30, 30):
        sl = sl.cut(cq.Workplane("XY").circle(4.2).extrude(10).rotate((0, 0, 0), (1, 0, 0), 90).translate((x, yr + 5, 142)))
        sl = sl.cut(cq.Workplane("XY").box(4.0, 10, 8).translate((x, yr, 146)))
    # boss sekrup bawah (masuk dari base) dengan heat-set insert
    for x in (-W / 2 + 12, W / 2 - 12):
        for y in (-D / 2 + 12, D / 2 - 12):
            boss = cq.Workplane("XY").circle(4.5).extrude(12).translate((x, y, Z_BASE))
            boss = boss.cut(cq.Workplane("XY").circle(INSERT_D / 2).extrude(INSERT_L + 1).translate((x, y, Z_BASE)))
            sl = sl.union(boss)
    return sl


ZC = Z_TOP + 26                         # tinggi sumbu lensa
LENS_N = (0.0, -math.cos(math.radians(TILT)), -math.sin(math.radians(TILT)))   # arah pandang: depan, 15° ke bawah
P0 = (0.0, -D / 2 + 9.0, ZC)             # titik di bidang belakang kantong kamera


def cam_plane(offset=0.0):
    o = cq.Vector(*P0) + cq.Vector(*LENS_N) * offset
    return cq.Plane(origin=o, xDir=(1, 0, 0), normal=LENS_N)


def cap():
    """Kepala kamera: muka depan tegak, kantong kamera yang dasarnya miring 15° ke bawah, rel penutup geser,
    kisi buang panas di atas-belakang."""
    h = Z_CAP - Z_TOP
    c = rrect(W, D, RC, Z_TOP, h).edges(">Z").fillet(8)
    c = c.cut(rrect(W - 2 * WALL, D - 2 * WALL, RC - WALL, Z_TOP - 1, h - WALL + 1))
    # bibir masuk ke selubung
    c = c.union(rrect(W - 2 * WALL - 2 * CLR, D - 2 * WALL - 2 * CLR, RC - WALL, Z_TOP - 5, 5)
                .cut(rrect(W - 2 * WALL - 2 * CLR - 4, D - 2 * WALL - 2 * CLR - 4, RC - WALL - 2, Z_TOP - 5, 5)))
    # pelat kamera miring di belakang kantong, lalu kantongnya
    c = c.union(cq.Workplane(cam_plane()).rect(52, 42).extrude(-3.0))
    c = c.cut(cq.Workplane(cam_plane()).rect(40, 32).extrude(30))
    c = c.cut(cq.Workplane(cam_plane()).circle(6.6).extrude(12, both=True))
    # boss M2 untuk Camera Module 3 (lubang 21 × 12.5) di belakang pelat
    pts = [(x, v) for x in (-10.5, 10.5) for v in (0.6, -11.9)]
    c = c.union(cq.Workplane(cam_plane(-3.0)).pushPoints(pts).circle(2.4).extrude(-5.0))
    c = c.cut(cq.Workplane(cam_plane(-3.0)).pushPoints(pts).circle(0.9).extrude(-6.0))
    # rel penutup geser di muka depan (atas dan bawah kantong)
    yf = -D / 2
    for zr, sgn in ((ZC + 21.5, 1), (ZC - 21.5, -1)):
        c = c.union(cq.Workplane("XY").box(96, 4.0, 3.0).translate((0, yf - 2.0, zr + sgn * 1.0)))
        c = c.union(cq.Workplane("XY").box(96, 1.6, 4.0).translate((0, yf - 4.0 + 0.8, zr - sgn * 1.0)))
    # kisi buang panas di atas-belakang
    for i in range(6):
        c = c.cut(cq.Workplane("XY").box(70, 2.6, 20).translate((0, D / 2 - 12 - i * 5.2, Z_CAP - 5)))
    return c


def shutter():
    """Penutup lensa geser: menutup kantong kamera, digeser ke kanan saat kamera dipakai."""
    s = cq.Workplane("XY").box(46, 1.4, 40.6).edges("|Y").fillet(3)
    s = s.union(cq.Workplane("XY").box(3, 3, 14).edges("|Z").fillet(1.2).translate((20, -2.0, 0)))   # pegangan
    return s


def wall_bracket():
    b = cq.Workplane("XY").box(90, 4, 30).edges("|Y").fillet(4)
    for x in (-30, 30):
        b = b.union(cq.Workplane("XY").circle(3.5).extrude(8).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, 2, 4)))
        b = b.union(cq.Workplane("XY").circle(6.5).extrude(2).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, 8, 4)))
    for x in (-40, 0, 40):
        b = b.cut(cq.Workplane("XY").circle(2.2).extrude(10).rotate((0, 0, 0), (1, 0, 0), -90).translate((x, -5, -8)))
    return b


PARTS = {"base": base, "spine": spine, "sleeve": sleeve, "cap": cap, "shutter": shutter, "wall_bracket": wall_bracket}

if __name__ == "__main__":
    import sys
    only = sys.argv[1:] or list(PARTS)
    for name in only:
        shape = PARTS[name]()
        cq.exporters.export(shape, str(OUT / "stl" / f"airlens_concept_{name}.stl"), tolerance=0.05, angularTolerance=0.2)
        cq.exporters.export(shape, str(OUT / "step" / f"airlens_concept_{name}.step"))
        bb = shape.val().BoundingBox()
        print(f"{name:13s} {bb.xlen:6.1f} × {bb.ylen:6.1f} × {bb.zlen:6.1f}  z {bb.zmin:.1f}–{bb.zmax:.1f}")
