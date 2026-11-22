// Adegan AirLens. Semua animasi deterministik terhadap waktu t (detik dalam adegan), agar bisa dirender frame demi frame.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const W = 1920, H = 1080;
const COL = { bg: 0x060d14, sky: 0x2ba8e0, cyan: 0x4fe3f0, amber: 0xf2994a, red: 0xff4d5e, navy: 0x0f3d52 };
const canvas = document.getElementById("gl");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setSize(W, H, false);
renderer.setPixelRatio(1);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const ease = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
const lerp = (a, b, k) => a + (b - a) * k;
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

const flat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, flatShading: true, roughness: 0.85, metalness: 0.05, ...extra });
function box(w, h, d, mat, x = 0, y = 0, z = 0, parent) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; parent && parent.add(m); return m;
}
function cyl(rt, rb, h, seg, mat, x = 0, y = 0, z = 0, parent) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat);
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; parent && parent.add(m); return m;
}

function makeComposer(scene, camera, strength = 0.7) {
  const c = new EffectComposer(renderer);
  c.setSize(W, H);
  c.addPass(new RenderPass(scene, camera));
  c.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), strength, 0.6, 0.82));
  c.addPass(new OutputPass());
  return c;
}

// ---------------------------------------------------------------- tekstur kanvas
function canvasTex(w, h, draw) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d"); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  t.userData = { c, g, draw }; return t;
}
function redraw(tex, ...args) { const { g, c, draw } = tex.userData; draw(g, c.width, c.height, ...args); tex.needsUpdate = true; }

function roundRect(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r); }

// Layar monitor kecil di kamar: dasbor AirLens mini; k = tingkat asap 0..1, alert = 0..1
function drawScreen(g, w, h, k = 0, alert = 0) {
  g.fillStyle = "#081520"; g.fillRect(0, 0, w, h);
  g.fillStyle = "#0E2333"; g.fillRect(0, 0, w, 54);
  g.fillStyle = "#2BA8E0"; g.font = "700 30px SG"; g.fillText("AirLens", 24, 37);
  g.fillStyle = "#8FB0C2"; g.font = "500 20px IN"; g.fillText("Your room · live", w - 190, 35);
  // kartu angka
  const pm = Math.round(lerp(14, 41, k));
  const card = (x, label, val, col) => {
    roundRect(g, x, 80, 220, 130, 14); g.fillStyle = "#0E2333"; g.fill();
    g.fillStyle = "#8FB0C2"; g.font = "500 19px IN"; g.fillText(label, x + 18, 112);
    g.fillStyle = col; g.font = "700 46px SG"; g.fillText(val, x + 18, 172);
  };
  card(24, "PM2.5 µg/m³", String(pm), k > 0.5 ? "#F2994A" : "#3DDC97");
  card(262, "MQ-7 · CO", k > 0.4 ? "rising" : "normal", k > 0.4 ? "#FF4D5E" : "#3DDC97");
  card(500, "City AQI", "72", "#EAF4FA");
  // grafik
  g.strokeStyle = "#1C3444"; g.lineWidth = 2;
  for (let i = 0; i < 4; i++) { g.beginPath(); g.moveTo(24, 260 + i * 50); g.lineTo(w - 24, 260 + i * 50); g.stroke(); }
  g.beginPath(); g.lineWidth = 5; g.strokeStyle = k > 0.5 ? "#F2994A" : "#4FE3F0";
  const N = 60;
  for (let i = 0; i <= N; i++) {
    const x = 24 + (w - 48) * i / N, ramp = clamp((i / N - 0.55) / 0.45) * k;
    const y = 400 - 25 * Math.sin(i * 0.7) * 0.4 - ramp * 150 - 18;
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  }
  g.stroke();
  // notifikasi
  if (alert > 0) {
    const y = lerp(-120, 70, easeOut(alert));
    g.save(); g.globalAlpha = clamp(alert * 2);
    roundRect(g, w - 560, y, 536, 108, 16); g.fillStyle = "#3A1016"; g.fill();
    g.lineWidth = 4; g.strokeStyle = "#FF4D5E"; g.stroke();
    g.fillStyle = "#FF4D5E"; g.font = "700 28px SG"; g.fillText("⚠ Possible local smoke", w - 534, y + 44);
    g.fillStyle = "#F4C9CE"; g.font = "500 20px IN"; g.fillText("Detected 2 m from you · close windows", w - 534, y + 80);
    g.restore();
  }
}

// ---------------------------------------------------------------- tokoh Pak Dengklek
function makePerson() {
  const p = new THREE.Group();
  const skin = flat(0xc68a5e), shirt = flat(0x2b6cb0), pants = flat(0x1e2a36), black = flat(0x15181c), white = flat(0xf1f1f1);
  box(0.42, 0.55, 0.26, shirt, 0, 1.05, 0, p);                 // badan (duduk)
  box(0.44, 0.16, 0.5, pants, 0, 0.72, -0.12, p);              // paha
  box(0.4, 0.42, 0.14, pants, 0, 0.45, -0.34, p);              // betis
  const head = new THREE.Group(); head.position.set(0, 1.5, 0.02); p.add(head);
  const skull = new THREE.Mesh(new THREE.IcosahedronGeometry(0.17, 1), skin); skull.castShadow = true; head.add(skull);
  cyl(0.16, 0.165, 0.11, 10, black, 0, 0.12, 0, head);          // peci
  box(0.16, 0.035, 0.03, black, 0, -0.04, -0.165, head);       // kumis
  box(0.24, 0.05, 0.04, white, 0, 0.05, -0.18, head).visible = false;
  const armL = box(0.12, 0.42, 0.12, shirt, -0.28, 1.05, -0.12, p); armL.rotation.x = -1.0;
  const armR = box(0.12, 0.42, 0.12, shirt, 0.28, 1.05, -0.12, p); armR.rotation.x = -1.0;
  p.userData = { head, armL, armR };
  return p;
}

// ---------------------------------------------------------------- partikel asap
function smokeSprite() {
  return canvasTex(128, 128, (g, w) => {
    const gr = g.createRadialGradient(64, 64, 4, 64, 64, 62);
    gr.addColorStop(0, "rgba(255,255,255,0.85)"); gr.addColorStop(0.5, "rgba(255,255,255,0.35)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, w, w);
  });
}
function makeSmoke(n, origin, dir) {
  const r = rng(7), tex = smokeSprite(), group = new THREE.Group(), parts = [];
  for (let i = 0; i < n; i++) {
    const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: 0x9aa3ad, transparent: true, depthWrite: false, opacity: 0 }));
    group.add(m);
    parts.push({ m, phase: r(), speed: 0.55 + r() * 0.5, sx: (r() - 0.5) * 0.9, sy: (r() - 0.5) * 0.6, size: 0.45 + r() * 0.7, wob: r() * 6.28 });
  }
  group.userData.update = (t, amount) => {
    for (const p of parts) {
      const life = (t * p.speed * 0.28 + p.phase) % 1;
      const d = life * 2.4;
      p.m.position.set(origin.x + dir.x * d + p.sx * (0.3 + life) + Math.sin(t * 0.9 + p.wob) * 0.15,
                       origin.y + p.sy * (0.3 + life * 1.4) + life * 0.5,
                       origin.z + dir.z * d + Math.cos(t * 0.7 + p.wob) * 0.15);
      const s = p.size * (0.35 + life * 0.9); p.m.scale.set(s, s, 1);
      p.m.material.opacity = amount * Math.sin(Math.PI * life) * 0.32;
    }
  };
  return group;
}

// ================================================================ ADEGAN: KAMAR
function buildRoom() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070f17);
  scene.fog = new THREE.Fog(0x070f17, 9, 18);
  const cam = new THREE.PerspectiveCamera(38, W / H, 0.1, 60);

  const wallM = flat(0x1a2a38), floorM = flat(0x132029), trim = flat(0x0d1821), wood = flat(0x5a3b28), woodD = flat(0x3c2718);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), floorM); floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  // dinding belakang dengan lubang jendela (x 0.8..2.4, y 1.4..2.6)
  const wz = -3;
  box(4.8, 4, 0.2, wallM, -1.6, 2, wz, scene);
  box(3.6, 4, 0.2, wallM, 4.2, 2, wz, scene);
  box(1.6, 1.4, 0.2, wallM, 1.6, 0.7, wz, scene);
  box(1.6, 1.4, 0.2, wallM, 1.6, 3.3, wz, scene);
  box(0.2, 4, 7, wallM, -4, 2, 0.5, scene);   // dinding kiri
  // kusen + ambang jendela
  box(1.72, 0.08, 0.32, trim, 1.6, 1.38, wz + 0.06, scene);
  box(1.72, 0.08, 0.26, trim, 1.6, 2.62, wz, scene);
  box(0.08, 1.3, 0.26, trim, 0.76, 2.0, wz, scene);
  box(0.08, 1.3, 0.26, trim, 2.44, 2.0, wz, scene);
  // daun jendela terbuka (berputar ke dalam)
  const sash = new THREE.Group(); sash.position.set(2.44, 2.0, wz + 0.05); scene.add(sash);
  const glass = new THREE.MeshStandardMaterial({ color: 0x9fd8ff, transparent: true, opacity: 0.18, roughness: 0.1 });
  box(0.8, 1.2, 0.03, glass, -0.4, 0, 0, sash); box(0.8, 0.05, 0.05, trim, -0.4, 0.6, 0, sash); box(0.8, 0.05, 0.05, trim, -0.4, -0.6, 0, sash);
  box(0.05, 1.2, 0.05, trim, -0.8, 0, 0, sash);
  // pemandangan senja di luar
  const sky = canvasTex(1024, 512, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#1b1f4a"); gr.addColorStop(0.55, "#b4475a"); gr.addColorStop(1, "#ffa25e");
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
    const r = rng(3); g.fillStyle = "#120d20";
    for (let x = 0; x < w; x += 40 + r() * 50) { const bh = 80 + r() * 200; g.fillRect(x, h - bh, 34 + r() * 40, bh); }
    g.fillStyle = "rgba(255,210,120,.9)";
    for (let i = 0; i < 70; i++) g.fillRect(r() * w, h - r() * 220, 4, 6);
  });
  const outside = new THREE.Mesh(new THREE.PlaneGeometry(9, 4.5), new THREE.MeshBasicMaterial({ map: sky, fog: false }));
  outside.position.set(1.6, 2.2, -6); scene.add(outside);

  // meja, kursi, rak
  box(2.0, 0.07, 0.9, wood, -0.7, 0.76, -2.1, scene);
  for (const [x, z] of [[-1.62, -2.48], [0.22, -2.48], [-1.62, -1.72], [0.22, -1.72]]) box(0.06, 0.74, 0.06, woodD, x, 0.37, z, scene);
  box(0.5, 0.06, 0.5, woodD, -0.7, 0.5, -1.05, scene); box(0.5, 0.6, 0.06, woodD, -0.7, 0.82, -0.8, scene);
  for (const [x, z] of [[-0.92, -1.27], [-0.48, -1.27], [-0.92, -0.83], [-0.48, -0.83]]) box(0.04, 0.5, 0.04, woodD, x, 0.25, z, scene);
  box(0.9, 1.8, 0.35, woodD, -3.6, 0.9, -1.6, scene);
  for (let i = 0; i < 4; i++) box(0.1 + (i % 2) * 0.05, 0.3, 0.22, flat([0x2ba8e0, 0xf2994a, 0x3ddc97, 0xeaf4fa][i]), -3.75 + i * 0.13, 1.35, -1.6, scene);
  // monitor
  const screenTex = canvasTex(1100, 640, drawScreen);
  box(1.12, 0.68, 0.05, flat(0x0b0f14), -0.7, 1.24, -2.42, scene);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(1.06, 0.62), new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false }));
  scr.position.set(-0.7, 1.24, -2.39); scene.add(scr);
  box(0.08, 0.3, 0.06, flat(0x0b0f14), -0.7, 0.93, -2.44, scene);
  box(0.36, 0.03, 0.2, flat(0x0b0f14), -0.7, 0.8, -2.42, scene);
  box(0.5, 0.02, 0.16, flat(0x1b2530), -0.7, 0.8, -1.95, scene);   // keyboard
  const screenLight = new THREE.PointLight(0x5fc7ff, 1.6, 3.2); screenLight.position.set(-0.7, 1.25, -2.1); scene.add(screenLight);
  // node AirLens di ambang jendela
  const node = new THREE.Group(); node.position.set(1.15, 1.42, -2.82); scene.add(node);
  box(0.36, 0.18, 0.2, flat(0xeaf4fa), 0, 0.09, 0, node);
  box(0.36, 0.02, 0.2, flat(COL.sky), 0, 0.185, 0, node);
  for (let i = 0; i < 3; i++) cyl(0.035, 0.035, 0.06, 10, flat(0xb7c0c8, { metalness: 0.6, roughness: 0.4 }), -0.1 + i * 0.1, 0.22, 0, node);
  box(0.12, 0.12, 0.06, flat(0x111418), 0.26, 0.1, 0.02, node);                      // ESP32-CAM menghadap jendela
  const lens = cyl(0.03, 0.03, 0.03, 12, new THREE.MeshStandardMaterial({ color: 0x223344, emissive: 0x4fe3f0, emissiveIntensity: 0 }), 0.26, 0.1, -0.02, node); lens.rotation.x = Math.PI / 2;
  const flash = new THREE.PointLight(0xffffff, 0, 3); flash.position.set(1.4, 1.6, -2.7); scene.add(flash);
  // tokoh
  const person = makePerson(); person.position.set(-0.7, 0, -1.05); person.rotation.y = Math.PI; scene.add(person);
  // asap
  const smoke = makeSmoke(90, new THREE.Vector3(1.6, 1.95, -3.2), new THREE.Vector3(-0.75, 0, 0.55)); scene.add(smoke);

  // cahaya
  scene.add(new THREE.HemisphereLight(0x8fa8ff, 0x1a1420, 1.25));
  const lamp = new THREE.PointLight(0xffc98a, 9, 9, 1.6); lamp.position.set(-1.2, 3.4, -0.6); lamp.castShadow = true; scene.add(lamp);
  const dusk = new THREE.DirectionalLight(0xff9a62, 2.2); dusk.position.set(3, 3.5, -8); dusk.target.position.set(-1, 0, 0);
  dusk.castShadow = true; dusk.shadow.mapSize.set(2048, 2048); Object.assign(dusk.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6 });
  scene.add(dusk, dusk.target);
  const rim = new THREE.PointLight(0x2ba8e0, 1.2, 9); rim.position.set(-3, 3, 2); scene.add(rim);
  const alertLight = new THREE.PointLight(0xff4d5e, 0, 4); alertLight.position.set(-0.7, 1.4, -1.9); scene.add(alertLight);

  const composer = makeComposer(scene, cam, 0.55);
  return {
    render(t, o = {}) {
      const smokeK = o.smoke ?? 0, alert = o.alert ?? 0, close = o.close ?? 0;
      const cp = o.cam ?? [2.9, 2.2, 1.9], ct = o.target ?? [0.1, 1.35, -2.2];
      cam.position.set(...cp); cam.lookAt(...ct);
      sash.rotation.y = lerp(1.1, 0, ease(close));
      smoke.userData.update(t, smokeK * (1 - 0.8 * close));
      redraw(screenTex, smokeK, alert);
      alertLight.intensity = alert * (1.5 + 0.8 * Math.sin(t * 9));
      const fl = o.flash ?? 0; flash.intensity = 14 * fl; lens.material.emissiveIntensity = 3 * clamp((o.camOn ?? 0));
      const badge = o.badge ?? 0;
      if (badge > 0) {
        cam.updateMatrixWorld(); const v = new THREE.Vector3(1.4, 1.75, -2.8).project(cam);
        const d = document.createElement("div"); d.className = "evbadge";
        d.style.left = `${(v.x * 0.5 + 0.5) * W}px`; d.style.top = `${(-v.y * 0.5 + 0.5) * H}px`;
        d.style.opacity = clamp(badge * 3); d.style.transform = `translate(-50%,-100%) scale(${lerp(0.85, 1, easeOut(badge))})`;
        d.innerHTML = `<b>● REC</b> Smoke detected → event photo saved`;
        $("labels").appendChild(d);
      }
      const { head, armR } = person.userData;
      head.rotation.y = lerp(0, 0.75, ease(o.look ?? 0));
      armR.rotation.x = -1.0 + Math.sin(t * 7) * 0.05 * (1 - (o.look ?? 0));
      composer.render();
    },
  };
}

// ================================================================ ADEGAN: KOMPONEN NODE (tampilan urai)
const PARTS = [
  { key: "esp32", series: "ESP32 DevKit V1", role: "Brain + WiFi", gas: "Reads every sensor, sends data to AirLens" },
  { key: "cam", series: "ESP32-CAM", role: "Event camera", gas: "Sleeps · wakes <b>only when sensors trigger</b>" },
  { key: "pms", series: "PMS5003", role: "Particle sensor", gas: "<b>PM2.5</b> · PM10 — the ground truth" },
  { key: "mq2", series: "MQ-2", role: "Smoke sensor", gas: "<b>Smoke</b>, LPG, methane, H₂" },
  { key: "mq7", series: "MQ-7", role: "CO sensor", gas: "<b>Carbon monoxide (CO)</b>" },
  { key: "mq135", series: "MQ-135", role: "Air-quality gas", gas: "<b>NH₃</b>, NOx, benzene, CO₂" },
  { key: "bme", series: "BME280", role: "Climate", gas: "Temperature · humidity · pressure" },
];
function buildNode() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(COL.bg);
  const cam = new THREE.PerspectiveCamera(32, W / H, 0.1, 80);
  scene.add(new THREE.HemisphereLight(0x8fb8ff, 0x05080c, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 2.0); key.position.set(3, 6, 5); scene.add(key);
  const rimC = new THREE.PointLight(COL.cyan, 6, 14); rimC.position.set(-5, 2, -3); scene.add(rimC);
  const rimA = new THREE.PointLight(COL.amber, 4, 14); rimA.position.set(5, -1, -2); scene.add(rimA);

  // lantai grid bercahaya
  const grid = new THREE.GridHelper(40, 40, COL.sky, 0x12324a); grid.position.y = -2.6; grid.material.transparent = true; grid.material.opacity = 0.35; scene.add(grid);

  const pcbBlue = flat(0x1d4ed8, { roughness: 0.6 }), pcbBlack = flat(0x101820), metal = flat(0xc9d1d8, { metalness: 0.8, roughness: 0.3 });
  const gold = flat(0xd4a017, { metalness: 0.8, roughness: 0.35 }), purple = flat(0x6b3fa0), dark = flat(0x1a1f26);
  const make = {
    cam: (g) => { box(0.42, 0.05, 0.6, pcbBlack, 0, 0, 0, g); box(0.3, 0.06, 0.3, dark, 0, 0.06, -0.08, g);
      const l = cyl(0.09, 0.09, 0.08, 18, flat(0x0b0f14), 0, 0.13, -0.08, g); cyl(0.05, 0.05, 0.02, 18, new THREE.MeshStandardMaterial({ color: 0x1a3550, emissive: 0x4fe3f0, emissiveIntensity: 1.2 }), 0, 0.18, -0.08, g);
      box(0.12, 0.03, 0.14, metal, 0.1, 0.04, 0.2, g); },
    esp32: (g) => { box(1.1, 0.06, 0.5, pcbBlack, 0, 0, 0, g); box(0.5, 0.1, 0.36, metal, -0.15, 0.08, 0, g); box(0.12, 0.06, 0.1, metal, 0.5, 0.06, 0, g);
      for (let i = 0; i < 15; i++) { box(0.03, 0.12, 0.03, gold, -0.49 + i * 0.07, -0.08, 0.22, g); box(0.03, 0.12, 0.03, gold, -0.49 + i * 0.07, -0.08, -0.22, g); } },
    pms: (g) => { box(0.9, 0.45, 0.68, metal, 0, 0, 0, g); const f = cyl(0.22, 0.22, 0.02, 24, dark, 0.15, 0.23, 0, g);
      for (let i = 0; i < 6; i++) { const b = box(0.2, 0.012, 0.05, flat(0x2a323c), 0.15, 0.245, 0, g); b.rotation.y = i * Math.PI / 3; } box(0.2, 0.04, 0.06, flat(0xffffff), -0.3, 0.24, 0.2, g); },
    mq: (g, ring) => { box(0.62, 0.05, 0.62, pcbBlue, 0, 0, 0, g); cyl(0.2, 0.2, 0.22, 20, flat(ring), 0, 0.13, 0, g);
      const mesh = cyl(0.17, 0.17, 0.08, 20, metal, 0, 0.28, 0, g); for (let i = 0; i < 4; i++) box(0.04, 0.12, 0.04, gold, -0.24 + i * 0.07, -0.08, 0.28, g); },
    bme: (g) => { box(0.42, 0.04, 0.36, purple, 0, 0, 0, g); box(0.08, 0.04, 0.08, metal, 0, 0.04, 0, g); for (let i = 0; i < 4; i++) box(0.03, 0.1, 0.03, gold, -0.1 + i * 0.07, -0.07, 0.15, g); },
  };
  const ringCol = { mq2: 0xb7c0c8, mq7: 0xb7c0c8, mq135: 0xb7c0c8 };
  const groups = PARTS.map((p, i) => {
    const g = new THREE.Group();
    if (p.key === "esp32") make.esp32(g); else if (p.key === "cam") { make.cam(g); g.userData.big = 2.2; } else if (p.key === "pms") make.pms(g); else if (p.key === "bme") { make.bme(g); g.userData.big = 1.9; } else make.mq(g, ringCol[p.key]);
    g.userData = { i, home: new THREE.Vector3(0, 0, 0) };
    scene.add(g); return g;
  });
  // posisi rakitan (kotak node) dan posisi urai
  const assembled = [[0, -0.2, 0], [0.75, 0.0, 0.45], [0.55, 0.2, 0.05], [-0.45, 0.25, 0.25], [-0.45, 0.25, -0.25], [0.05, 0.25, -0.3], [0.1, 0.18, 0.35]];
  const spread = PARTS.map((_, i) => i < 4 ? [(i - 1.5) * 3.15, 1.55, 0] : [(i - 5) * 3.6, -1.15, 0]);
  const shell = box(1.9, 0.9, 1.2, new THREE.MeshStandardMaterial({ color: 0xeaf4fa, transparent: true, opacity: 0.9, roughness: 0.4 }), 0, 0.05, 0, scene);

  const composer = makeComposer(scene, cam, 0.65);
  const labels = $("labels");
  return {
    render(t, o = {}) {
      const k = ease(o.explode ?? 1);
      shell.material.opacity = 0.9 * (1 - clamp(k * 2.5)); shell.visible = shell.material.opacity > 0.01;
      groups.forEach((g, i) => {
        const a = assembled[i], s = spread[i];
        g.position.set(lerp(a[0], s[0], k), lerp(a[1], s[1], k) + Math.sin(t * 1.4 + i) * 0.06 * k, lerp(a[2], s[2], k));
        g.rotation.set(0.35 * k, t * 0.35 + i * 0.6, 0);
        g.scale.setScalar(lerp(0.6, 1.45, k) * (k > 0 ? lerp(1, g.userData.big || 1, k) : 1));
      });
      cam.position.set(Math.sin(t * 0.08) * 1.0, 1.2, 13.2); cam.lookAt(0, -0.1, 0);
      composer.render();
      // label HTML diproyeksikan dari posisi 3D
      labels.innerHTML = "";
      const la = clamp((k - 0.6) / 0.4);
      if (la > 0) groups.forEach((g, i) => {
        const v = g.position.clone().add(new THREE.Vector3(0, -0.55, 0)).project(cam);
        const d = document.createElement("div"); d.className = "lbl";
        const p = PARTS[i]; d.style.left = `${(v.x * 0.5 + 0.5) * W}px`; d.style.top = `${(-v.y * 0.5 + 0.5) * H}px`;
        d.style.opacity = clamp(la * 1.6 - i * 0.12);
        d.innerHTML = `<div class="series">${p.series}</div><div class="role">${p.role}</div><div class="gas">${p.gas}</div>`;
        labels.appendChild(d);
      });
    },
  };
}

// ================================================================ ADEGAN HTML: notifikasi website, SHAP
const UI_CSS = `
.bgfx{position:absolute;inset:0;background:
  radial-gradient(900px 600px at 78% 30%, rgba(43,168,224,.18), transparent 60%),
  radial-gradient(700px 500px at 15% 85%, rgba(255,77,94,.12), transparent 60%), #060D14;}
.gridfx{position:absolute;inset:0;background-image:linear-gradient(rgba(79,227,240,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(79,227,240,.06) 1px,transparent 1px);background-size:64px 64px;}
.browser{position:absolute;left:160px;top:170px;width:1600px;height:760px;border-radius:22px;background:#0B1824;border:1px solid #1C3444;box-shadow:0 40px 120px rgba(0,0,0,.6),0 0 0 1px rgba(79,227,240,.08);overflow:hidden}
.bar{height:58px;background:#0E2131;display:flex;align-items:center;gap:12px;padding:0 22px}
.dot{width:14px;height:14px;border-radius:50%}
.url{margin-left:24px;background:#071420;border-radius:10px;padding:8px 18px;font:500 19px IN;color:#8FB0C2;width:560px}
.dash{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;padding:34px}
.card{background:#0E2131;border-radius:18px;padding:22px 26px;border:1px solid #17324a}
.card .l{font:600 17px IN;letter-spacing:2px;text-transform:uppercase;color:#8FB0C2}
.card .v{font:700 64px SG;margin-top:6px}
.card .s{font:500 18px IN;color:#8FB0C2}
.chart{grid-column:span 3;height:330px;position:relative}
.snap{height:330px;position:relative;overflow:hidden}
.snap img{position:absolute;left:22px;right:22px;top:58px;width:calc(100% - 44px);height:250px;object-fit:cover;border-radius:12px;border:2px solid #FF4D5E}
.evbadge{position:absolute;white-space:nowrap;font:600 24px IN;color:#fff;background:rgba(20,8,10,.85);border:2px solid #FF4D5E;border-radius:12px;padding:10px 18px;box-shadow:0 10px 40px rgba(255,77,94,.4)}
.evbadge b{color:#FF4D5E;margin-right:8px}
.toast{position:absolute;left:200px;width:640px;background:linear-gradient(135deg,#4a121b,#2a0b11);border:2px solid #FF4D5E;border-radius:20px;padding:26px 30px;box-shadow:0 20px 70px rgba(255,77,94,.35)}
.toast h3{margin:0;font:700 36px SG;color:#FF6B79}
.toast p{margin:10px 0 0;font:500 21px/1.4 IN;color:#F7D3D7}
.toast .chips{display:flex;gap:10px;margin-top:16px}
.chip{font:600 17px IN;padding:7px 14px;border-radius:999px;background:rgba(255,77,94,.18);color:#FFC2C8}
.shap{position:absolute;left:160px;top:150px;width:1600px}
.shap h2{font:700 64px SG;margin:0 0 6px;letter-spacing:-1px}
.shap .sub{font:500 26px IN;color:#8FB0C2;margin-bottom:46px}
.row{display:grid;grid-template-columns:420px 1fr 230px;align-items:center;gap:26px;margin:22px 0}
.row .n{font:700 34px SG}.row .n small{display:block;font:500 19px IN;color:#8FB0C2;margin-top:2px}
.track{height:50px;background:#0E2131;border-radius:12px;position:relative;overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;border-radius:12px}
.row .w{font:700 28px SG;text-align:right}
.verdict{margin-top:44px;display:flex;align-items:center;gap:22px;font:600 28px IN;color:#EAF4FA}
.badge{font:700 30px SG;padding:12px 24px;border-radius:14px}
`;
function uiBase() { return `<style>${UI_CSS}</style><div class="bgfx"></div><div class="gridfx"></div>`; }

function renderDash(t, o = {}) {
  const k = clamp(o.smoke ?? 1), al = clamp(o.alert ?? 1);
  const pm = Math.round(lerp(14, 41, k));
  let path = "";
  for (let i = 0; i <= 80; i++) {
    const x = i / 80 * 1532, ramp = clamp((i / 80 - 0.5) / 0.5) * k;
    const y = 250 - Math.sin(i * 0.45) * 10 - ramp * 190;
    path += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
  }
  const ty = lerp(-260, 300, easeOut(al));
  $("ui").innerHTML = uiBase() + `
  <div class="browser">
    <div class="bar"><span class="dot" style="background:#FF5F57"></span><span class="dot" style="background:#FEBC2E"></span><span class="dot" style="background:#28C840"></span>
      <span class="url">airlens · your room · live</span></div>
    <div class="dash">
      <div class="card"><div class="l">PM2.5 · PMS5003</div><div class="v" style="color:${k > 0.5 ? "#F2994A" : "#3DDC97"}">${pm}</div><div class="s">µg/m³</div></div>
      <div class="card"><div class="l">CO · MQ-7</div><div class="v" style="color:${k > 0.4 ? "#FF4D5E" : "#3DDC97"}">${k > 0.4 ? "▲ High" : "Normal"}</div><div class="s">vs 24-h median</div></div>
      <div class="card"><div class="l">Smoke · MQ-2</div><div class="v" style="color:${k > 0.4 ? "#FF4D5E" : "#3DDC97"}">${k > 0.4 ? "▲ High" : "Normal"}</div><div class="s">sudden rise</div></div>
      <div class="card"><div class="l">City · IQAir</div><div class="v">72</div><div class="s">Moderate · 18 km away</div></div>
      <div class="card chart"><div class="l">Last 60 minutes</div>
        <svg width="1060" height="270" viewBox="0 0 1532 270" preserveAspectRatio="none" style="position:absolute;left:34px;bottom:20px"><defs><linearGradient id="gf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#F2994A" stop-opacity=".45"/><stop offset="1" stop-color="#F2994A" stop-opacity="0"/></linearGradient></defs>
          <path d="${path} L1532 270 L0 270Z" fill="url(#gf)"/><path d="${path}" fill="none" stroke="#F2994A" stroke-width="5" stroke-linejoin="round"/></svg></div>
      <div class="card snap" style="opacity:${clamp(((o.snap ?? 1)) * 2)}"><div class="l">Event photo · ESP32-CAM</div><img src="${eventPhoto(true)}"></div>
    </div>
    <div class="toast" style="top:${ty}px;opacity:${clamp(al * 2)}">
      <h3>⚠ Possible local smoke</h3>
      <p>Your room is worse than the city right now. Close the windows and keep sensitive people away from the smoke.</p>
      <div class="chips"><span class="chip">MQ-2 smoke ▲</span><span class="chip">MQ-7 CO ▲</span><span class="chip">PM2.5 ${pm}</span></div>
    </div>
  </div>`;
}

function renderShap(t, o = {}) {
  const k = o.grow ?? 1;
  const rows = [
    ["CO sensor", "MQ-7 · carbon monoxide", 0.92, "#FF4D5E", "High"],
    ["Smoke sensor", "MQ-2 · sudden rise", 0.68, "#FF7A59", "High"],
    ["Sky photo", "CNN · hazy horizon", 0.34, "#F2994A", "Medium"],
    ["Humidity", "BME280 · 82% RH", 0.14, "#F2C94C", "Low"],
    ["City baseline", "IQAir · AQI 72", 0.22, "#4FE3F0", "Starting point"],
  ];
  $("ui").innerHTML = uiBase() + `<div class="shap">
    <h2>Why is your room worse than the city?</h2>
    <div class="sub">Explainable AI (SHAP) shows which sensor pushed the estimate up.</div>
    ${rows.map(([n, s, v, c, w], i) => {
      const g = easeOut((k - i * 0.12) / 0.5);
      return `<div class="row" style="opacity:${clamp(g * 2)}"><div class="n">${n}<small>${s}</small></div>
        <div class="track"><div class="fill" style="width:${v * 100 * g}%;background:linear-gradient(90deg,${c}aa,${c});box-shadow:0 0 26px ${c}77"></div></div>
        <div class="w" style="color:${c}">${w}</div></div>`; }).join("")}
    <div class="verdict" style="opacity:${clamp((k - 0.7) * 3)}">Estimate for your room:
      <span class="badge" style="background:#F2994A;color:#1a0d02">Unhealthy for sensitive groups</span>
      <span style="color:#8FB0C2">· city says Moderate</span></div>
  </div>`;
}


// ================================================================ foto kejadian (gaya CCTV) dan Grad-CAM
const photoCache = {};
function drawStreet(g, w, h, haze) {
  const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#2a3a6b"); gr.addColorStop(0.6, "#c0646a"); gr.addColorStop(1, "#f4a46a");
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
  const r = rng(11); g.fillStyle = "#1a1626";
  for (let x = -20; x < w; x += 50 + r() * 60) { const bh = h * (0.25 + r() * 0.35); g.fillRect(x, h - bh, 40 + r() * 50, bh); }
  g.fillStyle = "#2b2b33"; g.fillRect(0, h * 0.86, w, h * 0.14);
  if (haze > 0) {
    for (let i = 0; i < 14; i++) {
      const x = w * (0.15 + r() * 0.8), y = h * (0.2 + r() * 0.6), rad = w * (0.12 + r() * 0.2);
      const c = g.createRadialGradient(x, y, 0, x, y, rad); c.addColorStop(0, `rgba(190,190,198,${0.3 * haze})`); c.addColorStop(1, "rgba(200,200,205,0)");
      g.fillStyle = c; g.fillRect(0, 0, w, h);
    }
  }
}
function eventPhoto(smoky) {
  const key = smoky ? "s" : "c"; if (photoCache[key]) return photoCache[key];
  const c = document.createElement("canvas"); c.width = 640; c.height = 400; const g = c.getContext("2d");
  drawStreet(g, 640, 400, smoky ? 1 : 0);
  g.fillStyle = "rgba(0,0,0,.55)"; g.fillRect(0, 0, 640, 34);
  g.fillStyle = "#fff"; g.font = "600 17px IN"; g.fillText(`NODE-01 · 17:42:08 · EVENT: ${smoky ? "SMOKE" : "GAS (MQ-7)"}`, 12, 23);
  g.fillStyle = "#FF4D5E"; g.beginPath(); g.arc(622, 17, 7, 0, 7); g.fill();
  return (photoCache[key] = c.toDataURL("image/jpeg", 0.9));
}
function gradcamPhoto(a) {
  const c = document.createElement("canvas"); c.width = 640; c.height = 400; const g = c.getContext("2d");
  drawStreet(g, 640, 400, 1);
  g.globalAlpha = a;
  const blobs = [[330, 150, 190, 1], [470, 210, 140, 0.8], [190, 230, 120, 0.55]];
  for (const [x, y, rad, k] of blobs) {
    const gr = g.createRadialGradient(x, y, 0, x, y, rad);
    gr.addColorStop(0, `rgba(255,40,40,${0.85 * k})`); gr.addColorStop(0.35, `rgba(255,200,0,${0.65 * k})`);
    gr.addColorStop(0.7, `rgba(0,160,255,${0.35 * k})`); gr.addColorStop(1, "rgba(0,80,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 640, 400);
  }
  return c.toDataURL("image/jpeg", 0.88);
}

const UI2_CSS = `
.top{position:absolute;left:110px;top:150px;max-width:1700px}
.top .kicker{font:600 26px IN;letter-spacing:6px;text-transform:uppercase;color:#4FE3F0;margin-bottom:14px}
.top h1{margin:0;font:700 72px/1.05 SG;letter-spacing:-1px}.top h1 b{color:#4FE3F0}.top h1 em{font-style:normal;color:#F2994A}
.pane{position:absolute;background:#0E2131;border:1px solid #17324a;border-radius:22px;padding:24px 28px;box-shadow:0 30px 90px rgba(0,0,0,.5)}
.pane .l{font:600 18px IN;letter-spacing:2.5px;text-transform:uppercase;color:#8FB0C2;margin-bottom:14px}
.pane img{width:100%;border-radius:14px;display:block}
.cap{font:600 24px IN;margin-top:14px}
.gauge{height:44px;background:#071420;border-radius:12px;overflow:hidden;margin:10px 0 18px}
.gauge div{height:100%;border-radius:12px}
.gl{display:flex;justify-content:space-between;font:700 30px SG}.gl small{font:500 20px IN;color:#8FB0C2}
.flow path{fill:none;stroke-width:6;stroke-linecap:round}
.core{position:absolute;border-radius:50%;display:grid;place-items:center;text-align:center;font:700 34px/1.15 SG}
.ring text{font:700 30px SG;fill:#EAF4FA}.ring .s{font:500 19px IN;fill:#8FB0C2}
.ph{position:absolute;left:330px;top:300px;width:1260px;height:640px;border-radius:26px;border:3px dashed #2BA8E0;display:grid;place-items:center;text-align:center;background:rgba(43,168,224,.06)}
`;

function renderGas(t, o = {}) {
  const k = easeOut(o.gas ?? 1), al = clamp(o.alert ?? 1);
  const ty = lerp(40, 0, easeOut(al));
  $("ui").innerHTML = uiBase() + `<style>${UI2_CSS}</style>
  <div class="top"><div class="kicker">No smoke? Still dangerous.</div><h1>The camera can't see CO.<br><b>The sensor can.</b></h1></div>
  <div class="pane" style="left:110px;top:430px;width:780px">
    <div class="l">Event photo · ESP32-CAM</div><img src="${eventPhoto(false)}"><div class="cap" style="color:#3DDC97">Nothing visible in the photo</div></div>
  <div class="pane" style="left:960px;top:430px;width:850px">
    <div class="l">Gas sensors · live</div>
    <div class="gl">MQ-7 · CO <small>${k > 0.5 ? "rising fast" : "normal"}</small></div><div class="gauge"><div style="width:${lerp(12, 92, k)}%;background:linear-gradient(90deg,#F2994A,#FF4D5E);box-shadow:0 0 24px #FF4D5E88"></div></div>
    <div class="gl">MQ-2 · smoke <small>normal</small></div><div class="gauge"><div style="width:16%;background:#3DDC97"></div></div>
    <div class="gl">PM2.5 · particles <small>normal</small></div><div class="gauge"><div style="width:20%;background:#3DDC97"></div></div>
    <div class="toast" style="position:relative;left:0;width:auto;margin-top:8px;opacity:${clamp(al * 2)};transform:translateY(${ty}px)">
      <h3>⚠ Invisible gas — likely CO</h3><p>Check stoves, generators or engines nearby. Open windows and ventilate now.</p></div>
  </div>`;
}

function renderFusion(t, o = {}) {
  const k = o.flow ?? 1, cam = clamp(o.cam ?? 1);
  const dash = (i) => `stroke-dasharray:24 18;stroke-dashoffset:${-t * 120 - i * 40}`;
  const inA = (i) => clamp((k - i * 0.15) * 3);
  $("ui").innerHTML = uiBase() + `<style>${UI2_CSS}</style>
  <div class="top" style="top:120px"><div class="kicker">Explainable fusion</div><h1>Sensors + event photo + city baseline</h1></div>
  <svg class="flow" width="1920" height="1080" style="position:absolute;inset:0">
    <path d="M620 400 C 900 400, 1000 600, 1250 620" stroke="#FF7A59" style="${dash(0)};opacity:${inA(0)}"/>
    <path d="M620 650 C 900 650, 1000 640, 1250 640" stroke="#F2994A" style="${dash(1)};opacity:${inA(1)}"/>
    <path d="M620 900 C 900 900, 1000 680, 1250 660" stroke="#4FE3F0" style="${dash(2)};opacity:${inA(2)}"/>
  </svg>
  <div class="pane" style="left:110px;top:315px;width:510px;padding:18px 24px;opacity:${inA(0)}"><div class="l" style="margin:0">Sensors</div><div class="gl" style="font-size:26px;margin-top:6px">MQ-7 ▲ · MQ-2 ▲ · PM2.5 41</div></div>
  <div class="pane" style="left:110px;top:470px;width:510px;padding:18px 24px;opacity:${inA(1)}"><div class="l">Event photo → Grad-CAM</div><img src="${gradcamPhoto(cam)}" style="height:230px;object-fit:cover"></div>
  <div class="pane" style="left:110px;top:840px;width:510px;padding:18px 24px;opacity:${inA(2)}"><div class="l" style="margin:0">City baseline · IQAir</div><div class="gl" style="font-size:26px;margin-top:6px">AQI 72 · Moderate</div></div>
  <div class="core" style="left:1250px;top:470px;width:340px;height:340px;background:radial-gradient(circle,#123a52,#0a1d2b 70%);border:3px solid #4FE3F0;box-shadow:0 0 ${40 + 20 * Math.sin(t * 4)}px #4FE3F0aa,inset 0 0 60px #4FE3F044">
    <div>Fusion<br>model<div style="font:500 20px IN;color:#8FB0C2;margin-top:8px">+ SHAP</div></div></div>
  <div style="position:absolute;left:1240px;top:850px;width:360px;text-align:center;opacity:${clamp((k - 0.6) * 3)}">
    <span class="badge" style="background:#F2994A;color:#1a0d02;font:700 26px SG;padding:10px 18px;border-radius:12px;display:inline-block">Unhealthy for sensitive groups</span></div>
  <div style="position:absolute;left:110px;top:965px;font:500 20px IN;color:#8FB0C2;opacity:${cam}">Grad-CAM: where the photo model looked (red = most influence)</div>`;
}

function renderSite(t, o = {}) {
  $("ui").innerHTML = uiBase() + `<style>${UI2_CSS}</style>
  <div class="top" style="top:130px"><div class="kicker">Live at our booth</div><h1>Try it yourself.</h1></div>
  <div class="ph"><div><div style="font:700 44px SG;color:#2BA8E0">[ Website screen recording ]</div>
  <div style="font:500 24px IN;color:#8FB0C2;margin-top:12px">placeholder — replaced with a recording from the lab</div></div></div>`;
}

function renderLoop(t, o = {}) {
  const steps = [["Data", "sensors · photos"], ["Train", "MLflow tracking"], ["Shadow", "challenger vs prod"], ["Promote", "beat IQAir baseline"], ["Monitor", "drift · sensor health"]];
  const cx = 1180, cy = 600, R = 300, a0 = -Math.PI / 2, act = Math.floor((t * 1.4) % 5), dotA = a0 + (t * 1.4 % 5) / 5 * Math.PI * 2;
  const nodes = steps.map(([n, s], i) => {
    const a = a0 + i / 5 * Math.PI * 2, x = cx + R * Math.cos(a), y = cy + R * Math.sin(a), on = i === act;
    return `<circle cx="${x}" cy="${y}" r="${on ? 34 : 24}" fill="${on ? "#4FE3F0" : "#0E2131"}" stroke="#4FE3F0" stroke-width="4" style="filter:${on ? "drop-shadow(0 0 18px #4FE3F0)" : "none"}"/>
      <text x="${x + (Math.cos(a) >= -0.1 ? 52 : -52)}" y="${y + 6}" text-anchor="${Math.cos(a) >= -0.1 ? "start" : "end"}">${n}</text>
      <text class="s" x="${x + (Math.cos(a) >= -0.1 ? 52 : -52)}" y="${y + 34}" text-anchor="${Math.cos(a) >= -0.1 ? "start" : "end"}">${s}</text>`;
  }).join("");
  $("ui").innerHTML = uiBase() + `<style>${UI2_CSS}</style>
  <div class="top" style="top:140px;max-width:640px"><div class="kicker">MLOps</div><h1>Monitored, retrained, <b>always improving.</b></h1></div>
  <svg class="ring" width="1920" height="1080" style="position:absolute;inset:0">
    <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#1C3444" stroke-width="6"/>
    <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#2BA8E0" stroke-width="6" stroke-dasharray="40 30" style="stroke-dashoffset:${-t * 80}"/>
    <circle cx="${cx + R * Math.cos(dotA)}" cy="${cy + R * Math.sin(dotA)}" r="12" fill="#F2994A" style="filter:drop-shadow(0 0 14px #F2994A)"/>
    ${nodes}
    <text x="${cx}" y="${cy - 8}" text-anchor="middle" style="font:700 40px SG">AirLens</text>
    <text class="s" x="${cx}" y="${cy + 30}" text-anchor="middle">docker compose · MLflow · rollback</text>
  </svg>`;
}

function renderEnd(t, o = {}) {
  const a = easeOut(t / 1.2);
  $("ui").innerHTML = uiBase() + `<style>${UI2_CSS}</style>
  <div style="position:absolute;left:0;right:0;top:250px;text-align:center;opacity:${a};transform:scale(${lerp(0.92, 1, a)})">
    <img src="/assets/airlens_logo_dark.svg" style="height:200px">
    <div style="font:700 78px SG;margin-top:40px">Try it at our booth.</div>
    <div style="font:500 28px IN;color:#8FB0C2;margin-top:14px">Sensors + camera + explainable AI · MLOps course project</div>
  </div>
  <div style="position:absolute;right:120px;bottom:120px;width:230px;height:230px;border-radius:20px;border:3px dashed #4FE3F0;display:grid;place-items:center;text-align:center;font:600 22px IN;color:#8FB0C2;opacity:${clamp(t - 1)}">QR code<br>(website link)</div>`;
}

// ================================================================ ADEGAN: KOTA (jarak stasiun vs node)
function buildCity() {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x070f17); scene.fog = new THREE.Fog(0x070f17, 40, 130);
  const cam = new THREE.PerspectiveCamera(40, W / H, 0.1, 200);
  scene.add(new THREE.HemisphereLight(0x8fa8ff, 0x1a1420, 1.8));
  const sun = new THREE.DirectionalLight(0xff9a62, 1.6); sun.position.set(-20, 18, -30); scene.add(sun);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), flat(0x0d1821)); ground.rotation.x = -Math.PI / 2; scene.add(ground);
  const grid = new THREE.GridHelper(200, 100, 0x12324a, 0x0f2433); grid.position.y = 0.01; scene.add(grid);
  const r = rng(5), bmat = [flat(0x1b2c3c), flat(0x22374a), flat(0x16232f)];
  const win = new THREE.MeshBasicMaterial({ color: 0xffc46b });
  for (let x = -40; x <= 40; x += 4) for (let z = -50; z <= 12; z += 4) {
    if (Math.abs(x) < 2 && z > -2) continue; if (r() < 0.25) continue;
    const h = 0.8 + Math.pow(r(), 2.2) * 9, b = box(2.6, h, 2.6, bmat[Math.floor(r() * 3)], x + (r() - 0.5), h / 2, z + (r() - 0.5), scene);
    if (r() < 0.5) box(2.62, 0.15, 0.1, win, b.position.x, h * (0.3 + r() * 0.5), b.position.z + 1.31, scene);
  }
  // rumah Pak Dengklek + penanda
  const house = new THREE.Group(); house.position.set(0, 0, 4); scene.add(house);
  box(2.2, 1.6, 2.2, flat(0xeaf4fa), 0, 0.8, 0, house);
  const roof = new THREE.Mesh(new THREE.ConeGeometry(1.9, 1.1, 4), flat(0xf2994a)); roof.position.y = 2.15; roof.rotation.y = Math.PI / 4; house.add(roof);
  const beaconH = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 6, 8), new THREE.MeshBasicMaterial({ color: 0xf2994a, transparent: true, opacity: 0.8 })); beaconH.position.set(0, 5.5, 4); scene.add(beaconH);
  // stasiun IQAir jauh
  const st = new THREE.Group(); st.position.set(-18, 0, -30); scene.add(st);
  box(0.6, 7, 0.6, flat(0x9fb3c2), 0, 3.5, 0, st);
  const beaconS = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 14, 8), new THREE.MeshBasicMaterial({ color: 0x4fe3f0, transparent: true, opacity: 0.9, fog: false })); beaconS.position.set(-18, 9, -30); scene.add(beaconS);
  // garis jarak
  const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, 8, 4), new THREE.Vector3(-9, 14, -13), new THREE.Vector3(-18, 15, -30));
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(80)), new THREE.LineDashedMaterial({ color: 0xeaf4fa, dashSize: 0.8, gapSize: 0.6 }));
  line.computeLineDistances(); scene.add(line);
  const composer = makeComposer(scene, cam, 0.9);
  return {
    render(t, o = {}) {
      const k = ease(o.pull ?? 1);
      cam.position.set(lerp(3, 16, k), lerp(3.5, 26, k), lerp(10, 30, k)); cam.lookAt(lerp(0, -8, k), lerp(1.5, 4, k), lerp(4, -12, k));
      line.material.opacity = 1; line.visible = k > 0.35;
      composer.render();
      const lab = (p, html, col) => { const v = p.clone().project(cam); if (v.z > 1) return; const d = document.createElement("div"); d.className = "evbadge";
        d.style.borderColor = col; d.style.left = `${(v.x * 0.5 + 0.5) * W}px`; d.style.top = `${(-v.y * 0.5 + 0.5) * H}px`; d.style.opacity = clamp((k - 0.45) * 3); d.style.transform = "translate(-50%,-110%)"; d.innerHTML = html; $("labels").appendChild(d); };
      lab(new THREE.Vector3(0, 8.6, 4), `<b style="color:#F2994A">●</b> AirLens node · 2 m from Pak Dengklek`, "#F2994A");
      lab(new THREE.Vector3(-18, 16.2, -30), `<b style="color:#4FE3F0">●</b> City station (IQAir) · 18 km`, "#4FE3F0");
    },
  };
}

// ================================================================ API untuk perekam
let room, node, city;
const headline = (kicker, html, a = 1) => {
  $("headline").innerHTML = html ? `<div class="kicker">${kicker}</div><h1>${html}</h1>` : "";
  $("headline").style.opacity = a; $("headline").style.transform = `translateY(${(1 - a) * 30}px)`;
};
window.show = async (name, t, o = {}) => {
  $("ui").innerHTML = ""; $("labels").innerHTML = "";
  const is3d = ["room", "node", "city"].includes(name);
  canvas.style.visibility = is3d ? "visible" : "hidden";
  $("progress").style.width = `${(o.progress ?? 0) * 100}%`;
  if (name === "room") { room ??= buildRoom(); room.render(t, o); }
  if (name === "node") { node ??= buildNode(); node.render(t, o); }
  if (name === "city") { city ??= buildCity(); city.render(t, o); }
  if (name === "dash") renderDash(t, o);
  if (name === "gas") renderGas(t, o);
  if (name === "fusion") renderFusion(t, o);
  if (name === "shap") renderShap(t, o);
  if (name === "site") renderSite(t, o);
  if (name === "loop") renderLoop(t, o);
  if (name === "end") renderEnd(t, o);
  headline(o.kicker ?? "", o.text ?? "", o.textA ?? 1);
  $("headline").style.bottom = (o.textBottom ?? 150) + "px";
  $("fade").style.opacity = o.fade ?? 0;
  // tunggu gambar data-URL selesai di-decode agar tidak ada frame kosong
  await Promise.all([...document.images].map((im) => im.decode().catch(() => {})));
};
await document.fonts.ready;
window.ready = true;
