"""AirLens node — casing menara v0.2 (parametrik, CadQuery).

Ukuran komponen = PERKIRAAN dari modul umum di pasaran (lihat COMPONENTS). Tinggi ruang dihitung dari situ,
jadi bila modul asli berbeda, ubah angkanya lalu jalankan ulang: `python3 enclosure_v2.py`.

Bagian cetak (warna = filamen yang disarankan):
  base (biru)  · core (putih) · sled (putih) · hot (putih) · cap (biru)
  sisipan kecil: lens_bezel (oranye) · pms_panel (putih) · mq_shelf (putih)
  tambahan:     spacer_ring (+20 mm bila komponen lebih tinggi) · module_clip ×n · joint_test (uji celah sambungan)
"""
import math
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).parent / "out_v2"
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------------ perkiraan komponen (mm): lebar, tinggi, tebal
COMPONENTS = {
    "esp32_devkit_v1": (52, 29, 15),   # 30-pin; tebal termasuk header. Tambah ±12 mm untuk kabel jumper.
    "esp32_cam": (41, 27, 12),         # AI-Thinker; lensa OV2640 Ø8 menonjol ±5 mm
    "pms5003": (50, 38, 21),           # Plantower; lubang masuk/keluar kipas di satu sisi
    "mq_module": (32, 22, 26),         # papan FC-22 32×22, sensor Ø20 tinggi ±18 di atas papan
    "climate": (28, 25, 12),           # muat BME280 (13×11) maupun DHT22 (25×15×8)
    "power": (40, 25, 15),             # breakout USB-C / pembagi daya 5 V
}

R, WALL = 50.0, 3.0
RI = R - WALL
CLR = 0.3
SPIG_H, SPIG_T = 6.0, 2.2
LUG_H, LUG_W, LUG_D = 2.4, 8.0, 1.3
TWIST = 22.0
WIRE = 12.0                            # ruang kabel jumper

# tinggi tiap ruang diturunkan dari komponen
H_BASE = 3 + COMPONENTS["climate"][1] + 10            # lantai + kantong iklim + ruang kabel
front_stack = COMPONENTS["esp32_devkit_v1"][1] + COMPONENTS["esp32_cam"][1] + 3 * 6
H_CORE = max(front_stack, COMPONENTS["pms5003"][1] + COMPONENTS["power"][1] + 18) + SPIG_H + 4
H_HOT = SPIG_H + 3 + COMPONENTS["mq_module"][2] + 14  # rak + modul MQ + ruang udara panas di atasnya
Z_CORE = H_BASE
Z_HOT = Z_CORE + H_CORE
Z_CAP = Z_HOT + H_HOT
VENT_TILT = 32.0                       # kemiringan kisi spiral (derajat)


def tube(r_out, r_in, z0, h):
    return cq.Workplane("XY").workplane(offset=z0).circle(r_out).circle(r_in).extrude(h)


def disk(r, z0, h):
    return cq.Workplane("XY").workplane(offset=z0).circle(r).extrude(h)


def sector(r_out, r_in, a0, a1, z0, h):
    pts = [(0, 0)] + [((r_out + 5) * math.cos(math.radians(a)), (r_out + 5) * math.sin(math.radians(a)))
                      for a in [a0 + (a1 - a0) * i / 12 for i in range(13)]]
    wedge = cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(h)
    return tube(r_out, r_in, z0, h).intersect(wedge)


def spiral_vents(angles, w, h, zc, tilt=VENT_TILT):
    """Celah miring: kotak radial yang dimiringkan pada sumbu radialnya -> pola spiral naik."""
    acc = None
    for a in angles:
        c = (cq.Workplane("XY").box(WALL * 4, w, h).rotate((0, 0, 0), (1, 0, 0), tilt)
             .translate((R, 0, zc)).rotate((0, 0, 0), (0, 0, 1), a))
        acc = c if acc is None else acc.union(c)
    return acc


def radial_hole(a, z, d):
    return (cq.Workplane("YZ").circle(d / 2).extrude(WALL * 4).translate((R - WALL * 2, 0, z))
            .rotate((0, 0, 0), (0, 0, 1), a))


def male_joint(z_top):
    r_o = RI - CLR
    s = tube(r_o, r_o - SPIG_T, z_top, SPIG_H)
    half = LUG_W / r_o * 180 / math.pi / 2
    for a in (0, 180):
        s = s.union(sector(r_o + LUG_D, r_o - 0.5, a - half, a + half, z_top + SPIG_H - LUG_H - 0.8, LUG_H))
    return s


def female_slots(z_bottom):
    half = (LUG_W + 1.0) / RI * 180 / math.pi / 2
    cut = None
    for a in (0, 180):
        down = sector(RI + LUG_D + 0.4, RI - 0.5, a - half, a + half, z_bottom - 0.01, SPIG_H - 0.8 + 0.01)
        turn = sector(RI + LUG_D + 0.4, RI - 0.5, a - half, a + half + TWIST, z_bottom + SPIG_H - LUG_H - 1.0, LUG_H + 0.4)
        c = down.union(turn)
        cut = c if cut is None else cut.union(c)
    return cut


def logo_mark(zc, depth=0.8, s=1.0):
    """Lambang AirLens (cincin terbuka + 3 garis angin + titik) dicekungkan ke dinding depan."""
    ring = (cq.Workplane("YZ").circle(11 * s).circle(8.6 * s).extrude(8)
            .cut(cq.Workplane("YZ").polyline([(0, 0), (16 * s, -6 * s), (16 * s, 6 * s)]).close().extrude(8)))
    lines = cq.Workplane("YZ")
    for dz, l, dy in ((3.6, 10, -1), (0, 15, 1.5), (-3.6, 8, -0.5)):
        lines = lines.union(cq.Workplane("YZ").center(dy * s, dz * s).slot2D(l * s, 2.0 * s).extrude(8))
    dot = cq.Workplane("YZ").center(14.5 * s, 0).circle(1.6 * s).extrude(8)
    mark = ring.union(lines).union(dot)
    # sumbu Y-lokal YZ = +Y dunia; letakkan di permukaan depan (+X) lalu potong sedalam `depth`
    return mark.translate((R - depth, 0, zc))


# ================================================================== BAGIAN UTAMA
def make_base():
    b = tube(R, RI, 0, H_BASE).union(disk(R, 0, 3))
    b = b.cut(spiral_vents(range(0, 360, 12), 3.2, H_BASE - 16, H_BASE / 2 + 1))
    b = b.cut(cq.Workplane("XY").box(14, 16, 10, centered=(True, True, False)).translate((-R, 0, 3)))   # takik kabel
    for a in (45, 135, 225, 315):
        b = b.union(cq.Workplane("XY").circle(6).extrude(2).translate((38 * math.cos(math.radians(a)), 38 * math.sin(math.radians(a)), -2)))
    b = b.cut(cq.Workplane("XY").polygon(6, 11.2 / math.cos(math.pi / 6)).extrude(5.5).translate((0, 0, -2)))
    b = b.cut(cq.Workplane("XY").circle(3.4).extrude(10).translate((0, 0, -2)))
    # kantong iklim universal (BME280 atau DHT22): dinding rendah + 2 lubang M2,5 bersirip udara
    w, d, _ = COMPONENTS["climate"]
    pocket = (cq.Workplane("XY").rect(w + 5, d + 5).extrude(8).translate((-18, 0, 3))
              .cut(cq.Workplane("XY").rect(w + 1, d + 1).extrude(9).translate((-18, 0, 4))))
    pocket = pocket.cut(cq.Workplane("XY").box(w + 8, 6, 5, centered=(True, True, False)).translate((-18, 0, 7)))
    b = b.union(pocket)
    for x in (-8, 8):
        b = b.cut(cq.Workplane("XY").circle(1.3).extrude(6).translate((-18 + x, 0, 1)))
    return b.union(male_joint(H_BASE))


def make_core():
    c = tube(R, RI, Z_CORE, H_CORE).cut(female_slots(Z_CORE))
    z_cam = Z_CORE + H_CORE - SPIG_H - 4 - COMPONENTS["esp32_cam"][1] / 2
    c = c.cut(radial_hole(0, z_cam, 22))                                   # bukaan untuk sisipan cincin lensa
    for dy in (-15, 15):                                                    # lubang sekrup M2 cincin lensa
        c = c.cut(radial_hole(0, z_cam, 2.2).translate((0, dy, 0)))
    c = c.union(sector(R + 8, R - 0.5, -16, 16, z_cam + 14, 2.4))         # tudung kamera
    # jendela PMS5003 + 4 lubang sekrup panel
    z_pms = Z_CORE + SPIG_H + 6 + COMPONENTS["pms5003"][1] / 2
    win = cq.Workplane("XY").box(WALL * 4, 30, 40).translate((R, 0, z_pms)).rotate((0, 0, 0), (0, 0, 1), 105)
    c = c.cut(win)
    for dy, dz in ((-19, -24), (19, -24), (-19, 24), (19, 24)):
        c = c.cut(radial_hole(105, z_pms + dz, 2.2).translate((0, 0, 0)).rotate((0, 0, 0), (0, 0, 1), dy / R * 180 / math.pi))
    # kisi spiral kecil di punggung
    c = c.cut(spiral_vents(range(160, 260, 10), 3.0, 30, Z_CORE + H_CORE / 2))
    # rel sled
    for s in (1, -1):
        for x in (2.6, -2.6):
            rib = cq.Workplane("XY").box(1.6, 5, H_CORE - 10, centered=(True, True, False)).translate((x, s * (RI - 1.5), Z_CORE + 5))
            c = c.union(rib.intersect(disk(RI + 0.5, Z_CORE, H_CORE)))
    return c.union(male_joint(Z_CORE + H_CORE))


def make_sled():
    w, h = 2 * (RI - 0.6), H_CORE - SPIG_H - 6
    z0 = Z_CORE + SPIG_H + 1
    p = cq.Workplane("YZ").rect(w, h).extrude(3).translate((-1.5, 0, z0 + h / 2)).intersect(disk(RI - 0.6, z0, h))
    holes = None
    for y in range(-40, 41, 10):
        for z in range(int(z0 + 5), int(z0 + h - 3), 10):
            hc = cq.Workplane("YZ").circle(1.6).extrude(5).translate((-2.5, y, z))
            holes = hc if holes is None else holes.union(hc)
    # celah kabel vertikal di tengah (kabel pindah sisi depan/belakang)
    p = p.cut(holes).cut(cq.Workplane("XY").box(6, 6, h - 16).translate((0, 0, z0 + h / 2)))
    p = p.union(cq.Workplane("XY").box(3, 26, 9, centered=(True, True, False)).translate((0, 0, z0 + h)))
    return p.cut(cq.Workplane("YZ").circle(4.5).extrude(5).translate((-2.5, 0, z0 + h + 4.5)))


def make_hot():
    t = tube(R, RI, Z_HOT, H_HOT).cut(female_slots(Z_HOT))
    z_rack = Z_HOT + SPIG_H + 0.5
    # dudukan rak MQ yang bisa dilepas: 3 tonjolan penyangga
    for a in (60, 180, 300):
        t = t.union(sector(RI, RI - 4, a - 6, a + 6, z_rack - 3, 3))
    # kisi spiral rapat, panel depan dibiarkan polos untuk logo
    angs = [a for a in range(0, 360, 8) if not (-26 <= ((a + 180) % 360) - 180 <= 26)]
    t = t.cut(spiral_vents(angs, 3.0, H_HOT - SPIG_H - 16, z_rack + (H_HOT - SPIG_H) / 2 - 2))
    return t.cut(logo_mark(z_rack + (H_HOT - SPIG_H) / 2 - 2)).union(male_joint(Z_HOT + H_HOT))


def make_mq_shelf():
    """Rak MQ universal: 3 posisi dengan lubang lonjong (jarak lubang modul 18–30 mm) + lubang kabel."""
    z = Z_HOT + SPIG_H + 0.5
    s = disk(RI - 0.6, z, 2.5).cut(disk(9, z - 1, 5))
    for a in (90, 210, 330):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        cx, cy = 23 * ca, 23 * sa
        for side in (-1, 1):
            slot = (cq.Workplane("XY").slot2D(12, 3.0).extrude(5).rotate((0, 0, 0), (0, 0, 1), a + 90)
                    .translate((cx + side * 12 * math.cos(math.radians(a + 90)), cy + side * 12 * math.sin(math.radians(a + 90)), z - 1)))
            s = s.cut(slot)
        s = s.cut(cq.Workplane("XY").box(10, 4, 5).rotate((0, 0, 0), (0, 0, 1), a).translate((cx * 0.55, cy * 0.55, z + 1)))
    for a in (60, 180, 300):   # takik agar rak duduk di 3 penyangga dan tidak berputar
        s = s.cut(sector(RI, RI - 1.2, a - 7, a + 7, z - 1, 5))
    return s


def make_cap():
    collar = SPIG_H + 1.5
    c = tube(R, RI, Z_CAP, collar).cut(female_slots(Z_CAP))
    gap = 9.0
    for a in (45, 135, 225, 315):
        c = c.union(sector(R, RI, a - 6, a + 6, Z_CAP + collar, gap))
    rz = Z_CAP + collar + gap
    outer = (cq.Workplane("XY").workplane(offset=rz).circle(R + 5).extrude(2.5)
             .faces(">Z").workplane().circle(R + 5).workplane(offset=8).circle(20).loft())
    inner = (cq.Workplane("XY").workplane(offset=rz - 0.01).circle(R + 2.5).workplane(offset=8).circle(18).loft())
    roof = outer.cut(inner).union(disk(R + 5, rz, 2.0).cut(disk(R - 6, rz - 1, 4)))
    drip = tube(R + 5, R + 3.4, rz - 4, 4)
    return c.union(roof).union(drip)


# ================================================================== SISIPAN & TAMBAHAN
def make_lens_bezel():
    """Cincin lensa (oranye): flens Ø40 + sumbat Ø21,6 masuk ke bukaan core; lubang lensa Ø11 (ubah bila perlu)."""
    z_cam = Z_CORE + H_CORE - SPIG_H - 4 - COMPONENTS["esp32_cam"][1] / 2
    flange = (cq.Workplane("YZ").circle(20).extrude(12).translate((R - 6, 0, z_cam))
              .intersect(tube(R + 2.4, R + 0.05, z_cam - 25, 50)))          # flens melengkung mengikuti dinding
    b = flange.union(cq.Workplane("YZ").circle(10.8).extrude(WALL + 1.0).translate((R - WALL - 0.4, 0, z_cam)))
    b = b.cut(cq.Workplane("YZ").circle(5.5).extrude(10).translate((R - 6, 0, z_cam)))
    for dy in (-15, 15):
        b = b.cut(cq.Workplane("YZ").circle(1.2).extrude(10).translate((R - 6, dy, z_cam)))
    return b


def make_pms_panel():
    """Panel jendela PMS5003: kisi horizontal, disekrup 4×M2. Cetak ulang saja bila posisi port berbeda."""
    z_pms = Z_CORE + SPIG_H + 6 + COMPONENTS["pms5003"][1] / 2
    half = 23 / R * 180 / math.pi
    p = sector(R + 2.2, R + 0.1, -half, half, z_pms - 28, 56)                 # panel melengkung mengikuti dinding
    for i in range(7):
        p = p.cut(cq.Workplane("XY").box(10, 26, 2.6).translate((R + 1, 0, z_pms - 15 + i * 5)))
    for dy, dz in ((-19, -24), (19, -24), (-19, 24), (19, 24)):
        p = p.cut(cq.Workplane("YZ").circle(1.1).extrude(8).translate((R - 3, dy, z_pms + dz)))
    return p.rotate((0, 0, 0), (0, 0, 1), 105)


def make_spacer_ring(h=20.0, z0=0.0):
    s = tube(R, RI, z0, h).cut(female_slots(z0))
    s = s.cut(spiral_vents(range(0, 360, 12), 3.0, h - 10, z0 + h / 2))
    return s.union(male_joint(z0 + h))


def make_module_clip():
    """Klip universal: kaki ke sled (M3) + jepit lebar 1–2 mm untuk papan berukuran tak standar."""
    c = cq.Workplane("XY").box(14, 10, 3).union(cq.Workplane("XY").box(3, 10, 14).translate((5.5, 0, 5.5)))
    c = c.union(cq.Workplane("XY").box(5, 10, 2).translate((4.5, 0, 11.5)))
    c = c.cut(cq.Workplane("XY").box(2.2, 12, 2).translate((3.4, 0, 9.0)))   # alur papan PCB 1,6 mm
    return c.cut(cq.Workplane("XY").slot2D(7, 3.4).extrude(5).translate((-2, 0, -2)))


def make_joint_test():
    """Cincin uji 12 mm: satu spigot + satu kerah alur-L. Cetak dulu untuk memastikan celah 0,3 mm pas."""
    male = tube(R, RI, 0, 4).union(male_joint(4))
    female = tube(R, RI, 14, 8).cut(female_slots(14))
    return male.union(female.translate((0, 0, 0)))


# ================================================================== elektronik tiruan (visualisasi)
def bx(sx, sy, sz, x, y, z):
    return cq.Workplane("XY").box(sx, sy, sz).translate((x, y, z))


def electronics():
    e, C = {}, COMPONENTS
    z_esp = Z_CORE + SPIG_H + 6 + C["esp32_devkit_v1"][1] / 2
    e["esp32"] = bx(C["esp32_devkit_v1"][2], C["esp32_devkit_v1"][0], C["esp32_devkit_v1"][1], 1.5 + C["esp32_devkit_v1"][2] / 2, 0, z_esp)
    z_cam = Z_CORE + H_CORE - SPIG_H - 4 - C["esp32_cam"][1] / 2
    e["esp32cam"] = bx(C["esp32_cam"][2], C["esp32_cam"][0], C["esp32_cam"][1], 1.5 + C["esp32_cam"][2] / 2 + 14, 0, z_cam).union(
        cq.Workplane("YZ").circle(4).extrude(R - 3 - (1.5 + C["esp32_cam"][2] + 14)).translate((1.5 + C["esp32_cam"][2] + 14, 0, z_cam)))
    z_pms = Z_CORE + SPIG_H + 6 + C["pms5003"][1] / 2
    e["pms5003"] = bx(C["pms5003"][2], C["pms5003"][0], C["pms5003"][1], -1.5 - C["pms5003"][2] / 2, 15, z_pms)
    e["power"] = bx(C["power"][2], C["power"][0], C["power"][1], -1.5 - C["power"][2] / 2, -10, z_pms + C["pms5003"][1] / 2 + 6 + C["power"][1] / 2)
    e["climate"] = bx(C["climate"][0] - 3, C["climate"][1] - 3, 8, -18, 0, 9)
    top = Z_HOT + SPIG_H + 3
    for a in (90, 210, 330):
        x, y = 23 * math.cos(math.radians(a)), 23 * math.sin(math.radians(a))
        e[f"mq_{a}"] = (cq.Workplane("XY").box(32, 22, 1.6).translate((0, 0, top + 4))
                        .union(cq.Workplane("XY").circle(10).extrude(17).translate((0, 0, top + 5)))
                        .rotate((0, 0, 0), (0, 0, 1), a + 90).translate((x, y, 0)))
    return e


if __name__ == "__main__":
    parts = {
        "base": make_base(), "core": make_core(), "sled": make_sled(), "mq_shelf": make_mq_shelf(), "hot": make_hot(),
        "cap": make_cap(), "lens_bezel": make_lens_bezel(), "pms_panel": make_pms_panel(),
        "spacer_ring": make_spacer_ring(), "module_clip": make_module_clip(), "joint_test": make_joint_test(),
    }
    total = 0
    for name, wp in parts.items():
        cq.exporters.export(wp, str(OUT / f"airlens_{name}.stl"), tolerance=0.05, angularTolerance=0.1)
        cq.exporters.export(wp, str(OUT / f"airlens_{name}.step"))
        bb, v = wp.val().BoundingBox(), wp.val().Volume() / 1000
        total += v if name not in ("spacer_ring", "joint_test", "module_clip") else 0
        print(f"{name:12s} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm   {v:6.1f} cm3   valid={wp.val().isValid()}")
    for name, wp in electronics().items():
        cq.exporters.export(wp, str(OUT / f"elec_{name}.stl"), tolerance=0.1)
    print(f"H_BASE {H_BASE} H_CORE {H_CORE} H_HOT {H_HOT} tinggi total ~{Z_CAP + SPIG_H + 1.5 + 9 + 10.5:.0f} mm, volume casing utama {total:.0f} cm3")
