"""Model 3D modul konsep utama AirLens (GLB, mm, sumbu Y ke atas, alas papan di y = 0, pusat papan di x = z = 0).

Konsep utama: Raspberry Pi 5 + Active Cooler, AI HAT+ (Hailo), Camera Module 3 Wide, Sensirion SEN66,
Alphasense CO-B4 di papan ISB, ADC ADS1115. Ditambah papan breadboard untuk versi Beta.
Ukuran dari lembar data / toko resmi (lihat hardware/README.md); bentuk detail disederhanakan.
"""
import math

import numpy as np

import build_components as bc
from build_components import Part, mat

bc.M.update({
    "pcb_green": mat((18, 96, 52), 0.0, 0.5),
    "pcb_pi": mat((20, 110, 60), 0.0, 0.5),
    "alu": mat((196, 200, 206), 1.0, 0.35),
    "alu_dark": mat((120, 124, 132), 1.0, 0.4),
    "fan": mat((28, 30, 34), 0.0, 0.6),
    "sen_white": mat((228, 230, 228), 0.0, 0.45),
    "sen_green": mat((96, 178, 70), 0.0, 0.5),
    "co_body": mat((210, 214, 218), 0.0, 0.45),
    "filter": mat((60, 62, 66), 0.0, 0.85),
    "usb_blue": mat((40, 90, 200), 0.0, 0.5),
    "bb_white": mat((238, 236, 230), 0.0, 0.6),
    "bb_hole": mat((60, 60, 62), 0.0, 0.8),
    "red_line": mat((210, 50, 50), 0.0, 0.5),
    "blue_line": mat((50, 90, 210), 0.0, 0.5),
    "fpc": mat((200, 140, 50), 0.0, 0.45),
    "res_tan": mat((214, 190, 150), 0.0, 0.5),
})


def rpi5():
    """Raspberry Pi 5: papan 85 × 56, lubang M2.5 berjarak 58 × 49, plus Active Cooler resmi."""
    p = Part("rpi5")
    T = 1.6
    p.box((85, T, 56), (0, T / 2, 0), "pcb_pi")
    for x in (-39, 19):
        for z in (-24.5, 24.5):
            p.ring(3.0, 1.35, T + 0.05, (x, T / 2, z), "gold")
    # GPIO 2×20 di tepi -Z
    p.box((50.8, 2.5, 5.08), (-7.5, T + 1.25, -23.9), "plastic_black")
    for i in range(20):
        for z in (-25.17, -22.63):
            p.box((0.64, 6.0, 0.64), (-31.6 + i * 2.54, T + 3.0, z), "gold")
    # port di tepi +X: Ethernet, 2× USB3 (biru), 2× USB2
    p.box((21.0, 13.5, 16.0), (35.0, T + 6.75, 18.0), "shield")
    p.box((17.5, 16.0, 13.2), (36.5, T + 8.0, 0.0), "shield")
    p.box((0.6, 4.0, 11.0), (45.4, T + 11.5, 0.0), "usb_blue")
    p.box((0.6, 4.0, 11.0), (45.4, T + 4.5, 0.0), "usb_blue")
    p.box((17.5, 16.0, 13.2), (36.5, T + 8.0, -17.5), "shield")
    p.box((0.6, 4.0, 11.0), (45.4, T + 11.5, -17.5), "plastic_black")
    p.box((0.6, 4.0, 11.0), (45.4, T + 4.5, -17.5), "plastic_black")
    # tepi +Z: USB-C daya, 2× micro HDMI, 2× konektor kamera/display 22 pin
    p.box((9.0, 3.3, 7.5), (-31.0, T + 1.65, 25.0), "shield")
    for x in (-18.0, -4.6):
        p.box((7.0, 3.0, 7.5), (x, T + 1.5, 25.0), "shield")
    for x in (8.0, 18.0):
        p.box((3.0, 1.6, 14.0), (x, T + 0.8, 17.0), "plastic_black")
    # konektor PCIe FPC di tepi -X, tombol daya
    p.box((3.0, 1.6, 17.0), (-41.0, T + 0.8, -2.0), "plastic_black")
    p.box((2.6, 1.4, 3.2), (-41.0, T + 0.7, 14.0), "dark")
    # RP1 dan RAM
    p.box((9.0, 1.0, 9.0), (10.0, T + 0.5, 8.0), "chip")
    p.box((14.0, 1.0, 10.0), (-8.0, T + 0.5, 11.0), "chip")
    # Active Cooler: blok sirip aluminium + kipas
    cx, cz = -12.0, -2.0
    p.box((52.0, 2.0, 40.0), (cx, T + 4.0, cz), "alu")
    for i in range(14):
        p.box((1.0, 6.5, 40.0), (cx - 25.0 + i * 1.9, T + 8.25, cz), "alu")
    p.ring(15.0, 13.6, 7.0, (cx + 10.0, T + 8.5, cz), "fan")
    p.cyl(13.6, 1.0, (cx + 10.0, T + 6.2, cz), "fan")
    p.cyl(4.5, 6.5, (cx + 10.0, T + 8.5, cz), "fan")
    for k in range(9):
        a = k * 2 * math.pi / 9
        p.box((8.0, 0.8, 2.6), (cx + 10.0 + 8.5 * math.cos(a), T + 9.5, cz + 8.5 * math.sin(a)), "fan", rot_y=-a)
    for x, z in ((cx - 23, cz - 17), (cx + 23, cz - 17), (cx - 23, cz + 17), (cx + 23, cz + 17)):
        p.cyl(1.4, 3.0, (x, T + 1.5, z), "white", sections=12)
    return p.save()


def ai_hat_plus():
    """AI HAT+ (Hailo, 26 TOPS): papan 65 × 56.5 di atas penyangga 16 mm, kabel pita PCIe ke Pi."""
    p = Part("ai_hat_plus")
    T = 1.6
    p.box((65.0, T, 56.5), (0, T / 2, 0), "pcb_black")
    p.box((22.0, 1.4, 42.0), (8.0, T + 0.7, 2.0), "pcb_green")      # modul M.2 Hailo
    p.box((12.0, 1.6, 12.0), (8.0, T + 2.2, 2.0), "shield")
    p.box((50.8, 8.0, 5.08), (-0.5, -4.0, -23.9), "plastic_black")   # header susun di bawah papan
    for x in (-29, 29):
        for z in (-24.5, 24.5):
            p.cyl(2.6, 16.0, (x, -8.0, z), "steel", sections=16)
    p.box((2.0, 14.0, 16.0), (-33.5, -6.0, -2.0), "fpc")            # pita PCIe turun ke Pi
    return p.save()


def cam3_wide():
    """Camera Module 3 Wide: 25 × 24 × 12.4 mm, IMX708, lensa 120° diagonal."""
    p = Part("cam3_wide")
    T = 1.0
    p.box((25.0, T, 24.0), (0, T / 2, 0), "pcb_green")
    for x in (-10.5, 10.5):
        for z in (-9.5, 3.0):
            p.ring(1.6, 1.1, T + 0.05, (x, T / 2, z), "gold")
    p.box((9.0, 4.4, 9.0), (0, T + 2.2, 2.4), "plastic_black")
    p.cyl(5.6, 4.6, (0, T + 4.4 + 2.3, 2.4), "plastic_black")
    p.ring(5.6, 4.4, 0.6, (0, T + 9.3, 2.4), "steel")
    p.cyl(4.4, 1.6, (0, T + 10.2, 2.4), "glass")
    p.box((16.0, 2.4, 5.0), (0, -1.2, -9.5), "plastic_black")          # konektor FPC
    p.box((16.0, 0.3, 18.0), (0, -0.3, -21.0), "fpc")
    return p.save()


def sen66():
    """Sensirion SEN66: 55 × 26 × 21 mm (X × Z × tinggi). Lubang masuk dan keluar udara di sisi -Z."""
    p = Part("sen66")
    p.box((55.0, 21.0, 26.0), (0, 10.5, 0), "sen_white")
    p.box((55.2, 1.2, 26.2), (0, 20.6, 0), "alu_dark")
    p.box((30.0, 0.15, 12.0), (-6.0, 21.25, 2.0), "sen_green")          # label
    for x0, w in ((-17.0, 16.0), (16.0, 14.0)):                          # kisi masuk (kiri) dan keluar (kanan)
        p.box((w, 12.0, 0.6), (x0, 9.0, -13.1), "plastic_black")
        for k in range(5):
            p.box((w, 0.9, 0.8), (x0, 4.0 + k * 2.6, -13.3), "sen_white")
    for x in (-20.0, 20.0):
        p.box((8.0, 4.0, 3.0), (x, 4.0, 13.8), "white")                 # JST-GH daya & data
    return p.save()


def co_b4_isb():
    """Alphasense CO-B4 (sel elektrokimia Ø32 mm) terpasang menghadap ke bawah di papan ISB."""
    p = Part("co_b4_isb")
    T = 1.6
    p.box((40.0, T, 40.0), (0, T / 2, 0), "pcb_green")
    for x in (-8, -3, 3, 8):
        p.box((3.0, 1.2, 2.0), (x, T + 0.6, 14.0), "chip")              # op-amp penguat
    p.box((12.0, 6.0, 5.0), (0, T + 3.0, -16.5), "white")               # konektor keluaran
    p.cyl(16.0, 16.5, (0, -8.25, 0), "co_body")                         # badan sensor di bawah papan
    p.ring(16.2, 13.0, 1.0, (0, -16.0, 0), "steel")
    p.cyl(13.0, 0.4, (0, -16.6, 0), "filter")
    p.cyl(3.0, 0.6, (0, -16.9, 0), "dark")
    return p.save()


def ads1115():
    p = Part("ads1115")
    T = 1.6
    p.box((28.0, T, 17.5), (0, T / 2, 0), "pcb_blue")
    p.box((5.0, 1.0, 4.0), (2.0, T + 0.5, 0), "chip")
    for i in range(10):
        p.box((0.64, 6.0, 0.64), (-11.43 + i * 2.54, -2.5, -7.0), "gold")
    p.box((25.4, 2.5, 2.5), (0, -1.25, -7.0), "plastic_black")
    return p.save()


def breadboard_half():
    """Breadboard 400 lubang (83 × 55 × 8.5) untuk versi Beta."""
    p = Part("breadboard_half")
    H = 8.5
    p.box((83.0, H, 55.0), (0, H / 2, 0), "bb_white")
    p.box((83.0, 0.4, 2.4), (0, H, 0), "bb_hole")                       # parit tengah
    for zr in (-23.5, -21.0, 21.0, 23.5):                                # rel daya
        for i in range(25):
            p.box((1.0, 0.2, 1.0), (-36.0 + i * 3.0, H + 0.05, zr), "bb_hole")
    p.box((80.0, 0.2, 0.5), (0, H + 0.05, -25.8), "red_line")
    p.box((80.0, 0.2, 0.5), (0, H + 0.05, 25.8), "blue_line")
    for i in range(30):
        for j in range(5):
            for s in (-1, 1):
                p.box((1.0, 0.2, 1.0), (-37.7 + i * 2.54, H + 0.05, s * (3.8 + j * 2.54)), "bb_hole")
    return p.save()


if __name__ == "__main__":
    for f in (rpi5, ai_hat_plus, cam3_wide, sen66, co_b4_isb, ads1115, breadboard_half):
        path = f()
        print(path.name, f"{path.stat().st_size / 1024:.0f} KB")
