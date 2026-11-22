"""AirLens Beta — kotak cetak 3D untuk ESP32 + empat sensor MQ di breadboard (CadQuery, mm, Z ke atas).

Dua bagian: beta_base (nampan) dan beta_lid (tutup jepit). Revisi Beta SHAP: ruang sensor di sisi +X memuat empat
modul MQ (MQ-2, MQ-3, MQ-7, MQ-135) berjajar di sepanjang sumbu Y, dipisah sekat panas dari ESP32 karena empat
pemanas MQ (±600 mA) menghangatkan udara. Ruang sensor punya kisi di ujung, di dua sisi, dan di tutup.
"""
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).parent          # menulis ke stl/ dan step/ di folder ini
(OUT / "stl").mkdir(parents=True, exist_ok=True)
(OUT / "step").mkdir(parents=True, exist_ok=True)

L, Wd, H_BASE, H_LID, R, WALL, FLOOR, CLR = 150.0, 112.0, 30.0, 12.0, 8.0, 2.2, 2.4, 0.3
X_PART = 34.0                    # posisi sekat (ruang sensor di sisi +X, kedalaman ±39 mm)
MQ_X = 54.5                      # pusat modul MQ (papan 32 × 22, sisi panjang searah X)
MQ_Y = (-39.0, -13.0, 13.0, 39.0)  # MQ-2, MQ-3, MQ-7, MQ-135 berjajar


def rr(l, w, r, z0, h):
    return cq.Workplane("XY").workplane(offset=z0).rect(l, w).extrude(h).edges("|Z").fillet(r)


def beta_base():
    b = rr(L, Wd, R, 0, H_BASE).cut(rr(L - 2 * WALL, Wd - 2 * WALL, R - WALL, FLOOR, H_BASE))
    # rusuk penahan breadboard 83 × 55
    for x in (-56.0 - 1.2, 27.6 + 1.2):
        b = b.union(cq.Workplane("XY").box(2.0, 40, 4).translate((x, 0, FLOOR + 2)))
    # sekat panas dengan celah kabel di atas
    b = b.union(cq.Workplane("XY").box(2.0, Wd - 2 * WALL, 22).translate((X_PART, 0, FLOOR + 11))
                .cut(cq.Workplane("XY").box(4, 14, 8).translate((X_PART, 0, FLOOR + 19))))
    # penyangga empat modul MQ (lubang M3 berjarak 24 mm di sisi panjang papan, tinggi 9)
    for y in MQ_Y:
        for dx in (-12.0, 12.0):
            st = cq.Workplane("XY").circle(3.0).extrude(9).translate((MQ_X + dx, y, FLOOR))
            b = b.union(st).cut(cq.Workplane("XY").circle(1.3).extrude(9).translate((MQ_X + dx, y, FLOOR)))
    # kisi ruang sensor: ujung +X (di depan tiap modul) dan dua sisi panjang
    for i in range(5):
        z = 8 + i * 4
        for y in MQ_Y:
            b = b.cut(cq.Workplane("XY").box(10, 16, 2.0).translate((L / 2, y, z)))
        for s in (-1, 1):
            b = b.cut(cq.Workplane("XY").box(26, 10, 2.0).translate((MQ_X, s * Wd / 2, z)))
    # celah micro-USB ESP32 di ujung -X
    b = b.cut(cq.Workplane("XY").box(10, 13, 8).translate((-L / 2, 0, FLOOR + 14.5)))
    # lubang kait tutup
    for x in (-48, 48):
        for s in (-1, 1):
            b = b.cut(cq.Workplane("XY").box(10, 4, 1.6).translate((x, s * (Wd / 2 - WALL / 2), H_BASE - 4)))
    # kaki
    for x in (-L / 2 + 12, L / 2 - 12):
        for y in (-Wd / 2 + 12, Wd / 2 - 12):
            b = b.cut(cq.Workplane("XY").circle(4.2).extrude(0.8).translate((x, y, 0)))
    return b


def beta_lid():
    z0 = H_BASE
    lid = rr(L, Wd, R, z0, H_LID).edges(">Z").fillet(3)
    lid = lid.cut(rr(L - 2 * WALL, Wd - 2 * WALL, R - WALL, z0 - 1, H_LID - 1.8 + 1))
    # bibir masuk + kait jepit
    lip = rr(L - 2 * WALL - 2 * CLR, Wd - 2 * WALL - 2 * CLR, R - WALL, z0 - 6, 6).cut(
        rr(L - 2 * WALL - 2 * CLR - 3.2, Wd - 2 * WALL - 2 * CLR - 3.2, R - WALL - 1.6, z0 - 6, 6))
    lid = lid.union(lip)
    for x in (-48, 48):
        for s in (-1, 1):
            lid = lid.union(cq.Workplane("XY").box(9, 1.2, 1.4).translate((x, s * (Wd / 2 - WALL - CLR + 0.4), z0 - 4)))
    # kisi atas di atas empat MQ: satu kelompok celah per modul
    for y in MQ_Y:
        for i in range(7):
            lid = lid.cut(cq.Workplane("XY").box(2.4, 16, 10).translate((41 + i * 4.4, y, z0 + H_LID)))
    # tulisan timbul
    try:
        txt = (cq.Workplane("XY").workplane(offset=z0 + H_LID).center(-30, 0)
               .text("AirLens Beta", 8, 0.6, kind="bold", halign="center", valign="center"))
        lid = lid.union(txt)
    except Exception as e:      # font tidak tersedia
        print("teks dilewati:", e)
    return lid


PARTS = {"beta_base": beta_base, "beta_lid": beta_lid}

if __name__ == "__main__":
    for name, f in PARTS.items():
        s = f()
        cq.exporters.export(s, str(OUT / "stl" / f"airlens_{name}.stl"), tolerance=0.05, angularTolerance=0.2)
        cq.exporters.export(s, str(OUT / "step" / f"airlens_{name}.step"))
        bb = s.val().BoundingBox()
        print(f"{name:10s} {bb.xlen:.1f} × {bb.ylen:.1f} × {bb.zlen:.1f}")
