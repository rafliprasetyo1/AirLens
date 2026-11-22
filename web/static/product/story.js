// Halaman Product: gulir -> keadaan adegan 3D. Tiap <section data-scene> punya keadaan dasar; progres di dalam bagian
// (0..1) menggerakkan tutup, langkah sensor, dan ledakan rakitan. Label 3D dipasang ulang tiap frame.
const body = document.body;
const reducedQuery = matchMedia("(prefers-reduced-motion: reduce)");
const narrowQuery = matchMedia("(max-width: 899px), (orientation: portrait)");
const span = (p, a, b) => Math.min(1, Math.max(0, (p - a) / (b - a)));

const BASE = { az: 32, el: 22, dist: 420, tx: -6, ty: 14, tz: 0, lid: 0, lidFade: 1, wires: 1, explode: 0, esp: 0, mq: [0, 0, 0, 0],
  pulse: 0, power: 1, spin: 0 };
const SCENES = {
  hero: (p) => ({ spin: 1 }),
  open: (p) => ({ az: 22, el: 46, dist: 330, tx: -2, ty: 8, tz: 3, lid: span(p, 0.05, 0.5), lidFade: 1 - span(p, 0.3, 0.65) }),
  esp32: () => ({ az: -30, el: 40, dist: 150, tx: -29, ty: 33, tz: 1, lid: 1, lidFade: 0, wires: 0, esp: 1 }),
  sensors: (p) => {
    const k = Math.min(3, Math.floor(p * 4)), mq = [0, 0, 0, 0];
    mq[k] = 1;
    return { az: 62, el: 32, dist: 190, tx: 50, ty: 26, tz: [39, 13, -13, -39][k] * 0.55, lid: 1, lidFade: 0, wires: 0, mq, step: k };
  },
  divider: () => ({ az: 18, el: 54, dist: 118, tx: 9, ty: 11, tz: -8, lid: 1, lidFade: 0, wires: 0 }),
  explode: (p) => ({ az: 34, el: 18, dist: 480, tx: 0, ty: 34, tz: 0, lid: 0, lidFade: 1, wires: 0, explode: span(p, 0.05, 0.55) }),
  flow: () => ({ az: 38, el: 50, dist: 330, tx: 2, ty: 10, tz: 0, lid: 1, lidFade: 0, pulse: 1 }),
  end: () => ({ spin: 1 }),
};
// label per bagian: [nama titik, judul, keterangan, arah garis penunjuk (derajat, 0 = kanan, 90 = atas), panjang px]
const LABELS = {
  esp32: [["wroom", "ESP-WROOM-32", "Wi-Fi and the dual-core CPU", 30, 70], ["usb", "Micro-USB", "5 V power in", 205, 70],
    ["buttons", "EN and BOOT", "reset and flash mode", 145, 80], ["gpio", "GPIO 34, 35, 32, 33", "the four sensor inputs", 95, 90]],
  divider: [["r10", "10 kΩ", "brown, black, orange", 20, 70], ["r20", "20 kΩ", "red, black, orange", 160, 70]],
  explode: [["lid", "Clip-on lid", "", 30, 40], ["esp", "ESP32 DevKit V1", "", 150, 50], ["mq0", "4 MQ sensor boards", "", 25, 60],
    ["breadboard", "Half-size breadboard", "", 195, 60], ["base", "Printed tray", "", 205, 60]],
};
const MQ_LABELS = [["mq0", "MQ-2", "smoke and flammable gas", 40, 80], ["mq1", "MQ-3", "alcohol vapour", 40, 80],
  ["mq2", "MQ-7", "carbon monoxide hint", 40, 80], ["mq3", "MQ-135", "air quality and VOCs", 40, 80]];

function webglOK() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
}

async function start() {
  if (!webglOK()) { body.classList.add("no-3d"); return; }
  const canvas = document.getElementById("stage-canvas");
  const loader = document.getElementById("loader"), bar = document.getElementById("loader-bar"), loaderText = document.getElementById("loader-text");
  const weak = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  let stage;
  try {
    const { createScene } = await import("./beta-scene.js");
    stage = createScene(canvas, { weak, onProgress: (f) => { bar.style.width = `${Math.round(f * 100)}%`; } });
    stage.setReduced(reducedQuery.matches);
    reducedQuery.addEventListener("change", (e) => stage.setReduced(e.matches));
    stage.resize();
    await stage.load("/product/models/");
    loader.classList.add("done");
    window.__airlensStage = stage;   // untuk uji otomatis (tests/ui)
  } catch (err) {
    console.error(err);
    loaderText.textContent = "The 3D model could not load. The text below still describes every part.";
    return;
  }

  // ---------------------------------------------------------------- label
  const layer = document.getElementById("callouts"), els = new Map();
  function callout(name, title, sub, ang = 35, len = 50) {
    const key = `${name}|${title}`;
    if (!els.has(key)) {
      const d = document.createElement("div");
      d.className = "callout";
      d.innerHTML = `<span class="lead"></span><span class="txt"></span>`;
      const lead = d.querySelector(".lead"), txt = d.querySelector(".txt");
      txt.textContent = title;
      if (sub) { const s = document.createElement("small"); s.textContent = sub; txt.append(s); }
      const a = (ang * Math.PI) / 180, ex = Math.cos(a) * len, ey = -Math.sin(a) * len;
      lead.style.width = `${len}px`;
      lead.style.transform = `rotate(${-ang}deg)`;
      txt.style.left = `${ex}px`; txt.style.top = `${ey}px`;
      const right = Math.cos(a) >= -0.2;
      txt.style.transform = `translate(${right ? "6px" : "calc(-100% - 6px)"}, ${Math.sin(a) > 0.3 ? "-100%" : Math.sin(a) < -0.3 ? "0" : "-50%"})`;
      txt.style.textAlign = right ? "left" : "right";
      layer.append(d);
      els.set(key, { el: d, name });
    }
    return key;
  }
  let shown = new Set();
  stage.onFrame = () => {
    for (const [key, { el, name }] of els) {
      if (!shown.has(key)) { el.classList.remove("on"); continue; }
      const p = stage.project(name);
      if (!p) { el.classList.remove("on"); continue; }
      el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`;
      el.classList.add("on");
      // jaga teks tetap di dalam layar (HP): geser teksnya saja, titik dan garis tetap di tempat
      const txt = el.firstElementChild.nextElementSibling, r = txt.getBoundingClientRect();
      const off = Number(txt.dataset.off || 0);
      const delta = Math.max(0, 6 - r.left) - Math.max(0, r.right - (innerWidth - 6));
      if (Math.abs(delta) > 0.5) { txt.dataset.off = String(off + delta); txt.style.marginLeft = `${off + delta}px`; }
    }
  };

  // ---------------------------------------------------------------- gulir
  const sections = [...document.querySelectorAll("[data-scene]")];
  const sensorItems = [...document.querySelectorAll("#sensor-list li")];
  let queued = false;
  function update() {
    queued = false;
    const ref = innerHeight * (narrowQuery.matches ? 0.8 : 0.5);
    let sec = sections[0], p = 0;
    for (const s of sections) {
      const r = s.getBoundingClientRect();
      if (r.top <= ref) { sec = s; p = Math.min(1, (ref - r.top) / r.height); }
    }
    const name = sec.dataset.scene;
    const st = { ...BASE, mq: [0, 0, 0, 0], ...SCENES[name](p) };
    const aspect = canvas.clientWidth / Math.max(1, canvas.clientHeight);
    if (aspect < 1.25) st.dist *= Math.min(1.9, 1.25 / Math.max(aspect, 0.5));
    stage.setTarget(st);
    const labels = name === "sensors" ? [MQ_LABELS[st.step]] : (LABELS[name] || []);
    shown = new Set(labels.map(([n, t, s, ang, len]) => callout(n, t, s, ang, len)));
    sensorItems.forEach((li, i) => li.setAttribute("aria-current", String(name === "sensors" && i === st.step)));
    stage.kick();
  }
  const queue = () => { if (!queued) { queued = true; requestAnimationFrame(update); } };
  addEventListener("scroll", queue, { passive: true });
  addEventListener("resize", () => { stage.resize(); queue(); });
  update();
}

start();
