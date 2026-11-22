const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path");
const { scenes } = require("./timeline");
const ROOT = __dirname, types = { ".html": "text/html", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2" };
const srv = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0])); fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { "Content-Type": types[path.extname(f)] || "application/octet-stream" }); r.end(d); }); }).listen(8767);
const req = JSON.parse(process.argv[2]), out = process.argv[3];
(async () => {
  const b = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on("pageerror", (e) => console.log("ERR", e.message));
  await p.goto("http://localhost:8767/scene/index.html"); await p.waitForFunction("window.ready === true");
  for (const [id, t] of req) {
    const s = scenes.find((x) => x.id === id); const o = s.o(t); o.fade = 0; o.progress = 0.5;
    await p.evaluate(([nm, tt, oo]) => window.show(nm, tt, oo), [s.scene, t, o]);
    await p.screenshot({ path: `${out}/peek_${id}_${t}.jpg`, type: "jpeg", quality: 80 });
  }
  await b.close(); srv.close();
})();
