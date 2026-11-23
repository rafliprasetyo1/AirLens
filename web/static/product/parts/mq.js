// Modul sensor gas MQ (papan gaya FC-22): PCB biru 32 × 22 mm, sensor bertudung jaring baja ganda dengan cincin
// crimp nikel di atas dasar bakelit, trimpot biru 3296W dengan sekrup kuningan, LED PWR dan DO, header 4 pin
// (VCC GND DO AO) dengan konektor dupont betina. LM393 dan pasif ada di sisi bawah, seperti papan aslinya.
// Titik asal: pusat papan, sisi bawah PCB (y = 0). Sensor di ujung +X, header di ujung -X.
import * as THREE from "three";
import { sheet, texture, text, grain, pcb, box, cyl, chip, smd, led, lathe, instances, M, mat } from "./kit.js?v=20261123";

export const MQ = { L: 32, W: 22, T: 1.6, sensorX: 5.8, headerX: -14.2, hole: [-13.9, 8.6], pinZ: [-3.81, -1.27, 1.27, 3.81] };
const BLUE = "#1d4fa6", INK = "#f2f3ef", PAD = "#d9b45c";

let meshTex = null;
// Tenunan jaring kawat baja (satu ubin, diulang). Celah gelap = lapisan jaring kedua dan rongga di dalamnya.
function meshTextures() {
  if (meshTex) return meshTex;
  const N = 64, mk = () => { const c = document.createElement("canvas"); c.width = c.height = N; return c; };
  const col = mk(), bump = mk(), g = col.getContext("2d"), b = bump.getContext("2d");
  g.fillStyle = "#3b3f43"; g.fillRect(0, 0, N, N);
  b.fillStyle = "#000"; b.fillRect(0, 0, N, N);
  const wire = (ctx, horiz, i, over, colour) => {
    const p = i * (N / 2) + N / 4;
    const grad = horiz ? ctx.createLinearGradient(0, p - 9, 0, p + 9) : ctx.createLinearGradient(p - 9, 0, p + 9, 0);
    grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(0.3, colour); grad.addColorStop(0.5, over ? "#f4f6f8" : colour);
    grad.addColorStop(0.7, colour); grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    if (horiz) ctx.fillRect(0, p - 9, N, 18); else ctx.fillRect(p - 9, 0, 18, N);
  };
  for (const ctx of [g, b]) {
    const c = ctx === g ? "#b9bfc5" : "#bbbbbb";
    wire(ctx, true, 0, true, c); wire(ctx, true, 1, false, c);
    wire(ctx, false, 0, false, c); wire(ctx, false, 1, true, c);
    // titik silang: kawat di atas menutupi yang di bawah (pola anyaman polos)
    for (const [x, y, horizOver] of [[N / 4, N / 4, true], [3 * N / 4, 3 * N / 4, true], [3 * N / 4, N / 4, false], [N / 4, 3 * N / 4, false]]) {
      ctx.save(); ctx.beginPath(); ctx.rect(x - 9, y - 9, 18, 18); ctx.clip();
      wire(ctx, horizOver, y === N / 4 ? 0 : 1, true, c);
      if (!horizOver) wire(ctx, false, x === N / 4 ? 0 : 1, true, c);
      ctx.restore();
    }
  }
  const t = (c, srgb) => {
    const tx = new THREE.CanvasTexture(c);
    if (srgb) tx.colorSpace = THREE.SRGBColorSpace;
    tx.wrapS = tx.wrapT = THREE.RepeatWrapping;
    tx.anisotropy = 8;
    return tx;
  };
  meshTex = { col: t(col, true), bump: t(bump, false) };
  return meshTex;
}

// Badan sensor MQ: dasar bakelit, cincin crimp, tudung jaring, enam kaki di bawah papan.
function sensorBody() {
  const g = new THREE.Group();
  const base = lathe([[0, 0], [8.4, 0], [8.4, 3.0], [8.0, 3.5], [0, 3.5]], 24, 48).geo;
  g.add(new THREE.Mesh(base, M.bakelite()));
  const ring = lathe([[7.9, 2.7], [9.55, 2.9], [9.75, 3.6], [9.75, 4.4], [9.4, 4.9], [8.35, 5.15], [8.25, 5.5]], 24, 64).geo;
  g.add(new THREE.Mesh(ring, M.nickel()));
  // tudung jaring: sisi lurus lalu tepi membulat ke atap datar
  const prof = [[8.1, 4.9], [8.1, 14.2]];
  for (let a = 0; a <= 6; a++) { const t = (a / 6) * (Math.PI / 2); prof.push([7.2 + 0.9 * Math.cos(t), 14.2 + 0.9 * Math.sin(t)]); }
  prof.push([0, 15.1]);
  const { geo, length } = lathe(prof, 60, 72);
  const { col, bump } = meshTextures();
  const circ = 2 * Math.PI * 8.1, period = 0.62;     // ±0,3 mm per kawat
  const mc = col.clone(), mb = bump.clone();
  mc.repeat.set(circ / period, length / period); mb.repeat.copy(mc.repeat);
  mc.needsUpdate = mb.needsUpdate = true;
  const meshMat = new THREE.MeshStandardMaterial({ map: mc, bumpMap: mb, bumpScale: 0.6, metalness: 0.85, roughness: 0.42 });
  g.add(new THREE.Mesh(geo, meshMat));
  // enam kaki (terlihat di bawah papan saat modul diangkat)
  const legs = [];
  for (let k = 0; k < 6; k++) { const a = (k / 6) * Math.PI * 2 + Math.PI / 6; legs.push([Math.cos(a) * 4.8, -2.4, Math.sin(a) * 4.8]); }
  g.add(instances(new THREE.CylinderGeometry(0.3, 0.3, 4.8, 8), M.tin(), legs));
  return g;
}

// Trimpot 3296W: badan biru, sekrup kuningan bercelah di satu ujung atas.
function trimpot() {
  const g = new THREE.Group();
  const s = sheet(9.5, 4.8, 40);
  s.g.fillStyle = "#2457b8"; s.g.fillRect(-4.75, -2.4, 9.5, 4.8);
  const side = sheet(9.5, 10, 30);
  side.g.fillStyle = "#2457b8"; side.g.fillRect(-4.75, -5, 9.5, 10);
  text(side.g, "103", 0.6, -1.5, 1.6, { color: "#e9eef8", weight: 700 });
  text(side.g, "3296", 0.6, 1.2, 1.0, { color: "#e9eef8", weight: 600 });
  const blue = mat("potblue", () => new THREE.MeshStandardMaterial({ color: 0x2457b8, roughness: 0.42 }));
  const front = new THREE.MeshStandardMaterial({ map: texture(side), roughness: 0.42 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(4.8, 10, 9.5), [blue, front, blue, blue, blue, blue]);
  body.position.y = 5;
  g.add(body);
  const screw = cyl(1.15, 0.9, M.brass(), 0, 10, 3.3, 24);
  g.add(screw);
  g.add(box(0.35, 0.3, 2.0, mat("slot", () => new THREE.MeshStandardMaterial({ color: 0x3b2f12, roughness: 0.7 })), 0, 10.62, 3.3));
  return g;
}

// Konektor dupont betina (2,54 × 2,54 × 14 mm) dengan logam kecil di mulutnya.
export function dupontFemale() {
  const g = new THREE.Group();
  g.add(box(2.5, 14, 2.5, M.blackPlastic()));
  g.add(box(1.0, 0.4, 1.0, M.tin(), 0, -0.05, 0));
  g.add(box(2.6, 0.6, 2.6, mat("dupontrim", () => new THREE.MeshStandardMaterial({ color: 0x232427, roughness: 0.5 })), 0, 13.3, 0));
  return g;
}

function boardTextures(model) {
  const { L, W } = MQ, ppm = 26;
  const top = sheet(L, W, ppm), met = sheet(L, W, ppm), bot = sheet(L, W, ppm);
  for (const s of [top, bot]) { s.g.fillStyle = BLUE; s.g.fillRect(-L / 2, -W / 2, L, W); }
  met.g.fillStyle = "#000"; met.g.fillRect(-L / 2, -W / 2, L, W);
  const g = top.g;
  // jalur di bawah masker (sedikit lebih terang)
  g.strokeStyle = "#2a5db4"; g.lineWidth = 0.45; g.lineJoin = "round";
  for (const pts of [[[-14.2, -3.81], [-11, -3.81], [-9, -6], [-4, -6]], [[-14.2, 3.81], [-12, 3.81], [-10, 1.5], [-6, 1.5]],
    [[-14.2, -1.27], [-12.4, -1.27], [-12.4, -9], [2, -9]], [[-14.2, 1.27], [-13, 1.27], [-13, 9], [0, 9]]]) {
    g.beginPath(); pts.forEach(([x, z], i) => (i ? g.lineTo(x, z) : g.moveTo(x, z))); g.stroke();
  }
  // pad: header, kaki sensor, lubang pemasangan
  const pad = (x, z, r, sq = false) => {
    for (const [ctx, c] of [[g, PAD], [met.g, "#fff"], [bot.g, PAD]]) {
      ctx.fillStyle = c;
      const xx = ctx === bot.g ? -x : x;    // sisi bawah dicerminkan
      if (sq) ctx.fillRect(xx - r, z - r, 2 * r, 2 * r); else { ctx.beginPath(); ctx.arc(xx, z, r, 0, 7); ctx.fill(); }
    }
  };
  MQ.pinZ.forEach((z, i) => pad(MQ.headerX, z, 0.85, i === 0));
  for (let k = 0; k < 6; k++) { const a = (k / 6) * Math.PI * 2 + Math.PI / 6; pad(MQ.sensorX + Math.cos(a) * 4.8, Math.sin(a) * 4.8, 0.75); }
  pad(MQ.hole[0], MQ.hole[1], 2.3);
  // silkscreen
  const ink = { color: INK, weight: 600 };
  ["VCC", "GND", "DO", "AO"].forEach((lab, i) => text(g, lab, MQ.headerX + 2.6, MQ.pinZ[i], 0.95, { ...ink, align: "left" }));
  g.strokeStyle = INK; g.lineWidth = 0.2;
  g.beginPath(); g.arc(MQ.sensorX, 0, 10.0, 0, 7); g.stroke();
  text(g, model, -11.6, -8.0, 1.25, { ...ink, weight: 700, align: "left" });
  text(g, "PWR", -3.5, -6.8, 0.8, ink);
  text(g, "DO", -3.5, -9.0, 0.8, ink);
  g.strokeRect(-11.6, 5.8, 9.8, 5.2);   // garis besar trimpot
  g.strokeRect(-15.6, -5.3, 2.8, 10.6);
  // sisi bawah: tanda LM393 dan pasif (dilihat dari bawah)
  text(bot.g, "LM393", 8.6, 6.4, 0.9, { ...ink });
  bot.g.strokeStyle = INK; bot.g.lineWidth = 0.18; bot.g.strokeRect(5.8, 1.4, 5.6, 4.0);
  text(bot.g, `${model} gas sensor`, 4, -8.6, 1.0, ink);
  grain(top, 0.03); grain(bot, 0.03, 13);
  return { top: texture(top), metal: texture(met, { srgb: false }), bottom: texture(bot) };
}

export function buildMQ(model) {
  const { L, W, T } = MQ;
  const root = new THREE.Group();
  root.name = model;
  const tex = boardTextures(model);
  const holes = [{ x: MQ.hole[0], z: MQ.hole[1], r: 1.3 }];
  root.add(pcb({ w: L, d: W, t: T, r: 0.8, holes, top: tex.top, topMetal: tex.metal, bottom: tex.bottom, gloss: 0.4 }));
  const sensor = sensorBody();
  sensor.position.set(MQ.sensorX, T, 0);
  root.add(sensor);
  const pot = trimpot();
  pot.rotation.y = Math.PI / 2;       // sisi panjang searah X, di tepi +Z
  pot.position.set(-6.75, T, 8.4);
  root.add(pot);
  root.userData.leds = [];
  for (const [colour, z] of [[0xff2a1a, -6.8], [0x26d04a, -9.0]]) {
    const l = led(colour, -6.0, z, T, "0805");
    root.add(l); root.userData.leds.push(l.userData.lens);
  }
  root.add(smd("res", -8.6, -6.8, T, 0, "0805"), smd("res", -8.6, -9.0, T, 0, "0805"));
  // sisi bawah: LM393 SOIC-8 + pasif
  const lm = chip(4.9, 1.5, 3.9, ["LM393", "UTC 2041"], { legs: true, legSide: "z", legCount: 4 });
  lm.rotation.x = Math.PI;
  lm.position.set(-8.6, 0, 3.4);
  root.add(lm);
  for (const [k, x, z] of [["res", -3.4, 6.2], ["res", -3.4, 8.2], ["cap", 0, 8.4], ["res", -11.8, -7.6]]) {
    const p = smd(k, x, z, 0, 0, "0805"); p.rotation.x = Math.PI; root.add(p);
  }
  // header: penyangga plastik di atas papan, pin tegak, konektor dupont betina di atasnya
  root.add(box(2.5, 2.5, 10.16, M.blackPlastic(), MQ.headerX, T, 0));
  root.add(instances(new THREE.BoxGeometry(0.64, 11.4, 0.64), M.gold(), MQ.pinZ.map((z) => [MQ.headerX, T - 3.0 + 5.7, z])));
  root.add(instances(new THREE.ConeGeometry(0.8, 1.0, 14), M.tin(), MQ.pinZ.map((z) => [MQ.headerX, -0.5, z]), { rotX: Math.PI }));
  root.userData.plugs = MQ.pinZ.map((z) => {
    const d = dupontFemale();
    d.position.set(MQ.headerX, T + 2.5 + 1.0, z);
    d.userData.isPlug = true;
    root.add(d);
    return new THREE.Vector3(MQ.headerX, T + 2.5 + 1.0 + 14, z);   // titik keluarnya kabel (lokal)
  });
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return root;
}
