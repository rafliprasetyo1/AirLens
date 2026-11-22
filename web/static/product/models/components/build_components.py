"""Model 3D komponen node AirLens untuk website (GLB, satuan mm, sumbu Y ke atas, alas papan di y = 0).

Bentuknya disederhanakan tetapi mengikuti ciri yang dikenali orang: papan, modul logam, pin header, port, sensor.
Ukuran mengikuti modul yang umum dijual; jalankan ulang setelah komponen asli diukur.
"""
import math
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT = Path(__file__).parent
OUT.mkdir(exist_ok=True)


def mat(rgb, metal=0.0, rough=0.6, emissive=None):
    return PBRMaterial(baseColorFactor=[*rgb, 255], metallicFactor=metal, roughnessFactor=rough,
                       emissiveFactor=emissive, doubleSided=False)


M = {
    "pcb_black": mat((24, 26, 30), 0.0, 0.55),
    "pcb_blue": mat((22, 74, 160), 0.0, 0.5),
    "pcb_purple": mat((92, 52, 150), 0.0, 0.5),
    "module": mat((34, 38, 46), 0.0, 0.5),
    "shield": mat((205, 210, 216), 1.0, 0.28),
    "steel": mat((185, 190, 196), 1.0, 0.42),
    "gold": mat((214, 170, 70), 1.0, 0.3),
    "plastic_black": mat((18, 18, 20), 0.0, 0.7),
    "chip": mat((30, 30, 32), 0.0, 0.45),
    "white": mat((236, 236, 232), 0.0, 0.5),
    "orange": mat((214, 120, 40), 0.0, 0.5),
    "glass": mat((20, 40, 70), 0.3, 0.05),
    "led_red": mat((255, 60, 60), 0.0, 0.3, emissive=[1.0, 0.15, 0.15]),
    "led_blue": mat((70, 140, 255), 0.0, 0.3, emissive=[0.2, 0.45, 1.0]),
    "led_white": mat((250, 250, 240), 0.0, 0.2, emissive=[0.6, 0.6, 0.55]),
    "pot_blue": mat((40, 90, 210), 0.0, 0.5),
    "case_grey": mat((150, 156, 164), 0.85, 0.38),
    "dark": mat((40, 44, 50), 0.0, 0.6),
}


class Part:
    def __init__(self, name):
        self.scene = trimesh.Scene()
        self.name = name
        self.n = 0

    def add(self, mesh, m):
        mesh.visual = trimesh.visual.TextureVisuals(material=M[m])
        self.n += 1
        self.scene.add_geometry(mesh, node_name=f"{self.name}_{self.n}_{m}", geom_name=f"g{self.n}_{m}")

    def box(self, ext, c, m, rot_y=0.0):
        b = trimesh.creation.box(extents=ext)
        if rot_y:
            b.apply_transform(trimesh.transformations.rotation_matrix(rot_y, [0, 1, 0]))
        b.apply_translation(c)
        self.add(b, m)

    def cyl(self, r, h, c, m, axis="y", sections=40):
        cy = trimesh.creation.cylinder(radius=r, height=h, sections=sections)   # sumbu Z
        if axis == "y":
            cy.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
        elif axis == "x":
            cy.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        cy.apply_translation(c)
        self.add(cy, m)

    def ring(self, r_out, r_in, h, c, m):
        a = trimesh.creation.annulus(r_min=r_in, r_max=r_out, height=h, sections=48)
        a.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
        a.apply_translation(c)
        self.add(a, m)

    def header_row(self, n, pitch, x0, z, y_board_bottom, down=True):
        L = (n - 1) * pitch + 2.54
        self.box((L, 2.5, 2.5), (x0 + (n - 1) * pitch / 2, y_board_bottom - 1.25, z), "plastic_black")
        for i in range(n):
            x = x0 + i * pitch
            self.box((0.64, 6.0, 0.64), (x, y_board_bottom - 2.5 - 3.0 + 0.5, z), "gold")
            self.box((0.9, 0.5, 0.9), (x, y_board_bottom + 1.6 + 0.25, z), "gold")   # titik solder di atas

    def save(self):
        path = OUT / f"{self.name}.glb"
        self.scene.export(path)
        return path


def esp32_devkit():
    p = Part("esp32_devkit_v1")
    T = 1.6
    p.box((52, T, 28), (0, T / 2, 0), "pcb_black")
    # modul ESP32-WROOM-32 di ujung +X
    p.box((25.5, 0.8, 18), (12.5, T + 0.4, 0), "module")
    p.box((17.8, 2.6, 15.6), (9.6, T + 0.8 + 1.3, 0), "shield")
    for i, z in enumerate(np.linspace(-6.5, 6.5, 6)):          # antena PCB berliku
        p.box((0.6, 0.12, 3.0 if i % 2 else 13.0 / 5), (20.2 + i * 0.85, T + 0.86, z * 0.0 + (i % 2) * 0), "gold")
    for k in range(6):
        p.box((4.6, 0.12, 0.6), (22.4, T + 0.86, -6.5 + k * 2.6), "gold")
    p.box((0.6, 0.12, 13.6), (20.0, T + 0.86, 0), "gold")
    p.box((0.6, 0.12, 13.6), (24.8, T + 0.86, 0), "gold")
    # port micro-USB, tombol EN/BOOT, chip USB, regulator, LED
    p.box((6.0, 3.0, 8.0), (-24.2, T + 1.5, 0), "shield")
    p.box((1.0, 1.6, 5.6), (-27.15, T + 1.5, 0), "plastic_black")
    for z in (-9.5, 9.5):
        p.box((4.2, 0.7, 4.2), (-19.0, T + 0.35, z), "steel")
        p.box((2.6, 1.4, 2.6), (-19.0, T + 1.2, z), "plastic_black")
    p.box((5.0, 1.0, 5.0), (-11.5, T + 0.5, 0), "chip")
    p.box((6.5, 1.7, 3.6), (-12.5, T + 0.85, -8.6), "chip")
    p.box((3.0, 0.3, 3.6), (-16.2, T + 0.15, -8.6), "steel")
    p.box((1.6, 0.6, 0.9), (-6.0, T + 0.3, -10.5), "led_red")
    p.box((1.6, 0.6, 0.9), (-6.0, T + 0.3, 10.5), "led_blue")
    for x in (-3.0, -1.0, 1.0):
        p.box((1.0, 0.5, 0.6), (x, T + 0.25, 6.0), "dark")
    # pin header 2 × 15
    for z in (-12.7, 12.7):
        p.header_row(15, 2.54, -17.78, z, 0.0)
    return p.save()


def esp32_cam():
    p = Part("esp32_cam")
    T = 1.6
    p.box((40.5, T, 27), (0, T / 2, 0), "pcb_black")
    p.box((17.0, 2.4, 15.0), (-9.5, T + 1.2, 0), "shield")
    # slot microSD
    p.box((14.5, 1.8, 15.0), (10.0, T + 0.9, 0), "shield")
    # kamera OV2640: kabel pita oranye, badan kotak, lensa
    p.box((12.0, 0.3, 8.0), (2.0, T + 2.1, 0), "orange")
    p.box((8.5, 4.5, 8.5), (2.0, T + 2.25 + 2.0, 0), "plastic_black")
    p.cyl(4.0, 4.0, (2.0, T + 6.5 + 2.0, 0), "plastic_black")
    p.cyl(2.6, 0.3, (2.0, T + 10.6, 0), "glass")
    p.box((3.0, 1.0, 3.0), (-18.5, T + 0.5, 9.5), "led_white")          # LED flash
    p.box((1.8, 0.8, 1.4), (17.5, T + 0.4, -10.5), "led_red")
    for z in (-11.43, 11.43):
        p.header_row(8, 2.54, -8.89, z, 0.0)
    return p.save()


def pms5003():
    p = Part("pms5003")
    p.box((50, 21, 38), (0, 10.5, 0), "case_grey")
    # kipas di sisi atas
    p.ring(14.0, 12.4, 0.6, (5.0, 21.3, 0), "dark")
    p.cyl(12.4, 0.3, (5.0, 21.15, 0), "plastic_black")
    p.cyl(3.0, 0.8, (5.0, 21.5, 0), "dark")
    for k in range(7):
        p.box((10.5, 0.4, 2.2), (5.0 + 5.4 * math.cos(k * 2 * math.pi / 7), 21.45, 5.4 * math.sin(k * 2 * math.pi / 7)), "dark",
              rot_y=-k * 2 * math.pi / 7)
    # lubang masuk dan keluar udara di sisi -X
    p.box((0.6, 8.0, 12.0), (-25.2, 13.0, -9.0), "plastic_black")
    p.box((0.6, 6.0, 12.0), (-25.2, 5.5, 9.0), "plastic_black")
    for i in range(5):
        p.box((0.8, 0.8, 12.0), (-25.4, 10.0 + i * 1.6, -9.0), "case_grey")
    # konektor 8 pin putih
    p.box((10.0, 4.0, 3.5), (18.0, 4.0, 19.6), "white")
    # label
    p.box((20.0, 0.1, 10.0), (-12.0, 21.05, -8.0), "white")
    return p.save()


def mq_module(name):
    p = Part(name)
    T = 1.6
    p.box((32, T, 22), (0, T / 2, 0), "pcb_blue")
    # sensor: dasar hitam, tabung kasa logam, cincin atas
    p.cyl(10.0, 3.0, (-3.0, T + 1.5, 0), "plastic_black")
    p.cyl(9.2, 10.0, (-3.0, T + 3.0 + 5.0, 0), "steel")
    p.ring(9.6, 7.0, 1.2, (-3.0, T + 13.6, 0), "steel")
    for k in range(12):                                         # garis kasa
        a = k * math.pi / 6
        p.box((0.5, 9.6, 0.5), (-3.0 + 9.25 * math.cos(a), T + 8.0, 9.25 * math.sin(a)), "dark")
    # potensiometer, chip LM393, LED, resistor
    p.box((6.6, 4.6, 6.6), (11.0, T + 2.3, -5.0), "pot_blue")
    p.cyl(1.8, 0.8, (11.0, T + 5.0, -5.0), "white")
    p.box((5.0, 1.6, 4.0), (11.0, T + 0.8, 5.0), "chip")
    p.box((1.6, 0.6, 0.9), (13.8, T + 0.3, 9.0), "led_red")
    p.box((1.6, 0.6, 0.9), (13.8, T + 0.3, -9.6), "led_red")
    for z in (-2.0, 1.0):
        p.box((2.0, 0.6, 1.2), (7.0, T + 0.3, z), "dark")
    # 4 pin: VCC GND DO AO
    for i in range(4):
        x = 14.8
        z = -3.81 + i * 2.54
        p.box((0.64, 7.0, 0.64), (x, -2.0, z), "gold")
    p.box((2.5, 2.5, 10.5), (14.8, -1.25, 0), "plastic_black")
    return p.save()


def bme280():
    p = Part("bme280")
    T = 1.6
    p.box((13.0, T, 10.5), (0, T / 2, 0), "pcb_purple")
    p.box((2.5, 0.9, 2.5), (1.5, T + 0.45, 0), "shield")
    p.cyl(0.8, 0.5, (1.5, T + 0.95, 0.5), "dark", sections=16)
    for x in (-3.0, -1.5):
        p.box((1.0, 0.5, 0.6), (x, T + 0.25, 2.5), "dark")
    p.box((10.5, 2.5, 2.5), (-4.6 + 0.0, -1.25, 0), "plastic_black") if False else None
    for i in range(4):
        p.box((0.64, 6.0, 0.64), (-5.4, -2.5, -3.81 + i * 2.54), "gold")
    p.box((2.5, 2.5, 10.4), (-5.4, -1.25, 0), "plastic_black")
    return p.save()


if __name__ == "__main__":
    paths = [esp32_devkit(), esp32_cam(), pms5003(), mq_module("mq_2"), mq_module("mq_7"), mq_module("mq_135"), bme280()]
    for path in paths:
        print(path.name, f"{path.stat().st_size / 1024:.0f} KB")
