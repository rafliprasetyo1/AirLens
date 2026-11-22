"""Gabungkan casing + modul menjadi satu GLB bernama (untuk halaman produk) — sumbu Y ke atas, mm.

Node: enclosure_base, enclosure_spine, enclosure_sleeve, enclosure_cap, enclosure_shutter,
      comp_sen66, comp_co_b4_isb, comp_ads1115, comp_rpi5, comp_ai_hat_plus, comp_cam3_wide.
Juga menulis placements.json (posisi + arah tarik keluar tiap modul) untuk animasi di website.
"""
import json
import math
from pathlib import Path

import numpy as np
import trimesh
from trimesh.transformations import rotation_matrix as R, translation_matrix as T
from trimesh.visual.material import PBRMaterial

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[2]
GLB = REPO / "web/static/product/models/components"
STL = HERE / "stl"
Z2Y = R(-math.pi / 2, [1, 0, 0])            # CadQuery Z-up -> glTF Y-up: (x, y, z) -> (x, z, -y)


def pbr(rgb, metal=0.0, rough=0.55):
    return PBRMaterial(baseColorFactor=[*rgb, 255], metallicFactor=metal, roughnessFactor=rough)


SHELL = {"sleeve": (226, 228, 226), "cap": (52, 58, 66), "base": (52, 58, 66), "spine": (150, 156, 162),
         "shutter": (226, 132, 52), "wall_bracket": (52, 58, 66)}


def cq_pos(x, y, z):
    return np.array([x, z, -y])


def place(rot, pos):
    return T(pos) @ rot


import enclosure_concept as E

n = np.array(E.LENS_N)
up = np.cross(n, [1, 0, 0])                          # yDir bidang kamera (ke atas)
P0 = np.array(E.P0)


def place_cq(cols, origin):
    """Letakkan komponen dengan sumbu lokal (X, Y, Z) -> vektor cols di koordinat CadQuery, lalu ke Y-up."""
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2] = cols
    M[:3, 3] = origin
    return Z2Y @ M


CAM_TF = place_cq(([-1, 0, 0], n, up), P0 - 8.0 * n - 2.4 * up)

COMPS = {
    #  nama        : (transform, arah tarik keluar di Y-up, label)
    "sen66": (place(R(math.pi, [0, 1, 0]), cq_pos(-22, -25.0, 43.8)), [0, 0, 1], "Sensirion SEN66"),
    "co_b4_isb": (place(np.eye(4), cq_pos(24, 8, 47.5)), [1, 0, 0], "Alphasense CO-B4 + ISB"),
    "ads1115": (place(np.eye(4), cq_pos(-20, 22, 50.5)), [-1, 0, 0], "ADS1115 16-bit ADC"),
    "rpi5": (place(R(math.pi, [0, 1, 0]), cq_pos(-8, -4, 96.0)), [-1, 0, 0], "Raspberry Pi 5"),
    "ai_hat_plus": (place(R(math.pi, [0, 1, 0]), cq_pos(2, -4, 113.6)), [0, 1, 0], "AI HAT+ (Hailo)"),
    "cam3_wide": (CAM_TF, [0, 0.3, 1], "Camera Module 3 Wide"),
}


def load_component(name):
    sc = trimesh.load(GLB / f"{name}.glb", force="scene")
    return sc


def build(out_path, sleeve_op=None):
    scene = trimesh.Scene()
    for part, rgb in SHELL.items():
        if part == "wall_bracket":
            continue
        m = trimesh.load(STL / f"airlens_concept_{part}.stl")
        if part == "shutter":
            m.apply_translation([26.0, -E.D / 2 - 1.2 - 0.7, E.ZC])     # posisi terbuka (digeser ke kanan)
        m.apply_transform(Z2Y)
        mat = pbr(rgb, 0.0, 0.5)
        m.visual = trimesh.visual.TextureVisuals(material=mat)
        scene.add_geometry(m, node_name=f"enclosure_{part}", geom_name=f"enclosure_{part}")
    placements = {}
    for name, (tf, pull, label) in COMPS.items():
        sc = load_component(name)
        for node in sc.graph.nodes_geometry:
            ntf, gname = sc.graph[node]
            g = sc.geometry[gname].copy()
            g.apply_transform(tf @ ntf)
            scene.add_geometry(g, node_name=f"comp_{name}__{node}", geom_name=f"comp_{name}__{gname}",
                               parent_node_name=None)
        placements[name] = {"label": label, "pull_dir": pull,
                            "position_mm": [round(v, 2) for v in tf[:3, 3].tolist()]}
    scene.export(out_path)
    return placements


if __name__ == "__main__":
    out = REPO / "web/static/product/models"
    out.mkdir(parents=True, exist_ok=True)
    pl = build(out / "airlens_node_concept.glb")
    (out / "placements.json").write_text(json.dumps(pl, indent=2))
    print("ok", (out / "airlens_node_concept.glb").stat().st_size // 1024, "KB")
