// ESP32 DevKit V1 (30 pin): papan 51,5 × 28,3 × 1,6 mm, masker hitam, modul ESP-WROOM-32 di ujung antena (+X),
// micro-USB, tombol EN dan BOOT, CP2102, regulator AMS1117, dua LED, header 2 × 15 pin (jarak baris 25,4 mm).
// Titik asal: pusat papan, sisi bawah PCB (y = 0). Pin menancap ke bawah melewati penyangga plastik header.
import * as THREE from "three";
import { sheet, texture, text, grain, pcb, box, cyl, chip, smd, led, instances, M, mat } from "./kit.js?v=20261122b";

export const ESP32 = {
  L: 51.5, W: 28.3, T: 1.6,
  headerX: 1.0,          // pusat header relatif pusat papan (sedikit ke arah antena)
  rowZ: 12.7,            // baris pin di z = ±12,7 (jarak 25,4 mm)
  plastic: 2.5,          // tinggi penyangga plastik header di bawah papan
  // label pin, indeks 0 = ujung antena (+X). Kiri = sisi -Z.
  left: ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27", "D14", "D12", "D13", "GND", "VIN"],
  right: ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "TX2", "RX2", "D4", "D2", "D15", "GND", "3V3"],
};
export const pinX = (i) => ESP32.headerX + (7 - i) * 2.54;

const MASK = "#16191c", INK = "#eeeee8", PAD = "#d9b45c";

function boardTextures() {
  const { L, W } = ESP32, ppm = 26;
  const col = sheet(L, W, ppm), met = sheet(L, W, ppm);
  const g = col.g, m = met.g;
  g.fillStyle = MASK; g.fillRect(-L / 2, -W / 2, L, W);
  m.fillStyle = "#000"; m.fillRect(-L / 2, -W / 2, L, W);

  // jalur tembaga di bawah masker: sedikit lebih terang dari masker
  g.strokeStyle = "#20262b"; g.lineWidth = 0.28; g.lineJoin = "round";
  const trace = (pts) => { g.beginPath(); pts.forEach(([x, z], i) => (i ? g.lineTo(x, z) : g.moveTo(x, z))); g.stroke(); };
  for (let i = 1; i < 13; i++) {
    const x = pinX(i), zl = -ESP32.rowZ, zr = ESP32.rowZ;
    if (x < 1) {
      trace([[x, zl + 1.2], [x, zl + 3 + (i % 3)], [x + 2, zl + 5 + (i % 3)], [Math.min(x + 6, 0), zl + 5 + (i % 3)]]);
      trace([[x, zr - 1.2], [x, zr - 3 - (i % 3)], [x + 2, zr - 5 - (i % 3)], [Math.min(x + 6, 0), zr - 5 - (i % 3)]]);
    }
  }
  trace([[-25, -2], [-20, -2], [-17, 1], [-11, 1]]);
  trace([[-25, 2], [-21, 2], [-19, 4], [-12, 4]]);
  trace([[-18, -5], [-8, -5], [-5, -8], [0, -8]]);
  // bidang tembaga (ground pour) samar di sekitar modul
  g.fillStyle = "rgba(255,255,255,0.018)"; g.fillRect(-2, -10, 4, 20);

  // pad pin: cincin emas + lubang (solder di atasnya digambar sebagai mesh)
  for (let i = 0; i < 15; i++) for (const z of [-ESP32.rowZ, ESP32.rowZ]) {
    const x = pinX(i);
    for (const [ctx, c] of [[g, PAD], [m, "#fff"]]) {
      ctx.fillStyle = c;
      if (i === 0 && z < 0) ctx.fillRect(x - 0.85, z - 0.85, 1.7, 1.7);   // pin 1 bujur sangkar
      else { ctx.beginPath(); ctx.arc(x, z, 0.85, 0, 7); ctx.fill(); }
    }
  }
  // label pin, berdiri tegak lurus sumbu papan seperti aslinya
  ESP32.left.forEach((lab, i) => text(g, lab, pinX(i), -ESP32.rowZ + 2.9, 0.95, { rot: -90, align: "center", color: INK }));
  ESP32.right.forEach((lab, i) => text(g, lab, pinX(i), ESP32.rowZ - 2.9, 0.95, { rot: -90, align: "center", color: INK }));
  // garis pemisah label + nama papan
  g.strokeStyle = INK; g.lineWidth = 0.18;
  g.strokeRect(-24.6, -10.4, 11.6, 20.8);
  text(g, "ESP32", -8.6, 0, 1.9, { rot: -90, color: INK, weight: 700 });
  text(g, "DEVKIT V1", -6.0, 0, 1.25, { rot: -90, color: INK, weight: 600 });
  text(g, "EN", -21.6, -6.2, 0.95, { color: INK });
  text(g, "BOOT", -21.6, 6.4, 0.95, { color: INK });
  // garis besar komponen
  g.strokeRect(-16.2, 1.4, 5.6, 5.6);           // CP2102
  g.strokeRect(-17.6, -8.2, 7.4, 4.4);          // AMS1117
  g.beginPath(); g.arc(-19.2, 2.8, 0.25, 0, 7); g.fillStyle = INK; g.fill();
  // pad tempat modul (tepi bertimah tampak di samping modul)
  for (let k = 0; k < 14; k++) {
    const x = 1.2 + k * 1.27;
    for (const z of [-9.25, 9.25]) { for (const [ctx, c] of [[g, PAD], [m, "#fff"]]) { ctx.fillStyle = c; ctx.fillRect(x - 0.4, z - 0.45, 0.8, 0.9); } }
  }
  grain(col, 0.03);
  return { map: texture(col), metal: texture(met, { srgb: false }) };
}

// Modul ESP-WROOM-32: PCB modul 18 × 25,5 mm, pelindung logam beretsa, antena meander di ujung.
function wroom() {
  const g = new THREE.Group();
  const ML = 25.5, MW = 18, MT = 0.8;
  const s = sheet(ML, MW, 28), sm = sheet(ML, MW, 28);
  s.g.fillStyle = "#1a1d21"; s.g.fillRect(-ML / 2, -MW / 2, ML, MW);
  sm.g.fillStyle = "#000"; sm.g.fillRect(-ML / 2, -MW / 2, ML, MW);
  // antena meander (tembaga di bawah masker hitam: hanya sedikit lebih terang dari masker)
  const ax = ML / 2 - 6.3;
  s.g.strokeStyle = "#3a3426"; s.g.lineWidth = 0.32; s.g.lineCap = "square";
  s.g.beginPath();
  s.g.moveTo(ax + 0.4, -MW / 2 + 2.2);
  for (let k = 0; k < 4; k++) {
    const x1 = ax + 0.9 + k * 1.3, x2 = x1 + 0.65;
    s.g.lineTo(x1, -MW / 2 + 2.2); s.g.lineTo(x1, MW / 2 - 2.4); s.g.lineTo(x2, MW / 2 - 2.4); s.g.lineTo(x2, -MW / 2 + 2.2);
  }
  s.g.stroke();
  s.g.strokeRect(ax + 0.4, -MW / 2 + 1.2, 0.01, 1.0);
  text(s.g, "ESP32", ax + 3.2, MW / 2 - 0.75, 0.6, { color: "#c7c7c0" });
  // pad castellated di tepi
  for (let k = 0; k < 14; k++) for (const zz of [-MW / 2 + 0.35, MW / 2 - 0.35]) {
    const x = -ML / 2 + 0.9 + k * 1.27;
    for (const [ctx, c] of [[s.g, PAD], [sm.g, "#fff"]]) { ctx.fillStyle = c; ctx.fillRect(x - 0.4, zz - 0.35, 0.8, 0.7); }
  }
  for (let k = 0; k < 10; k++) {
    const zz = -5.7 + k * 1.27;
    for (const [ctx, c] of [[s.g, PAD], [sm.g, "#fff"]]) { ctx.fillStyle = c; ctx.fillRect(-ML / 2 + 0.05, zz - 0.4, 0.6, 0.8); }
  }
  const board = pcb({ w: ML, d: MW, t: MT, r: 0.3, top: texture(s), topMetal: texture(sm, { srgb: false }), gloss: 0.42 });
  g.add(board);

  // pelindung logam: aluminium disikat + tulisan etsa laser
  const SL = 17.6, SW = 16.6, SH = 2.4;
  const sh = sheet(SL, SW, 30), c = sh.g;
  c.fillStyle = "#c3c7cb"; c.fillRect(-SL / 2, -SW / 2, SL, SW);
  let r = 11;
  for (let i = 0; i < 900; i++) {   // goresan sikat searah X
    r = (r * 16807) % 2147483647;
    const zz = -SW / 2 + (r / 2147483647) * SW;
    c.strokeStyle = `rgba(${i % 2 ? 255 : 90},${i % 2 ? 255 : 95},${i % 2 ? 255 : 100},0.07)`;
    c.lineWidth = 0.04 + (i % 5) * 0.012;
    c.beginPath(); c.moveTo(-SL / 2, zz); c.lineTo(SL / 2, zz); c.stroke();
  }
  const etch = { color: "#6f767c", rot: -90, weight: 600 };
  text(c, "ESP-WROOM-32", 4.6, 0, 1.55, { ...etch, weight: 700 });
  text(c, "ESPRESSIF", 1.6, 0, 1.0, etch);
  text(c, "FCC ID: 2AC7Z-ESPWROOM32", -1.4, 0, 0.7, { ...etch, weight: 500 });
  text(c, "211-161007", -3.4, 0, 0.7, { ...etch, weight: 500 });
  c.strokeStyle = "#6f767c"; c.lineWidth = 0.14;
  c.beginPath(); c.arc(-6.4, 0, 1.3, 0, 7); c.stroke();
  text(c, "CE", -6.4, 0, 0.9, { ...etch, weight: 700 });
  const shieldTop = new THREE.MeshStandardMaterial({ map: texture(sh), metalness: 1, roughness: 0.36 });
  const shieldSide = M.steel();
  const shield = new THREE.Mesh(new THREE.BoxGeometry(SL, SH, SW), [shieldSide, shieldSide, shieldTop, shieldSide, shieldSide, shieldSide]);
  shield.position.set(-ML / 2 + 0.9 + SL / 2, MT + SH / 2, 0);
  g.add(shield);
  return g;
}

// Micro-USB: cangkang logam dengan mulut berlidah.
function microUSB() {
  const g = new THREE.Group();
  const shell = M.steel();
  const D = 5.6, H = 2.6, W = 7.6;
  g.add(box(D, 0.25, W, shell, 0, 0, 0));                 // bawah
  g.add(box(D, 0.25, W, shell, 0, H - 0.25, 0));          // atas
  g.add(box(D, H, 0.25, shell, 0, 0, -W / 2 + 0.125));
  g.add(box(D, H, 0.25, shell, 0, 0, W / 2 - 0.125));
  g.add(box(0.25, H, W, shell, D / 2 - 0.125, 0, 0));     // belakang
  g.add(box(D - 0.4, H - 0.5, W - 0.5, M.blackPlastic(), 0.2, 0.25, 0));   // rongga gelap
  g.add(box(D - 1.2, 0.6, 3.8, M.blackPlastic(), -0.4, 0.95, 0));          // lidah
  for (const s of [-1, 1]) g.add(box(1.6, 0.3, 1.2, shell, 1.0, 0, s * (W / 2 + 0.5)));   // kaki solder
  return g;
}

// Tombol taktil SMD dengan bingkai logam dan plunger hitam.
function tact() {
  const g = new THREE.Group();
  g.add(box(4.2, 1.1, 3.2, M.blackPlastic()));
  g.add(box(4.0, 0.25, 3.0, M.steel(), 0, 1.1, 0));
  const p = cyl(0.85, 0.55, M.blackPlastic(), 0, 1.35, 0, 20);
  g.add(p);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(box(0.6, 0.25, 0.5, M.tin(), sx * 2.3, 0, sz * 1.1));
  return g;
}

function ams1117() {
  const g = chip(6.5, 1.6, 3.5, ["AMS1117", "3.3  1734"]);
  g.position.z = 0;
  g.add(box(3.0, 0.25, 1.8, M.tin(), 0, 0.2, -2.5));          // tab
  for (const x of [-2.3, 0, 2.3]) g.add(box(0.7, 0.25, 1.6, M.tin(), x, 0.15, 2.4));
  return g;
}

export function buildESP32() {
  const { L, W, T } = ESP32;
  const root = new THREE.Group();
  root.name = "esp32";
  const tex = boardTextures();
  const board = pcb({ w: L, d: W, t: T, r: 0.9, top: tex.map, topMetal: tex.metal, mask: 0x16191c, gloss: 0.46 });
  root.add(board);

  const mod = wroom();
  mod.position.set(L / 2 - 25.5 / 2 + 0.2, T, 0);
  root.add(mod);

  const usb = microUSB();
  usb.position.set(-L / 2 + 2.2, T, 0);
  root.add(usb);
  for (const z of [-7.6, 7.6]) { const b = tact(); b.position.set(-21.6, T, z); root.add(b); }
  const cp = chip(5, 0.9, 5, ["SILABS", "CP2102", "DCL00X"]);
  cp.position.set(-13.4, T, 4.2);
  root.add(cp);
  const reg = ams1117();
  reg.position.set(-13.9, T, -6.0);
  root.add(reg);
  // pasif SMD
  const passives = [["cap", -10, -2], ["res", -10, -0.4], ["cap", -17.5, 0.6], ["res", -19.2, 6.0], ["res", -19.2, -6.0],
    ["cap", -9.0, -7.5], ["cap", -9.0, -9.2], ["res", -4.4, 3.4], ["res", -4.4, -3.4], ["cap", -3.0, 6.6], ["cap", -3.0, -6.6],
    ["res", -17.6, 8.8], ["cap", -10.2, 8.6]];
  passives.forEach(([k, x, z], i) => root.add(smd(k, x, z, T, i % 3 === 0 ? Math.PI / 2 : 0)));
  // dioda SOD-123 dekat USB
  const dio = box(2.7, 1.1, 1.6, M.epoxy(), -18.4, T, -2.6);
  root.add(dio, box(0.5, 1.12, 1.62, mat("band", () => new THREE.MeshStandardMaterial({ color: 0x9a9da0, roughness: 0.5 })), -19.4, T, -2.6));
  // LED: merah = daya, biru = GPIO2
  const ledPwr = led(0xff2a1a, -19.2, 2.8, T), ledIo = led(0x2a6bff, -19.2, -2.6 + 1.2, T);
  ledIo.position.z = -0.6;
  root.add(ledPwr, ledIo);
  root.userData.leds = [ledPwr.userData.lens, ledIo.userData.lens];

  // header: penyangga plastik di bawah papan + pin emas + fillet solder di atas
  for (const z of [-ESP32.rowZ, ESP32.rowZ]) root.add(box(38.1, ESP32.plastic, 2.5, M.blackPlastic(), ESP32.headerX, -ESP32.plastic, z));
  const pinPos = [], solder = [];
  for (let i = 0; i < 15; i++) for (const z of [-ESP32.rowZ, ESP32.rowZ]) {
    pinPos.push([pinX(i), -ESP32.plastic - 6 + 11.5 / 2, z]);   // -8,5 .. 3,0
    solder.push([pinX(i), T, z]);
  }
  root.add(instances(new THREE.BoxGeometry(0.64, 11.5, 0.64), M.gold(), pinPos));
  root.add(instances(new THREE.ConeGeometry(0.85, 1.1, 16), M.tin(), solder.map(([x, y, z]) => [x, y + 0.5, z])));
  root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return root;
}
