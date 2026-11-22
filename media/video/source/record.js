// Merekam tiap adegan langsung ke satu MP4 (JPEG di-pipe ke ffmpeg, tanpa file per frame).
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path"), { spawn } = require("child_process");
const { scenes, total, FADE, clamp } = require("./timeline");
const ROOT = __dirname, FPS = 30;
const types = { ".html": "text/html", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2" };
const srv = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0])); fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { "Content-Type": types[path.extname(f)] || "application/octet-stream" }); r.end(d); }); }).listen(8766);
const only = process.argv[2] ? process.argv[2].split(",") : null;
const step = Number(process.argv[3] || 1);   // >1 = pratinjau cepat (lewati frame)
fs.mkdirSync(path.join(ROOT, "out", "scenes"), { recursive: true });
(async () => {
  const b = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on("pageerror", (e) => console.log("ERR", e.message));
  await p.goto("http://localhost:8766/scene/index.html");
  await p.waitForFunction("window.ready === true", null, { timeout: 60000 });
  let start = 0;
  for (const s of scenes) {
    const s0 = start; start += s.dur;
    if (only && !only.includes(s.id)) continue;
    const n = Math.round(s.dur * FPS), tmp = path.join(ROOT, "out", "scenes", `${s.id}.part.mp4`), fin = tmp.replace(".part", "");
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS / step), "-c:v", "mjpeg", "-i", "-",
      "-vf", step > 1 ? `fps=${FPS}` : "null", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", String(FPS), "-f", "mp4", tmp]);
    const t0 = Date.now();
    for (let i = 0; i < n; i += step) {
      const t = i / FPS, o = s.o(t);
      o.progress = (s0 + t) / total;
      o.fade = Math.max(1 - clamp(t / FADE), clamp((t - (s.dur - FADE)) / FADE));
      await p.evaluate(([nm, tt, oo]) => window.show(nm, tt, oo), [s.scene, t, o]);
      const buf = await p.screenshot({ type: "jpeg", quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    }
    ff.stdin.end();
    const code = await new Promise((r) => ff.on("close", r));
    if (code === 0) fs.renameSync(tmp, fin);
    console.log(s.id, code === 0 ? "ok" : "GAGAL", ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); srv.close();
})();
