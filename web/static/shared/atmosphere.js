// Latar "debu di dalam berkas cahaya" (efek Tyndall): partikel halus melayang, lebih terang saat berada di dalam
// berkas cahaya diagonal dari kiri atas. Itulah cara polusi udara terlihat, dan itu yang diukur AirLens.
// Ringan: <= 110 partikel, 30 fps, berhenti saat tab tidak terlihat; diam (satu gambar) bila pengguna memilih
// mengurangi animasi. Lapisan berada di belakang semua isi (z-index -1) dan tidak menangkap klik.
(() => {
  if (window.__airlensAtmosphere) return;
  window.__airlensAtmosphere = true;

  const layer = document.createElement("div");
  layer.className = "atmo";
  layer.setAttribute("aria-hidden", "true");
  layer.innerHTML = '<canvas class="atmo-dust"></canvas>';
  document.body.prepend(layer);

  const canvas = layer.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let w = 0, h = 0, dpr = 1, dust = [], last = 0, running = false;

  // poros berkas cahaya (ruang 0..1): dari kiri atas ke tengah bawah
  const A = { x: 0.04, y: -0.05 }, B = { x: 0.62, y: 1.05 };
  const beamDist = (x, y) => {
    const ax = A.x * w, ay = A.y * h, bx = B.x * w, by = B.y * h;
    const dx = bx - ax, dy = by - ay;
    return Math.abs(dy * x - dx * y + bx * ay - by * ax) / Math.hypot(dx, dy);
  };

  function seed() {
    const n = Math.round(Math.min(110, (w * h) / 15000));
    dust = Array.from({ length: n }, () => spawn(Math.random() * w, Math.random() * h));
  }
  function spawn(x, y) {
    return { x, y, r: 0.4 + Math.random() * 1.3, vx: 4 + Math.random() * 8, vy: -2 + Math.random() * 4,
      ph: Math.random() * Math.PI * 2, tw: 0.4 + Math.random() * 1.2 };
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = innerWidth; h = innerHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    renderBeam();
    seed();
    draw(performance.now(), 0);
  }

  // berkas cahaya: kerucut dari kiri atas yang melebar dan memudar ke bawah (terang di pangkal), plus inti tipis
  // yang hanya terlihat di dekat pangkal. Sedikit "bernapas" mengikuti waktu.
  // Digambar SEKALI per ukuran layar ke kanvas terpisah (efek buram mahal); tiap frame hanya ditempel dengan
  // kecerahan yang bernapas.
  const beamCanvas = document.createElement("canvas");
  function renderBeam() {
    beamCanvas.width = canvas.width; beamCanvas.height = canvas.height;
    const ctx = beamCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const ax = A.x * w, ay = A.y * h, bx = B.x * w, by = B.y * h;
    const len = Math.hypot(bx - ax, by - ay), ang = Math.atan2(by - ay, bx - ax);
    const breathe = 1, wide = Math.max(w, h);
    ctx.save();
    ctx.translate(ax, ay); ctx.rotate(ang);
    const cone = (w0, w1, alpha) => {
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, len);
      g.addColorStop(0, `rgba(196,194,255,${(alpha * breathe).toFixed(3)})`);
      g.addColorStop(0.35, `rgba(120,116,255,${(alpha * 0.55 * breathe).toFixed(3)})`);
      g.addColorStop(1, "rgba(110,107,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0, -w0); ctx.lineTo(len, -w1); ctx.lineTo(len, w1); ctx.lineTo(0, w0);
      ctx.closePath(); ctx.fill();
    };
    ctx.filter = "blur(18px)";
    cone(wide * 0.02, wide * 0.32, 0.22);      // kerucut lebar, lembut
    cone(wide * 0.008, wide * 0.1, 0.28);      // kerucut sempit, lebih terang
    ctx.filter = "none";
    const core = ctx.createLinearGradient(0, 0, len * 0.4, 0);   // inti tipis, hanya dekat pangkal
    core.addColorStop(0, `rgba(235,235,255,${(0.35 * breathe).toFixed(3)})`); core.addColorStop(1, "rgba(235,235,255,0)");
    ctx.fillStyle = core;
    ctx.fillRect(0, -1, len * 0.4, 2);
    ctx.restore();
  }
  function beam(t) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 0.88 + 0.12 * Math.sin(t / 4200);
    ctx.drawImage(beamCanvas, 0, 0);
    ctx.restore();
  }

  function draw(t, dt) {
    ctx.clearRect(0, 0, w, h);
    beam(t);
    const half = Math.max(w, h) * 0.16;           // setengah lebar berkas yang "menyala"
    for (const p of dust) {
      if (dt) {
        p.x += p.vx * dt; p.y += (p.vy + Math.sin(t / 1700 + p.ph) * 3) * dt;   // angin pelan + gerak Brown
        if (p.x > w + 4) { p.x = -4; p.y = Math.random() * h; }
        if (p.y < -4) p.y = h + 4; else if (p.y > h + 4) p.y = -4;
      }
      const lit = Math.max(0, 1 - beamDist(p.x, p.y) / half);            // 1 di poros berkas, 0 di luar
      const twinkle = 0.75 + 0.25 * Math.sin(t / 1000 * p.tw + p.ph);
      const a = (0.1 + 0.75 * lit * lit) * twinkle;
      ctx.fillStyle = lit > 0.15 ? `rgba(222,221,255,${a.toFixed(3)})` : `rgba(170,175,210,${a.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * (1 + lit * 0.6), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function frame(t) {
    if (!running) return;
    const dt = Math.min(0.1, (t - last) / 1000);
    if (dt >= 1 / 30) { last = t; draw(t, dt); }
    requestAnimationFrame(frame);
  }
  function start() {
    if (running || reduced.matches || document.hidden) return;
    running = true; last = performance.now(); requestAnimationFrame(frame);
  }
  function stop() { running = false; }

  addEventListener("resize", resize);
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  reduced.addEventListener?.("change", () => (reduced.matches ? (stop(), draw(performance.now(), 0)) : start()));
  resize();
  start();
})();
