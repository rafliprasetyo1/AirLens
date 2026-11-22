// AirLens Node: menghubungkan gulir ke adegan 3D.
// Setiap bagian <section data-scene> memberi progres 0..1. Dari (indeks bagian, progres) dihitung satu keadaan
// target; keadaan yang tampil mengejar target dengan lerp per frame. Karena target murni fungsi dari posisi gulir,
// menggulir mundur memutar balik animasi.
import { SHELL, MODULES, EXPLODE, SPOTLIGHTS, VOLUMES, AIRFLOW, LABELS } from "./parts.js";

const root = document.documentElement;
const canvas = document.getElementById("stage-canvas");
const labelLayer = document.getElementById("callouts");
const stageTag = document.getElementById("stage-tag");
const loader = document.getElementById("loader");
const loaderText = document.getElementById("loader-text");
const loaderBar = document.getElementById("loader-bar");
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };
const span = (p, a, b) => smooth((p - a) / (b - a));
const mix = (a, b, k) => a + (b - a) * k;
const MB = (b) => (b / 1048576).toFixed(1);

// ------------------------------------------------------------------ tombol Beta Wrapped / Unwrapped
// Berlaku juga tanpa WebGL (menukar gambar diam). Dengan 3D, pilihan tombol menimpa progres gulir sampai
// pengunjung keluar dari bagian Beta.
const betaButtons = { wrapped: document.getElementById("beta-wrapped"), unwrapped: document.getElementById("beta-unwrapped") };
const betaFigure = document.getElementById("beta-figure");
let betaOverride = null;   // null = ikut gulir; 0 = Wrapped; 1 = Unwrapped
function showBetaState(open) {
  betaButtons.wrapped?.setAttribute("aria-pressed", String(!open));
  betaButtons.unwrapped?.setAttribute("aria-pressed", String(open));
  if (betaFigure) betaFigure.dataset.open = String(open);
}
let onBetaChange = () => {};
for (const [name, btn] of Object.entries(betaButtons)) {
  btn?.addEventListener("click", () => {
    betaOverride = name === "unwrapped" ? 1 : 0;
    showBetaState(betaOverride === 1);
    onBetaChange();
  });
}
showBetaState(false);

function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}
function noThreeD(reason) {
  root.classList.remove("has-3d");
  root.classList.add("no-3d");
  if (reason) console.info(`AirLens: 3D view off (${reason}); showing the text version.`);
}

async function start() {
  if (!canvas || !hasWebGL()) return noThreeD("WebGL not available");
  root.classList.add("has-3d");

  const weak = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4
    || (window.matchMedia("(pointer: coarse)").matches && window.innerWidth < 900);

  let stage;
  try {
    const { createScene } = await import("./scene.js");
    stage = createScene(canvas, {
      weak, labelLayer,
      onProgress(got, total) {
        if (!total) return;
        const pct = Math.round((got / total) * 100);
        loaderBar.style.width = `${pct}%`;
        loader.setAttribute("aria-valuenow", String(pct));
        loaderText.textContent = `Loading 3D model, ${MB(got)} of ${MB(total)} MB`;
      },
    });
  } catch (err) {
    return noThreeD(err.message);
  }

  const sections = [...document.querySelectorAll("[data-scene]")];
  stage.loadModels("product/models/").then(() => {
    loader.classList.add("done");
    loaderText.textContent = "3D model ready";
    root.classList.add("model-ready");
    kick();
  }).catch((err) => {
    console.error("AirLens: model failed to load", err);
    loader.classList.add("failed");
    loaderText.textContent = "The 3D model couldn't load. Everything on this page is also in the text.";
  });

  // ------------------------------------------------------------------ target per bagian
  const explodeKeys = Object.keys(EXPLODE);
  function blank() {
    const explode = {}, fade = {}, spot = {}, labels = {}, volumes = {}, flows = {};
    for (const k of explodeKeys) explode[k] = 0;
    for (const k of [...SHELL, ...MODULES]) fade[k] = 1;
    for (const k of MODULES) spot[k] = 0;
    for (const k of Object.keys(LABELS)) labels[k] = 0;
    for (const k of Object.keys(VOLUMES)) volumes[k] = 0;
    for (const k of Object.keys(AIRFLOW)) flows[k] = 0;
    return { az: 30, el: 10, dist: 640, target: [0, 102, 0], explode, shutter: 0, fade, spot, labels, volumes, flows,
      wires: 1, swap: 0, betaOpen: 0 };
  }

  function targetFor(i, p, t) {
    const s = blank();
    const scene = sections[i]?.dataset.scene || "hero";
    const fullExplode = () => { for (const k of explodeKeys) s.explode[k] = 1; };
    switch (scene) {
      case "hero":
        s.az = 30 + t * 9;
        break;
      case "design":     // kamera mengitari; penutup lensa menutup lalu membuka lagi
        s.az = mix(-60, 60, smooth(p)); s.el = 12; s.dist = 600; s.target = [0, 112, 0];
        s.shutter = span(p, 0.25, 0.45) * (1 - span(p, 0.6, 0.8));
        break;
      case "senses":     // kantong kamera, lalu zona sensor
        s.az = 25; s.el = 12;
        s.volumes.cameraPocket = span(p, 0.05, 0.18) * (1 - span(p, 0.42, 0.5));
        s.volumes.sensorZone = span(p, 0.5, 0.62);
        break;
      case "explode": {
        for (const [k, ex] of Object.entries(EXPLODE)) s.explode[k] = span(p, ex.from, ex.to);
        const k = span(p, 0, 0.6);
        s.az = 35; s.el = 14; s.dist = mix(640, 1100, k); s.target = [0, mix(102, 175, k), 0];
        break;
      }
      case "spot": {     // modul ditarik ke depan kamera; casing 10%, modul lain 25%
        const n = Number(sections[i].dataset.spot), sp = SPOTLIGHTS[n];
        fullExplode();
        for (const k of SHELL) s.fade[k] = sp.keep?.includes(k) ? 0.55 : 0.1;
        for (const k of MODULES) s.fade[k] = sp.keys.includes(k) ? 1 : 0.25;
        if (sp.keep?.includes("enclosure_sleeve")) s.explode.enclosure_sleeve = 0;   // corong SEN66 di tempatnya
        if (sp.keep?.includes("enclosure_shutter")) s.fade.enclosure_shutter = 1;
        for (const k of sp.keys) s.spot[k] = span(p, 0.02, 0.3);
        s.labels[sp.id] = span(p, 0.22, 0.36);
        s.az = sp.az + (p - 0.5) * 10; s.el = sp.el; s.dist = sp.dist;
        s.target = stage.spotTarget(n);
        break;
      }
      case "zones":      // sekat ganda: zona bawah biru, zona atas oranye tipis
        s.fade.enclosure_sleeve = 0.22; s.fade.enclosure_cap = 0.5;
        s.volumes.coolZone = span(p, 0.05, 0.25);
        s.volumes.divider = span(p, 0.2, 0.4);
        s.volumes.warmZone = span(p, 0.35, 0.55);
        s.az = 40; s.el = 12; s.dist = 660;
        break;
      case "airflow":
        s.fade.enclosure_sleeve = 0.22; s.fade.enclosure_cap = 0.45;
        s.flows.sensor = span(p, 0.05, 0.3);
        s.flows.pi = span(p, 0.3, 0.55);
        s.az = 55; s.el = 14; s.dist = 720; s.target = [0, 115, 0];
        break;
      case "triggers":
        s.az = -25; s.el = 10; s.dist = 660;
        break;
      case "xai":
        s.az = -45; s.el = 12; s.dist = 660;
        break;
      case "beta": {     // model berganti ke Beta; gulir membuka tutup bertahap, tombol bisa menimpa
        s.swap = span(p, 0, 0.12);
        const open = betaOverride ?? span(p, 0.35, 0.65);
        s.betaOpen = open;
        s.labels.beta = (open > 0.5 ? 1 : 0) * s.swap;
        s.az = 30; s.el = 28; s.dist = 420; s.target = [0, 22, 0];
        break;
      }
      case "end":
        s.az = 30 + t * 9;
        break;
    }
    // Layar tegak: lebar pandang sempit. Sorotan dan kotak Beta (lebar 128 mm) butuh lebih jauh lagi.
    if (stage.layout === "narrow") s.dist *= scene === "spot" ? 1.8 : scene === "beta" ? 2.2 : 1.65;
    return s;
  }

  // ------------------------------------------------------------------ posisi gulir
  function scrollPosition() {
    const mid = window.innerHeight * 0.5;
    for (let i = 0; i < sections.length; i++) {
      const r = sections[i].getBoundingClientRect();
      if (r.top <= mid && r.bottom > mid) return { i, p: clamp01((mid - r.top) / r.height) };
    }
    const first = sections[0].getBoundingClientRect();
    return first.top > mid ? { i: 0, p: 0 } : { i: sections.length - 1, p: 1 };
  }

  // ------------------------------------------------------------------ lerp per frame
  const shortest = (from, to) => from + ((((to - from) % 360) + 540) % 360) - 180;
  let cur = null, last = performance.now(), clock = 0, raf = 0, lastScene = "";
  const live = (scene) => ["hero", "end", "airflow", "spot"].includes(scene);
  const maps = ["explode", "fade", "spot", "labels", "volumes", "flows"];

  function step(now) {
    raf = 0;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const still = reduce.matches;
    if (!still) clock += dt;

    const pos = scrollPosition();
    const scene = sections[pos.i].dataset.scene;
    if (scene !== lastScene) {
      if (lastScene === "beta") betaOverride = null;      // pilihan tombol berlaku selama di bagian Beta
      stageTag.textContent = scene === "beta" ? "Running at this booth" : "Full version · concept design";
      lastScene = scene;
    }
    // Gerak dikurangi: tiap bagian langsung menampilkan keadaan akhirnya, tanpa putaran dan tanpa lerp.
    const tgt = targetFor(pos.i, still ? 1 : pos.p, still ? 0 : clock);
    if (scene === "beta") showBetaState(tgt.betaOpen >= 0.5);
    const k = still || !cur ? 1 : 1 - Math.exp(-dt / 0.12);
    if (!cur) cur = structuredClone(tgt);

    let moving = 0;
    const ease = (a, b) => { const v = a + (b - a) * k; moving = Math.max(moving, Math.abs(b - v)); return v; };
    cur.az = ease(cur.az, shortest(cur.az, tgt.az));
    cur.el = ease(cur.el, tgt.el);
    cur.dist = ease(cur.dist, tgt.dist);
    cur.target = cur.target.map((v, j) => ease(v, tgt.target[j]));
    for (const m of maps) for (const key in tgt[m]) cur[m][key] = ease(cur[m][key], tgt[m][key]);
    for (const key of ["shutter", "wires", "swap", "betaOpen"]) cur[key] = ease(cur[key], tgt[key]);
    cur.time = clock;
    // Batas label penunjuk: jangan masuk kolom teks (lebar) atau panel teks di bawah model (ponsel tegak).
    const copy = sections[pos.i].querySelector(".copy")?.getBoundingClientRect();
    cur.textRight = copy && stage.layout === "wide" ? copy.right : 0;
    cur.textTop = copy && stage.layout === "narrow" ? copy.top : Infinity;

    stage.apply(cur);
    measureFps(dt);

    if (!document.hidden && (moving > 0.001 || (!still && live(scene)))) kick();
    else idle = true;
  }
  // Setelah diam, frame pertama tidak boleh menghitung jeda panjang sebagai dt (merusak lerp dan ukuran fps).
  let idle = true;
  function kick() {
    if (raf) return;
    if (idle) { last = performance.now(); idle = false; }
    raf = requestAnimationFrame(step);
  }
  onBetaChange = kick;

  // Bila komputer tidak sanggup ±60 fps, turunkan pixel ratio (paling banyak dua kali).
  let fpsFrames = 0, fpsTime = 0, fpsChecks = 0;
  function measureFps(dt) {
    if (fpsChecks >= 2 || !root.classList.contains("model-ready")) return;
    fpsFrames++; fpsTime += dt;
    if (fpsTime < 2) return;
    const fps = fpsFrames / fpsTime;
    fpsFrames = 0; fpsTime = 0; fpsChecks++;
    if (fps < 45) stage.lowerQuality();
  }

  // Teks menempel selama bagiannya digulir, kecuali bila tidak muat di ruangnya: ponsel tegak = di bawah model
  // (±47% tinggi layar), lebar = di bawah posisi top 24% (layar pendek seperti HP miring sering tidak muat).
  function fitCopies() {
    const room = window.innerHeight * (stage.layout === "narrow" ? 0.47 : 0.72);
    for (const c of document.querySelectorAll(".sec .copy")) {
      c.classList.remove("tall");
      c.classList.toggle("tall", c.offsetHeight > room);
    }
  }
  document.fonts?.ready.then(fitCopies);
  fitCopies();

  window.addEventListener("scroll", kick, { passive: true });
  window.addEventListener("resize", () => { stage.resize(); fitCopies(); kick(); });
  document.addEventListener("visibilitychange", () => { idle = true; kick(); });
  reduce.addEventListener?.("change", kick);
  kick();
}

start();
