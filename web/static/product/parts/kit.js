// Alat bantu bersama untuk model modul AirLens Beta (mm, Y ke atas).
// Semua detail permukaan (silkscreen, pad emas, lubang breadboard, jaring baja, logam disikat) digambar di kanvas
// saat halaman dibuka, jadi tidak ada berkas tekstur yang diunduh.
import * as THREE from "three";

export const MAX_ANISO = { value: 4 };

// ---------------------------------------------------------------- kanvas
// Kanvas dalam koordinat milimeter papan: x kiri→kanan = -w/2..w/2 (sumbu X), y atas→bawah = -d/2..d/2 (sumbu Z).
export function sheet(w, d, ppm = 20) {
  const c = document.createElement("canvas");
  c.width = Math.round(w * ppm); c.height = Math.round(d * ppm);
  const g = c.getContext("2d");
  g.setTransform(ppm, 0, 0, ppm, (w / 2) * ppm, (d / 2) * ppm);
  return { c, g, w, d, ppm };
}

export function texture(s, { srgb = true, repeat = null } = {}) {
  const t = new THREE.CanvasTexture(s.c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = MAX_ANISO.value;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); }
  return t;
}

// Teks silkscreen: tinggi huruf h (mm). rot dalam derajat. align: "left" | "center" | "right".
export function text(g, str, x, y, h, { rot = 0, align = "center", weight = 600, color = "#f1f2ee", font = "Arial, Helvetica, sans-serif", stretch = 1 } = {}) {
  g.save();
  g.translate(x, y);
  g.rotate((rot * Math.PI) / 180);
  g.scale(stretch, 1);
  g.font = `${weight} ${h * 1.36}px ${font}`;   // tinggi huruf kapital ±0,73 em
  g.fillStyle = color;
  g.textAlign = align;
  g.textBaseline = "middle";
  g.fillText(str, 0, 0);
  g.restore();
}

export function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}

// Bintik halus agar permukaan tidak tampak seperti plastik CG yang rata.
export function grain(s, amount = 0.035, seed = 7) {
  const { c } = s, g = c.getContext("2d");
  const img = g.getImageData(0, 0, c.width, c.height), px = img.data;
  let r = seed;
  for (let i = 0; i < px.length; i += 4) {
    r = (r * 16807) % 2147483647;
    const n = ((r / 2147483647) - 0.5) * 255 * amount;
    px[i] += n; px[i + 1] += n; px[i + 2] += n;
  }
  g.putImageData(img, 0, 0);
}

// ---------------------------------------------------------------- material
const cache = new Map();
export function mat(key, make) {
  if (!cache.has(key)) cache.set(key, make());
  return cache.get(key);
}
export const M = {
  gold: () => mat("gold", () => new THREE.MeshStandardMaterial({ color: 0xd8b25a, metalness: 1, roughness: 0.28 })),
  tin: () => mat("tin", () => new THREE.MeshStandardMaterial({ color: 0xcfd2d4, metalness: 1, roughness: 0.22 })),
  steel: () => mat("steel", () => new THREE.MeshStandardMaterial({ color: 0xc4c8cc, metalness: 1, roughness: 0.34 })),
  nickel: () => mat("nickel", () => new THREE.MeshStandardMaterial({ color: 0xb7bcc1, metalness: 1, roughness: 0.3 })),
  brass: () => mat("brass", () => new THREE.MeshStandardMaterial({ color: 0xc9a24a, metalness: 1, roughness: 0.38 })),
  blackPlastic: () => mat("blackPlastic", () => new THREE.MeshStandardMaterial({ color: 0x17181a, roughness: 0.62 })),
  epoxy: () => mat("epoxy", () => new THREE.MeshStandardMaterial({ color: 0x1c1d1f, roughness: 0.48 })),
  bakelite: () => mat("bakelite", () => new THREE.MeshStandardMaterial({ color: 0x1a1918, roughness: 0.55 })),
  fr4: () => mat("fr4", () => new THREE.MeshStandardMaterial({ color: 0xb8a774, roughness: 0.8 })),
  ceramic: () => mat("ceramic", () => new THREE.MeshStandardMaterial({ color: 0xb0916a, roughness: 0.6 })),
  hidden: () => mat("hidden", () => { const m = new THREE.MeshBasicMaterial(); m.visible = false; return m; }),
};

// ---------------------------------------------------------------- geometri
export function box(w, h, d, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y + h / 2, z);
  return m;
}
export function cyl(r, h, material, x = 0, y = 0, z = 0, seg = 24) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), material);
  m.position.set(x, y + h / 2, z);
  return m;
}

// Persegi panjang bersudut bulat di bidang XY (pusat 0,0), lubang = [{x, z, r}] (z papan = -y bentuk).
export function rrShape(w, d, r, holes = []) {
  const s = new THREE.Shape(), x0 = -w / 2, y0 = -d / 2;
  s.moveTo(x0 + r, y0);
  s.lineTo(x0 + w - r, y0); s.quadraticCurveTo(x0 + w, y0, x0 + w, y0 + r);
  s.lineTo(x0 + w, y0 + d - r); s.quadraticCurveTo(x0 + w, y0 + d, x0 + w - r, y0 + d);
  s.lineTo(x0 + r, y0 + d); s.quadraticCurveTo(x0, y0 + d, x0, y0 + d - r);
  s.lineTo(x0, y0 + r); s.quadraticCurveTo(x0, y0, x0 + r, y0);
  for (const h of holes) { const p = new THREE.Path(); p.absarc(h.x, -h.z, h.r, 0, Math.PI * 2, true); s.holes.push(p); }
  return s;
}

// Lapisan permukaan rata (ShapeGeometry) dengan UV 0..1 terhadap kotak w×d, menghadap +Y pada ketinggian y.
// under = true: menghadap -Y (sisi bawah papan); tekstur digambar "seperti dilihat dari bawah" (u dicerminkan).
function cap(shape, w, d, y, under = false) {
  const g = new THREE.ShapeGeometry(shape, 8);
  const p = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) {
    const u = (p.getX(i) + w / 2) / w;
    uv.setXY(i, under ? 1 - u : u, (p.getY(i) + d / 2) / d);
  }
  g.rotateX(-Math.PI / 2);
  if (under) {
    const idx = g.index.array;
    for (let i = 0; i < idx.length; i += 3) { const t = idx[i]; idx[i] = idx[i + 2]; idx[i + 2] = t; }
    const n = g.attributes.normal;
    for (let i = 0; i < n.count; i++) n.setXYZ(i, 0, -1, 0);
  }
  g.translate(0, y, 0);
  return g;
}

// PCB: atas bertekstur (warna + peta logam untuk pad emas), bawah warna masker, tepi FR4.
export function pcb({ w, d, t = 1.6, r = 0.8, holes = [], top, topMetal = null, bottom = null, mask = 0x1b2024, gloss = 0.5 }) {
  const shape = rrShape(w, d, r, holes), g = new THREE.Group();
  const side = new THREE.ExtrudeGeometry(shape, { depth: t, bevelEnabled: false, curveSegments: 8 });
  side.rotateX(-Math.PI / 2);
  g.add(new THREE.Mesh(side, [M.hidden(), M.fr4()]));
  const topMat = new THREE.MeshPhysicalMaterial({ map: top, metalnessMap: topMetal, metalness: topMetal ? 1 : 0,
    roughness: gloss, clearcoat: 0.35, clearcoatRoughness: 0.4 });
  g.add(new THREE.Mesh(cap(shape, w, d, t), topMat));
  const botMat = bottom
    ? new THREE.MeshPhysicalMaterial({ map: bottom, roughness: gloss, clearcoat: 0.3 })
    : new THREE.MeshStandardMaterial({ color: mask, roughness: gloss });
  g.add(new THREE.Mesh(cap(shape, w, d, 0, true), botMat));
  return g;
}

// Profil putar dengan titik berjarak sama sepanjang lintasan (UV v merata, penting untuk tekstur jaring).
export function lathe(points, n = 48, seg = 64) {
  const pts = points.map(([x, y]) => new THREE.Vector2(x, y));
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + pts[i].distanceTo(pts[i - 1]));
  const total = lens[lens.length - 1], out = [];
  for (let k = 0; k <= n; k++) {
    const s = (k / n) * total;
    let i = 1;
    while (i < lens.length - 1 && lens[i] < s) i++;
    const f = (s - lens[i - 1]) / (lens[i] - lens[i - 1] || 1);
    out.push(new THREE.Vector2().lerpVectors(pts[i - 1], pts[i], f));
  }
  return { geo: new THREE.LatheGeometry(out, seg), length: total };
}

// Gabungkan banyak mesh kecil bermaterial sama menjadi InstancedMesh (pin header, sambungan solder, lubang).
export function instances(geo, material, positions, { rotX = 0 } = {}) {
  const m = new THREE.InstancedMesh(geo, material, positions.length), o = new THREE.Object3D();
  positions.forEach((p, i) => { o.position.set(...p); o.rotation.set(rotX, 0, 0); o.updateMatrix(); m.setMatrixAt(i, o.matrix); });
  m.instanceMatrix.needsUpdate = true;
  return m;
}

// Chip hitam dengan tulisan laser di atas (tekstur kecil sendiri).
export function chip(w, h, d, lines, { legs = null, legSide = "z", pitch = 1.27, legCount = 4 } = {}) {
  const s = sheet(w, d, 40);
  s.g.fillStyle = "#1d1e20"; s.g.fillRect(-w / 2, -d / 2, w, d);
  const lh = Math.min(d / (lines.length + 1.2), w / 6);
  lines.forEach((ln, i) => text(s.g, ln, 0, (i - (lines.length - 1) / 2) * lh * 1.25, lh, { color: "#8e9296", weight: 500 }));
  s.g.fillStyle = "#3a3c3f"; s.g.beginPath(); s.g.arc(-w / 2 + 0.6, -d / 2 + 0.6, 0.25, 0, 7); s.g.fill();   // titik pin 1
  const topMat = new THREE.MeshStandardMaterial({ map: texture(s), roughness: 0.5 });
  const mats = [M.epoxy(), M.epoxy(), topMat, M.epoxy(), M.epoxy(), M.epoxy()];
  const grp = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mats);
  body.position.y = h / 2 + (legs ? 0.15 : 0);
  grp.add(body);
  if (legs) {   // kaki gull-wing
    const lg = new THREE.BoxGeometry(legSide === "z" ? 0.4 : 1.0, 0.2, legSide === "z" ? 1.0 : 0.4);
    const pos = [];
    for (let i = 0; i < legCount; i++) {
      const o = (i - (legCount - 1) / 2) * pitch;
      for (const sgn of [-1, 1]) pos.push(legSide === "z" ? [o, 0.1, sgn * (d / 2 + 0.4)] : [sgn * (w / 2 + 0.4), 0.1, o]);
    }
    grp.add(instances(lg, M.tin(), pos));
  }
  return grp;
}

// Komponen SMD pasif (resistor hitam bertutup timah / kapasitor cokelat).
export function smd(kind, x, z, y, rot = 0, size = "0603") {
  const [L, W, H] = size === "0805" ? [2.0, 1.25, 0.5] : [1.6, 0.8, 0.45];
  const g = new THREE.Group();
  if (kind === "cap") g.add(box(L, H, W, mat("smdcap", () => new THREE.MeshStandardMaterial({ color: 0xa8875e, roughness: 0.55 }))));
  else {
    g.add(box(L * 0.7, H, W, mat("smdres", () => new THREE.MeshStandardMaterial({ color: 0x151617, roughness: 0.5 }))));
  }
  for (const s of [-1, 1]) g.add(box(L * 0.18, H + 0.02, W + 0.02, M.tin(), s * L * 0.41, -0.01, 0));
  g.position.set(x, y, z);
  g.rotation.y = rot;
  return g;
}

// LED SMD: kubah bening berwarna yang bisa menyala (emissive) saat alat dinyalakan.
export function led(colour, x, z, y, size = "0603") {
  const [L, W] = size === "0805" ? [2.0, 1.25] : [1.6, 0.8];
  const g = new THREE.Group();
  g.add(box(L, 0.25, W, mat("ledbase", () => new THREE.MeshStandardMaterial({ color: 0xe9e4d6, roughness: 0.4 }))));
  // tanpa "transmission": efek kaca itu memaksa seluruh adegan dirender dua kali per frame
  const lens = new THREE.MeshPhysicalMaterial({ color: colour, emissive: colour, emissiveIntensity: 0, roughness: 0.15, clearcoat: 0.6 });
  g.add(box(L * 0.8, 0.35, W * 0.9, lens, 0, 0.25, 0));
  for (const s of [-1, 1]) g.add(box(L * 0.15, 0.3, W + 0.02, M.tin(), s * L * 0.43, 0, 0));
  g.position.set(x, y, z);
  g.userData.lens = lens;
  return g;
}
