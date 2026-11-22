// Breadboard setengah (400 lubang), resistor karbon 1/4 W dengan gelang warna, kabel jumper, dan casing cetak dari STL.
import * as THREE from "three";
import { mergeVertices, toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";
import { sheet, texture, text, grain, box, lathe, M, mat } from "./kit.js?v=20261122c";

// ---------------------------------------------------------------- breadboard
export const BB = { L: 83, W: 55, H: 8.5, pitch: 2.54 };
export const colX = (c) => (c - 14.5) * BB.pitch;                 // kolom 0..29 (dicetak 1..30)
export const ROW = { a: -13.97, b: -11.43, c: -8.89, d: -6.35, e: -3.81, f: 3.81, g: 6.35, h: 8.89, i: 11.43, j: 13.97 };
export const RAIL = { negPlusIn: -19.05, negMinusOut: -21.59, posPlusIn: 19.05, posMinusOut: 21.59 };
export const railHole = (c) => c >= 1 && (c - 1) % 6 !== 5;      // lima kelompok berisi lima lubang

export function buildBreadboard() {
  const { L, W, H } = BB, ppm = 18;
  const col = sheet(L, W, ppm), bump = sheet(L, W, ppm);
  const g = col.g, b = bump.g;
  g.fillStyle = "#efeee8"; g.fillRect(-L / 2, -W / 2, L, W);
  b.fillStyle = "#fff"; b.fillRect(-L / 2, -W / 2, L, W);
  // parit tengah
  g.fillStyle = "#d9d8d1"; g.fillRect(-L / 2, -1.25, L, 2.5);
  b.fillStyle = "#6a6a6a"; b.fillRect(-L / 2, -1.25, L, 2.5);
  const hole = (x, z) => {
    g.fillStyle = "#c9c8c1"; g.fillRect(x - 0.75, z - 0.75, 1.5, 1.5);
    g.fillStyle = "#2a2b2d"; g.fillRect(x - 0.52, z - 0.52, 1.04, 1.04);
    g.fillStyle = "#56585b"; g.fillRect(x - 0.52, z - 0.52, 1.04, 0.22);
    b.fillStyle = "#000"; b.fillRect(x - 0.55, z - 0.55, 1.1, 1.1);
  };
  for (let c = 0; c < 30; c++) for (const z of Object.values(ROW)) hole(colX(c), z);
  for (let c = 0; c < 30; c++) if (railHole(c)) for (const z of Object.values(RAIL)) hole(colX(c), z);
  // garis rel: merah (+) di dalam, biru (−) di luar
  for (const s of [-1, 1]) {
    g.fillStyle = "#c8312b"; g.fillRect(-L / 2 + 3, s * 16.5 - 0.2, L - 6, 0.4);
    g.fillStyle = "#2b5fb3"; g.fillRect(-L / 2 + 3, s * 24.0 - 0.2, L - 6, 0.4);
    text(g, "+", -L / 2 + 1.8, s * 19.05, 1.6, { color: "#c8312b", weight: 700 });
    text(g, "−", -L / 2 + 1.8, s * 21.59, 1.6, { color: "#2b5fb3", weight: 700 });
  }
  for (const n of [1, 5, 10, 15, 20, 25, 30]) for (const s of [-1, 1]) text(g, String(n), colX(n - 1), s * 15.35, 0.95, { color: "#7b7a74", weight: 500 });
  "abcdefghij".split("").forEach((ch, k) => {
    const z = Object.values(ROW)[k];
    text(g, ch, colX(0) - 2.4, z, 1.0, { color: "#7b7a74", weight: 500 });
    text(g, ch, colX(29) + 2.4, z, 1.0, { color: "#7b7a74", weight: 500 });
  });
  grain(col, 0.02);
  const topMat = new THREE.MeshStandardMaterial({ map: texture(col), bumpMap: texture(bump, { srgb: false }), bumpScale: 1.2, roughness: 0.58 });
  const sideMat = mat("bbside", () => new THREE.MeshStandardMaterial({ color: 0xe6e5df, roughness: 0.6 }));
  const m = new THREE.Mesh(new THREE.BoxGeometry(L, H, W), [sideMat, sideMat, topMat, sideMat, sideMat, sideMat]);
  m.position.y = H / 2;
  m.castShadow = m.receiveShadow = true;
  const grp = new THREE.Group();
  grp.name = "breadboard";
  grp.add(m);
  // tonjolan pengunci di sisi panjang (seperti breadboard asli yang bisa disambung)
  for (const x of [-30, 0, 30]) grp.add(box(4, 4, 1.2, sideMat, x, 2, W / 2 + 0.6), box(4, 4, 1.2, sideMat, x, 2, -W / 2 - 0.6));
  return grp;
}

// ---------------------------------------------------------------- resistor karbon 1/4 W
const BAND = { black: 0x171717, brown: 0x6a3a1c, red: 0xc0262d, orange: 0xe0701c, gold: 0xc9a24a };
const PROFILE = [[0, -3.15], [0.75, -3.15], [1.12, -2.9], [1.22, -2.35], [1.06, -1.7], [1.0, -1.2], [1.0, 1.2], [1.06, 1.7], [1.22, 2.35],
  [1.12, 2.9], [0.75, 3.15], [0, 3.15]];
const radiusAt = (y) => { for (let i = 1; i < PROFILE.length; i++) if (PROFILE[i][1] >= y) { const [r0, y0] = PROFILE[i - 1], [r1, y1] = PROFILE[i]; return r0 + (r1 - r0) * ((y - y0) / (y1 - y0 || 1)); } return 1; };

// p0, p1: titik lubang di permukaan breadboard (koordinat induk). bands: ["brown","black","orange","gold"].
export function buildResistor(bands, p0, p1, { lift = 1.6, depth = 2.5 } = {}) {
  const g = new THREE.Group();
  const dir = new THREE.Vector3().subVectors(p1, p0); dir.y = 0;
  const len = dir.length(); dir.normalize();
  const mid = new THREE.Vector3().addVectors(p0, p1).multiplyScalar(0.5);
  const bodyY = p0.y + lift;
  const body = new THREE.Group();
  body.add(new THREE.Mesh(lathe(PROFILE, 40, 32).geo, mat("resbody", () => new THREE.MeshStandardMaterial({ color: 0xd8c497, roughness: 0.5 }))));
  [-2.3, -1.35, -0.45, 1.95].forEach((y, k) => {
    const r = radiusAt(y) + 0.03, colour = BAND[bands[k]];
    const bm = mat(`band${colour}`, () => new THREE.MeshStandardMaterial({ color: colour, roughness: 0.45, metalness: bands[k] === "gold" ? 0.9 : 0 }));
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.5, 32, 1, true), bm);
    ring.position.y = y;
    body.add(ring);
  });
  body.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  body.position.set(mid.x, bodyY, mid.z);
  g.add(body);
  // kaki timah: keluar dari badan, menekuk ke bawah, masuk ke lubang
  const pts = [
    p0.clone().setY(p0.y - depth), p0.clone().setY(bodyY - 0.6), p0.clone().setY(bodyY).addScaledVector(dir, 0.6),
    mid.clone().setY(bodyY).addScaledVector(dir, -3.0),
  ];
  const pts2 = [
    p1.clone().setY(p1.y - depth), p1.clone().setY(bodyY - 0.6), p1.clone().setY(bodyY).addScaledVector(dir, -0.6),
    mid.clone().setY(bodyY).addScaledVector(dir, 3.0),
  ];
  for (const p of [pts, pts2]) {
    const curve = new THREE.CatmullRomCurve3(p, false, "catmullrom", 0.05);
    const m = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.3, 8, false), M.tin());
    g.add(m);
  }
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  g.userData.len = len;
  return g;
}

// ---------------------------------------------------------------- kabel
export const WIRE = { red: 0xd22d2d, black: 0x1d1e21, blue: 0x1f6fd6, yellow: 0xe0b417, violet: 0x8a49c8, green: 0x2ea24f,
  orange: 0xec7a1c, white: 0xe9e9e4 };
const wireMat = (c) => mat(`wire${c}`, () => new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.38, clearcoat: 0.4, clearcoatRoughness: 0.35 }));

// Konektor dupont jantan berdiri di lubang breadboard; mengembalikan titik keluar kabel.
function maleHousing(g, at) {
  g.add(box(2.5, 12, 2.5, M.blackPlastic(), at.x, at.y, at.z));
  g.add(box(0.64, 3, 0.64, M.gold(), at.x, at.y - 3, at.z));
  return at.clone().setY(at.y + 12);
}

// Kabel jumper fleksibel. from/to: { at: Vector3, kind: "male" | "socket" } ; via: titik bantu lintasan.
export function buildJumper(colour, from, to, via = [], { r = 0.75 } = {}) {
  const g = new THREE.Group();
  const a = from.kind === "male" ? maleHousing(g, from.at) : from.at.clone();
  const b = to.kind === "male" ? maleHousing(g, to.at) : to.at.clone();
  const pts = [a, a.clone().setY(a.y + 4), ...via, b.clone().setY(b.y + 4), b];
  const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
  g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(40, pts.length * 18), r, 10, false), wireMat(colour)));
  g.userData.curve = curve;
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

// Kabel kaku pra-tekuk (jumper kit) yang rata di permukaan breadboard: isolasi berwarna, ujung timah masuk lubang.
export function buildFlatJumper(colour, p0, p1, { h = 1.0, depth = 2.5 } = {}) {
  const g = new THREE.Group();
  const y = p0.y + h, dir = new THREE.Vector3().subVectors(p1, p0).setY(0).normalize();
  const path = new THREE.CurvePath();
  const A = p0.clone().setY(p0.y - depth), B = p0.clone().setY(y), C = p1.clone().setY(y), D = p1.clone().setY(p1.y - depth);
  path.add(new THREE.LineCurve3(A, B)); path.add(new THREE.LineCurve3(B, C)); path.add(new THREE.LineCurve3(C, D));
  g.add(new THREE.Mesh(new THREE.TubeGeometry(path, 48, 0.32, 8, false), M.tin()));
  const ins = new THREE.LineCurve3(B.clone().addScaledVector(dir, 0.7), C.clone().addScaledVector(dir, -0.7));
  g.add(new THREE.Mesh(new THREE.TubeGeometry(ins, 4, 0.62, 12, false), wireMat(colour)));
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

// ---------------------------------------------------------------- casing (STL biner dari CadQuery, mm, Z ke atas)
export function parseSTL(buf) {
  const dv = new DataView(buf), n = dv.getUint32(80, true);
  const pos = new Float32Array(n * 9);
  for (let i = 0, o = 84; i < n; i++, o += 50) for (let k = 0; k < 9; k++) pos[i * 9 + k] = dv.getFloat32(o + 12 + k * 4, true);
  let geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.rotateX(-Math.PI / 2);                       // (x, y, z) CadQuery -> (x, z, -y)
  geo = toCreasedNormals(mergeVertices(geo, 1e-4), (32 * Math.PI) / 180);
  geo.computeBoundingBox();
  return geo;
}

// Plastik cetak FDM: garis lapisan 0,2 mm samar mengikuti ketinggian.
export function printedMaterial(colour) {
  const m = new THREE.MeshStandardMaterial({ color: colour, roughness: 0.66, metalness: 0 });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying float vLayerY;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvLayerY = transformed.y;");   // lokal: garis ikut bergerak bersama tutup
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying float vLayerY;")
      .replace("#include <color_fragment>", "#include <color_fragment>\n  float layer = abs(sin(vLayerY * 15.70796));\n  diffuseColor.rgb *= 0.965 + 0.035 * smoothstep(0.15, 0.9, layer);");
  };
  m.customProgramCacheKey = () => `printed-${colour}`;
  return m;
}
