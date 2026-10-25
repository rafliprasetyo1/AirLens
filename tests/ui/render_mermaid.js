// Validasi diagram Mermaid di ARCHITECTURE.md: render tiap blok di Chrome headless; galat sintaks = gagal.
// Dijalankan oleh `make docs-check`; gambar hasil render di results/ui/diagram_<n>.png.
const puppeteer = require("puppeteer");
const fs = require("fs");
(async () => {
  const md = fs.readFileSync("/doc/ARCHITECTURE.md", "utf8");
  const blocks = [...md.matchAll(/```mermaid\n([\s\S]*?)```/g)].map((m) => m[1]);
  const b = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
  const p = await b.newPage();
  await p.setViewport({ width: 1600, height: 1200 });
  await p.setContent(`<html><body style="background:#fff"><div id="out"></div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script></body></html>`, { waitUntil: "networkidle0" });
  let bad = 0;
  for (let i = 0; i < blocks.length; i++) {
    const r = await p.evaluate(async (code, i) => {
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
      try { const { svg } = await mermaid.render(`d${i}`, code); document.getElementById("out").innerHTML = svg; return "OK"; }
      catch (e) { return "GALAT: " + String(e.message || e).slice(0, 300); }
    }, blocks[i], i);
    console.log(`diagram ${i + 1}: ${r}`);
    if (r !== "OK") bad++;
    else await (await p.$("#out svg")).screenshot({ path: `/out/diagram_${i + 1}.png` });
  }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
