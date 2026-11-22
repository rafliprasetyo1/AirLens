// AirLens Beta: rakitan 3D lengkap (mm, Y ke atas, depan casing = +Z) dan adegan Three.js.
// Tata letak sama dengan hardware/enclosure-beta/beta_case.py: nampan 150 × 112 mm, breadboard 83 × 55 mm di kiri,
// sekat panas di x = 34, empat modul MQ berjajar di ruang sensor (x = 54,5) di atas penyangga 9 mm.
// Halaman (story.js) memberi keadaan yang dituju lewat setTarget(state); adegan ini hanya menggambar.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { MAX_ANISO } from "./parts/kit.js";
import { buildESP32, ESP32, pinX } from "./parts/esp32.js";
import { buildMQ, MQ } from "./parts/mq.js";
import { buildBreadboard, buildResistor, buildJumper, buildFlatJumper, parseSTL, printedMaterial, BB, colX, ROW, RAIL, WIRE } from "./parts/bench.js";

const FLOOR = 2.4, BB_X = -29, BB_TOP = FLOOR + BB.H;   // BB_X sama dengan beta_case.py (revisi USB 2026-11-22)
const MQ_X = 54.5, MQ_Y = FLOOR + 9.0;
export const SENSORS = [   // z tiga dimensi = -y CadQuery; MQ-2 paling dekat ke depan
  { model: "MQ-2", z: 39, gpio: 3, colour: WIRE.blue },
  { model: "MQ-3", z: 13, gpio: 4, colour: WIRE.yellow },
  { model: "MQ-7", z: -13, gpio: 5, colour: WIRE.violet },
  { model: "MQ-135", z: -39, gpio: 6, colour: WIRE.green },
];
const ESP_COL = 9;                                  // kolom breadboard untuk pin tengah (indeks 7)
const espColumn = (i) => ESP_COL + 7 - i;           // pin i -> kolom
const hole = (c, z) => new THREE.Vector3(BB_X + colX(c), BB_TOP, z);

// Tahap 1 (langsung): casing saja. Bagian pembuka halaman hanya menampilkan kotak tertutup, jadi casing dirender segera.
function buildCase(caseGeo) {
  const root = new THREE.Group();
  const P = {};   // bagian yang bisa digerakkan
  P.base = new THREE.Mesh(caseGeo.base, printedMaterial(0x4a5360));   // PETG abu grafit
  P.lid = new THREE.Mesh(caseGeo.lid, printedMaterial(0xe3e5e3));
  for (const m of [P.base, P.lid]) { m.castShadow = m.receiveShadow = true; m.material.transparent = true; root.add(m); }
  P.base.userData.mats = [P.base.material];
  P.lid.userData.mats = [P.lid.material];
  const A = { lid: [P.lid, null], base: [P.base, new THREE.Vector3(-62, 24, 56)] };
  return { root, P, A, signal: [], complete: false };
}

// jeda di antara modul agar halaman tetap responsif selama isi casing dibangun
const pause = () => new Promise((r) => (window.requestIdleCallback ? requestIdleCallback(() => r(), { timeout: 150 }) : setTimeout(r, 16)));

// Tahap 2 (bertahap, di latar belakang): isi casing, satu modul per jeda.
async function buildInside(kit) {
  const { root, P } = kit;
  await pause();
  // breadboard
  P.breadboard = buildBreadboard();
  P.breadboard.position.set(BB_X, FLOOR, 0);
  root.add(P.breadboard);

  // ESP32: baris kiri (-Z) di baris b, baris kanan di baris j -> baris a di sisi -Z tetap terbuka untuk kabel
  await pause();
  P.esp32 = buildESP32();
  const espCx = BB_X + colX(ESP_COL) - ESP32.headerX;
  P.esp32.position.set(espCx, BB_TOP + ESP32.plastic, (ROW.b + ROW.j) / 2);
  root.add(P.esp32);

  // modul MQ
  P.mq = [];
  for (const s of SENSORS) {
    await pause();
    const m = buildMQ(s.model);
    m.position.set(MQ_X, MQ_Y, s.z);
    root.add(m);
    P.mq.push(m);
  }
  await pause();

  // pembagi tegangan dan kabel di atas breadboard
  P.bench = new THREE.Group();
  root.add(P.bench);
  P.wires = new THREE.Group();
  root.add(P.wires);
  const signal = kit.signal;      // lintasan sinyal untuk animasi denyut: MQ AO -> pembagi -> GPIO
  P.resistors = [];
  SENSORS.forEach((s, j) => {
    const cb = 19 + 3 * j;
    const r10 = buildResistor(["brown", "black", "orange", "gold"], hole(cb, ROW.f), hole(cb, ROW.e));
    const r20 = buildResistor(["red", "black", "orange", "gold"], hole(cb, ROW.b), hole(cb, RAIL.negMinusOut));
    P.bench.add(r10, r20);
    P.resistors.push({ r10, r20 });
    // titik tengah pembagi -> GPIO (baris a, di samping tepi ESP32)
    const gp = buildJumper(s.colour, { at: hole(cb, ROW.d), kind: "male" }, { at: hole(espColumn(s.gpio), ROW.a), kind: "male" },
      [new THREE.Vector3(BB_X + colX(cb) - 4, BB_TOP + 20 + j * 2.2, ROW.c - 1.5 - j * 1.1),
        new THREE.Vector3(BB_X + colX(espColumn(s.gpio)) + 3, BB_TOP + 18 + j * 2.2, ROW.a - 2.5 - j * 0.6)], { r: 0.7 });
    P.wires.add(gp);
    // ke modul MQ lewat celah sekat (x 34, y 17–25, z ±7)
    const m = P.mq[j], plugs = m.userData.plugs.map((p) => p.clone().add(m.position));
    const zg = (k) => -5.4 + (j * 3 + k) * 0.98;
    const route = (from, plug, k, colour) => buildJumper(colour, { at: from, kind: "male" }, { at: plug, kind: "socket" }, [
      new THREE.Vector3(from.x + 6, BB_TOP + 26 + k * 1.5, (from.z + zg(k)) / 2),
      new THREE.Vector3(30, FLOOR + 19.2 + (k % 2) * 1.6, zg(k)),
      new THREE.Vector3(38, FLOOR + 19.2 + (k % 2) * 1.6, zg(k)),
      new THREE.Vector3(plug.x - 1.5, plug.y + 8, (plug.z + zg(k)) / 2 + (plug.z - zg(k)) * 0.35),
    ], { r: 0.72 });
    P.wires.add(route(hole(cb + 1, RAIL.negPlusIn), plugs[0], 0, WIRE.red));       // VCC 5 V dari rel +
    P.wires.add(route(hole(cb + 1, RAIL.negMinusOut), plugs[1], 1, WIRE.black));   // GND dari rel −
    const ao = route(hole(cb, ROW.j), plugs[3], 2, s.colour);                     // AO -> sisi atas pembagi
    P.wires.add(ao);
    // konektor dupont betina milik kabel: tetap di tempat (dan memudar bersama kabel) saat modul diangkat
    m.updateMatrixWorld(true);
    for (const plugMesh of m.children.filter((c) => c.userData.isPlug)) P.wires.attach(plugMesh);
    signal.push({ path: [ao.userData.curve, gp.userData.curve], reverse: [true, false] });
  });
  // daya ESP32: VIN -> rel +, GND -> rel − (jumper kaku rata)
  P.bench.add(buildFlatJumper(WIRE.red, hole(espColumn(14), ROW.a), hole(espColumn(14), RAIL.negPlusIn)));
  P.bench.add(buildFlatJumper(WIRE.black, hole(espColumn(13), ROW.a), hole(espColumn(13), RAIL.negMinusOut)));
  // kabel USB ke ESP32 (keluar lewat dinding -X)
  const usbAt = new THREE.Vector3(espCx - ESP32.L / 2 - 6, BB_TOP + ESP32.plastic + ESP32.T + 1.3, P.esp32.position.z);
  const plug = new THREE.Group();
  plug.add(new THREE.Mesh(new THREE.BoxGeometry(12, 4.6, 9), new THREE.MeshStandardMaterial({ color: 0x232528, roughness: 0.5 })));
  plug.position.copy(usbAt);
  P.usb = plug;
  // lewat celah micro-USB di dinding -X (beta_case.py), lalu jatuh ke meja
  const cable = new THREE.CatmullRomCurve3([usbAt.clone().add(new THREE.Vector3(-6, 0, 0)), new THREE.Vector3(-90, usbAt.y, usbAt.z),
    new THREE.Vector3(-106, usbAt.y - 9, usbAt.z + 5), new THREE.Vector3(-130, 1.9, usbAt.z + 28), new THREE.Vector3(-195, 1.9, usbAt.z + 70)]);
  const cableMesh = new THREE.Mesh(new THREE.TubeGeometry(cable, 64, 1.9, 12, false), new THREE.MeshStandardMaterial({ color: 0x26282b, roughness: 0.55 }));
  P.usb.userData.cable = cableMesh;
  P.wires.add(plug, cableMesh);

  // material milik sendiri untuk bagian yang bisa memudar
  for (const key of ["wires", "bench"]) {
    const clones = new Map();
    P[key].traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = o.receiveShadow = true;
      if (!clones.has(o.material)) { const c = o.material.clone(); c.transparent = true; clones.set(o.material, c); }
      o.material = clones.get(o.material);
    });
    P[key].userData.mats = [...clones.values()];
  }

  // titik label (lokal terhadap bagian)
  Object.assign(kit.A, {
    wroom: [P.esp32, new THREE.Vector3(ESP32.L / 2 - 14, 5.2, 0)],
    usb: [P.esp32, new THREE.Vector3(-ESP32.L / 2 + 1, 4.4, 0)],
    buttons: [P.esp32, new THREE.Vector3(-21.6, 3.6, -7.6)],
    gpio: [P.esp32, new THREE.Vector3(pinX(4.5), 2.4, -ESP32.rowZ)],
    r10: [P.resistors[1].r10, new THREE.Vector3().addVectors(hole(22, ROW.f), hole(22, ROW.e)).multiplyScalar(0.5).setY(BB_TOP + 3)],
    r20: [P.resistors[1].r20, new THREE.Vector3().addVectors(hole(22, ROW.b), hole(22, RAIL.negMinusOut)).multiplyScalar(0.5).setY(BB_TOP + 3)],
    breadboard: [P.breadboard, new THREE.Vector3(-34, BB.H, 22)],
    esp: [P.esp32, new THREE.Vector3(-10, 3, 0)],
    ...Object.fromEntries(P.mq.map((m, k) => [`mq${k}`, [m, new THREE.Vector3(MQ.sensorX, 17, 0)]])),
  });
}

// ---------------------------------------------------------------- adegan
export function createScene(canvas, { weak = false, onProgress } = {}) {
  performance.mark("airlens:mulai");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  MAX_ANISO.value = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const maxDpr = weak ? 1.5 : 2;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(26, 1, 10, 5000);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.03).texture;
  pmrem.dispose();

  // studio gelap: cahaya utama hangat kiri-atas-depan dengan bayangan lembut, isian dingin dari kanan, garis tepi dari belakang
  scene.add(new THREE.HemisphereLight(0xdfe8f4, 0x1a2436, 0.75));
  const key = new THREE.DirectionalLight(0xfff8f0, 2.4);
  key.position.set(-160, 340, 220);
  key.castShadow = true;
  key.shadow.mapSize.set(weak ? 1024 : 2048, weak ? 1024 : 2048);
  Object.assign(key.shadow.camera, { left: -150, right: 150, top: 150, bottom: -150, near: 50, far: 900 });
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  key.shadow.radius = 5;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xc9d8ec, 0.6);
  fill.position.set(260, 120, -140);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xbcd0ea, 1.1);   // memisahkan casing gelap dari latar gelap
  rim.position.set(-120, 160, -320);
  scene.add(rim);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(2400, 2400), new THREE.ShadowMaterial({ opacity: 0.45 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  let kit = null;
  const pulses = [];

  async function load(base) {
    const CASE_REV = "2026-11-22c";   // naikkan setiap STL casing diganti (STL di-cache 1 hari); samakan dengan preload di product.html
    const urls = [`${base}airlens_beta_base.stl?v=${CASE_REV}`, `${base}airlens_beta_lid.stl?v=${CASE_REV}`];
    const got = [0, 0], total = [0, 0];
    const bufs = await Promise.all(urls.map(async (u, i) => {
      const res = await fetch(u);
      if (!res.ok) throw new Error(`${u}: HTTP ${res.status}`);
      total[i] = Number(res.headers.get("Content-Length")) || [60000, 105000][i];   // gzip tidak mengirim panjang: perkiraan ukuran terkompresi
      const reader = res.body.getReader(), parts = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value); got[i] += value.byteLength;
        onProgress?.(Math.min(0.9, (got[0] + got[1]) / (total[0] + total[1])));
      }
      const out = new Uint8Array(got[i]); let o = 0;
      for (const p of parts) { out.set(p, o); o += p.byteLength; }
      return out.buffer;
    }));
    performance.mark("airlens:stl-unduh");
    kit = buildCase({ base: parseSTL(bufs[0]), lid: parseSTL(bufs[1]) });
    performance.mark("airlens:casing");
    scene.add(kit.root);
    kit.rest = { lid: kit.P.lid.position.clone(), base: kit.P.base.position.clone() };
    for (let k = 0; k < 12; k++) {
      const p = new THREE.Mesh(new THREE.SphereGeometry(1.7, 16, 12), new THREE.MeshBasicMaterial({ color: 0x0b8fd6, transparent: true }));
      p.visible = false;
      scene.add(p);
      pulses.push(p);
    }
    onProgress?.(1);
    kick();
    // isi casing dibangun bertahap; tekstur silkscreen butuh font sudah dimuat
    kit.inside = (async () => {
      await document.fonts?.ready;
      await buildInside(kit);
      Object.assign(kit.rest, Object.fromEntries(Object.entries({ breadboard: kit.P.breadboard, esp32: kit.P.esp32, bench: kit.P.bench,
        wires: kit.P.wires, ...Object.fromEntries(kit.P.mq.map((m, k) => [`mq${k}`, m])) }).map(([k, o]) => [k, o.position.clone()])));
      kit.complete = true;
      performance.mark("airlens:isi");
      kick();
    })();
    return kit;
  }

  // ---------------------------------------------------------------- keadaan
  // cur mengejar tgt dengan redaman; reduced motion -> langsung.
  const blank = () => ({ az: 35, el: 24, dist: 360, tx: 0, ty: 18, tz: 0, lid: 0, lidFade: 1, wires: 1, explode: 0,
    esp: 0, mq: [0, 0, 0, 0], pulse: 0, power: 0, spin: 0 });
  const cur = blank(), tgt = blank();
  let reduced = false, spinAngle = 0, last = performance.now(), running = false, dirty = true;

  function setTarget(s) { Object.assign(tgt, s); if (s.mq) tgt.mq = [...s.mq]; dirty = true; kick(); }
  function setReduced(v) { reduced = v; }

  const keys = ["az", "el", "dist", "tx", "ty", "tz", "lid", "lidFade", "wires", "explode", "esp", "pulse", "power", "spin"];
  function step(dt) {
    const k = reduced ? 1 : 1 - Math.exp(-dt * 4.2);
    let moving = 0;
    for (const key of keys) { const d = tgt[key] - cur[key]; cur[key] += d * k; moving = Math.max(moving, Math.abs(d)); }
    for (let i = 0; i < 4; i++) { const d = tgt.mq[i] - cur.mq[i]; cur.mq[i] += d * k; moving = Math.max(moving, Math.abs(d)); }
    return moving;
  }

  function applyPose(t) {
    if (!kit) return;
    const { P, rest } = kit, ex = cur.explode;
    const fade = (part, a) => { for (const m of part.userData.mats) m.opacity = a; part.visible = a > 0.01; };
    // tutup: naik, sedikit miring, lalu memudar
    P.lid.position.set(rest.lid.x, rest.lid.y + cur.lid * 70 + ex * 70, rest.lid.z);
    P.lid.rotation.z = cur.lid * 0.06;
    fade(P.lid, cur.lidFade);
    P.base.position.y = rest.base.y - ex * 36;
    if (!kit.complete) return;     // isi casing belum selesai dibangun
    P.breadboard.position.y = rest.breadboard.y - ex * 12;
    P.bench.position.y = rest.bench.y - ex * 12;
    P.esp32.position.y = rest.esp32.y + cur.esp * 24 + ex * 26;
    P.esp32.rotation.z = cur.esp * 0.12;
    P.mq.forEach((m, i) => { m.position.y = rest[`mq${i}`].y + cur.mq[i] * 20 + ex * 22; m.rotation.x = cur.mq[i] * 0.22 * Math.sign(m.position.z); });
    fade(P.wires, cur.wires);
    // LED menyala saat alat "hidup"
    for (const lens of [...P.esp32.userData.leds, ...P.mq.flatMap((m) => m.userData.leds)]) lens.emissiveIntensity = cur.power * 2.2;
    // denyut data sepanjang kabel sinyal: MQ -> pembagi -> GPIO
    pulses.forEach((p, idx) => {
      const sig = kit.signal[idx % 4];
      const show = cur.pulse > 0.05 && cur.wires > 0.5;
      p.visible = show;
      if (!show) return;
      const phase = ((t / 2600) + Math.floor(idx / 4) / 3 + (idx % 4) * 0.11) % 1;
      const leg = phase < 0.62 ? 0 : 1, u = leg === 0 ? phase / 0.62 : (phase - 0.62) / 0.38;
      const curve = sig.path[leg];
      curve.getPointAt(sig.reverse[leg] ? 1 - u : u, p.position);
      p.material.opacity = cur.pulse * Math.min(1, Math.sin(u * Math.PI) * 3);
    });
  }

  function placeCamera() {
    const az = THREE.MathUtils.degToRad(cur.az + spinAngle), el = THREE.MathUtils.degToRad(cur.el);
    const target = new THREE.Vector3(cur.tx, cur.ty, cur.tz);
    camera.position.set(target.x + cur.dist * Math.cos(el) * Math.sin(az), target.y + cur.dist * Math.sin(el),
      target.z + cur.dist * Math.cos(el) * Math.cos(az));
    camera.lookAt(target);
  }

  // titik label -> piksel layar (atau null bila di belakang kamera / bagian tak terlihat)
  const v = new THREE.Vector3();
  function project(name) {
    if (!kit || !kit.A[name]) return null;
    const [obj, local] = kit.A[name];
    if (!obj.visible) return null;
    if (local) v.copy(local); else {
      obj.geometry.boundingBox.getCenter(v); v.y = obj.geometry.boundingBox.max.y;
    }
    obj.localToWorld(v);
    v.project(camera);
    if (v.z > 1) return null;
    const r = canvas.getBoundingClientRect();
    return { x: r.left + (v.x * 0.5 + 0.5) * r.width, y: r.top + (-v.y * 0.5 + 0.5) * r.height };
  }

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, maxDpr));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // layar lebar: kanvas selebar layar di belakang teks; geser titik tengah gambar ke kanan (pusat di ±70 % lebar)
    // agar model berada di bagian yang bebas teks.
    const wide = !matchMedia("(max-width: 899px), (orientation: portrait)").matches;
    // HP: geser gambar ke atas agar model berada di ±45 % atas layar, di atas teks
    if (wide) camera.setViewOffset(w, h, -w * 0.2, 0, w, h); else camera.setViewOffset(w, h, 0, h * 0.24, w, h);
    camera.updateProjectionMatrix();
    dirty = true; kick();
  }

  let onFrame = null;
  function frame(now) {
    // stempel waktu rAF bisa lebih awal dari performance.now() saat kick(): jangan biarkan dt negatif
    const dt = Math.min(0.05, Math.max(0, (now - last) / 1000)); last = Math.max(last, now);
    const moving = step(dt);
    if (!reduced && cur.spin > 0.01) spinAngle += dt * 6 * cur.spin; else if (cur.spin <= 0.01) spinAngle *= 0.96;
    applyPose(now);
    placeCamera();
    renderer.render(scene, camera);
    onFrame?.();
    dirty = false;
    const animating = moving > 0.002 || (!reduced && (cur.spin > 0.01 || cur.pulse > 0.05)) || Math.abs(spinAngle) > 0.01;
    if (animating && !document.hidden) requestAnimationFrame(frame); else running = false;
  }
  function kick() { if (!running) { running = true; last = performance.now(); requestAnimationFrame(frame); } }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) kick(); });

  return { load, setTarget, setReduced, resize, project, kick, set onFrame(f) { onFrame = f; }, get kit() { return kit; }, camera };
}
