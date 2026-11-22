"""Rakitan versi Beta untuk halaman produk: satu GLB, dua tampilan (dibungkus / tanpa bungkus).

Node: beta_case_base, beta_case_lid (sembunyikan keduanya untuk tampilan tanpa bungkus),
      comp_breadboard, comp_esp32, comp_mq_sensors_mq2 / _mq3 / _mq7 / _mq135 (label "4 MQ gas sensors" memakai awalan
      comp_mq_sensors), comp_resistors (empat pembagi 10 kΩ / 20 kΩ), comp_wire_<sensor>_<warna>.
Revisi Beta SHAP: empat MQ berjajar di ruang sensor (MQ-3 memakai bentuk mq_2.glb, modulnya sama).
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
Z2Y = R(-math.pi / 2, [1, 0, 0])
FLOOR = 2.4


def pbr(rgb, metal=0.0, rough=0.55):
    return PBRMaterial(baseColorFactor=[*rgb, 255], metallicFactor=metal, roughnessFactor=rough)


def at(x, y, z, ry=0.0):
    """Posisi dalam koordinat CadQuery (Z ke atas) untuk komponen GLB (Y ke atas), putar ry di sekitar sumbu tegak."""
    return T([x, z, -y]) @ R(ry, [0, 1, 0])


def tube(points_cq, r, rgb, scene, name):
    pts = np.array([[p[0], p[2], -p[1]] for p in points_cq])
    parts = []
    for a, b in zip(pts[:-1], pts[1:]):
        v = b - a
        L = np.linalg.norm(v)
        if L < 1e-6:
            continue
        c = trimesh.creation.cylinder(radius=r, height=L, sections=12)
        z = np.array([0, 0, 1.0])
        axis = np.cross(z, v / L)
        ang = math.acos(np.clip(np.dot(z, v / L), -1, 1))
        if np.linalg.norm(axis) > 1e-6:
            c.apply_transform(R(ang, axis))
        c.apply_translation((a + b) / 2)
        parts.append(c)
        parts.append(trimesh.creation.icosphere(subdivisions=1, radius=r).apply_translation(b))
    m = trimesh.util.concatenate(parts)
    m.visual = trimesh.visual.TextureVisuals(material=pbr(rgb, 0.0, 0.45))
    scene.add_geometry(m, node_name=name, geom_name=name)


def bezier(p0, p1, p2, p3, n=24):
    p0, p1, p2, p3 = map(np.array, (p0, p1, p2, p3))
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3


def add_glb(scene, name, tf, prefix):
    sc = trimesh.load(GLB / f"{name}.glb", force="scene")
    for node in sc.graph.nodes_geometry:
        ntf, gname = sc.graph[node]
        g = sc.geometry[gname].copy()
        g.apply_transform(tf @ ntf)
        scene.add_geometry(g, node_name=f"{prefix}__{node}", geom_name=f"{prefix}__{gname}")


def build():
    scene = trimesh.Scene()
    for part, rgb in (("beta_base", (52, 58, 66)), ("beta_lid", (226, 228, 226))):
        m = trimesh.load(STL / f"airlens_{part}.stl")
        m.apply_transform(Z2Y)
        m.visual = trimesh.visual.TextureVisuals(material=pbr(rgb))
        scene.add_geometry(m, node_name=f"beta_case_{part.split('_')[1]}", geom_name=f"beta_case_{part}")
    bb_top = FLOOR + 8.5
    add_glb(scene, "breadboard_half", at(-14.0, 0, FLOOR), "comp_breadboard")
    add_glb(scene, "esp32_devkit_v1", at(-28.5, 0, bb_top + 2.5), "comp_esp32")
    from beta_case import MQ_X, MQ_Y
    shapes = (("mq2", "mq_2"), ("mq3", "mq_2"), ("mq7", "mq_7"), ("mq135", "mq_135"))
    for (key, glb), y in zip(shapes, MQ_Y):
        add_glb(scene, glb, at(MQ_X, y, FLOOR + 9.0), f"comp_mq_sensors_{key}")
    # empat pembagi 10 kΩ / 20 kΩ di breadboard (AO -> GPIO34/35/32/33)
    res = []
    for j in range(4):
        for i, x in enumerate((4.0, 14.0)):
            zz = -14.0 + j * 7.0
            body = trimesh.creation.cylinder(radius=1.2, height=6.0, sections=16)
            body.apply_transform(R(math.pi / 2, [0, 1, 0]))
            body.apply_translation([x, bb_top + 3.0, zz])
            legs = [trimesh.creation.box(extents=[0.5, 3.0, 0.5]).apply_translation([x + s * 3.8, bb_top + 1.5, zz]) for s in (-1, 1)]
            lead = trimesh.creation.box(extents=[7.6, 0.5, 0.5]).apply_translation([x, bb_top + 3.0, zz])
            res += [body, lead] + legs
    rm = trimesh.util.concatenate(res)
    rm.visual = trimesh.visual.TextureVisuals(material=pbr((214, 190, 150)))
    scene.add_geometry(rm, node_name="comp_resistors", geom_name="comp_resistors")
    # kabel per sensor: breadboard -> celah sekat (x 34, z ±22) -> pin di sisi -X modul (pin ilustratif)
    sig = {"mq2": (31, 122, 224), "mq3": (209, 161, 15), "mq7": (142, 68, 201), "mq135": (43, 168, 74)}
    for j, ((key, _), y) in enumerate(zip(shapes, MQ_Y)):
        for k, (color, rgb) in enumerate((("red", (210, 40, 40)), ("black", (25, 25, 28)), ("signal", sig[key]))):
            start = (-45.0 + k * 2.54, 13.0 - j * 2.54, bb_top) if color != "signal" else (18.0, 14.0 - j * 7.0, bb_top)
            end = (MQ_X - 17.0, y - 2.54 + k * 2.54, FLOOR + 5.0)
            mid = (34, -6.0 + j * 4.0 + k * 1.2, 22.5)
            pts = np.vstack([bezier(start, (start[0], start[1], bb_top + 14), (26, mid[1], 23), mid),
                             bezier(mid, (40, mid[1], 22), (end[0] - 4, end[1], end[2] + 6), end)[1:]])
            tube(pts, 0.7, rgb, scene, f"comp_wire_{key}_{color}")
    return scene


if __name__ == "__main__":
    out = REPO / "web/static/product/models"
    out.mkdir(parents=True, exist_ok=True)
    build().export(out / "airlens_beta.glb")
    print("ok", (out / "airlens_beta.glb").stat().st_size // 1024, "KB")
