// Uji UI sungguhan di Chrome headless (Puppeteer). Dijalankan oleh `make ui-test` di jaringan compose.
// Membuktikan: alur end-to-end, semua keadaan galat tampil, lebar 360 px, keyboard saja, reduced motion,
// kontras teks >= 4.5:1, dan tidak ada pergeseran tata letak saat hasil muncul.
"use strict";
const puppeteer = require("puppeteer");
const fs = require("fs");

const BASE = process.env.BASE_URL || "http://web";
const OUT = "/out";
const F = { photo: "/fixtures/test_photo.jpg", dark: "/fixtures/dark.jpg", fake: "/fixtures/palsu.jpg", big: "/fixtures/besar.jpg" };
const results = [];
let failed = 0;

function check(name, ok, detail = "") {
  results.push({ name, ok: !!ok, detail });
  if (!ok) failed++;
  console.log(`${ok ? "OK   " : "GAGAL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function newPage(browser, { width = 1280, height = 900, reduced = false } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  if (reduced) await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") page.errors.push(m.text()); });
  await page.evaluateOnNewDocument(() => {
    window.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  await page.goto(BASE, { waitUntil: "networkidle0" });
  return page;
}

async function upload(page, file) {
  const input = await page.$("#file");
  await input.uploadFile(file);
}
const waitDone = (page, timeout = 30000) => page.waitForFunction(
  () => document.querySelector("#analyze").textContent.trim() === "Analisis foto"
    && (!document.querySelector("#cards").hidden || !document.querySelector("#alert").hidden), { timeout });
const visible = (page, sel) => page.$eval(sel, (e) => getComputedStyle(e).display !== "none" && e.getBoundingClientRect().height > 0);
const text = (page, sel) => page.$eval(sel, (e) => e.textContent.trim());

// Kontras WCAG antara warna teks dan latar efektif (naik ke induk sampai ketemu latar tidak transparan).
const CONTRAST_FN = `(sel) => {
  const el = document.querySelector(sel); if (!el) return null;
  const parse = (c) => { const m = c.match(/[\\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] ?? 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  let bgEl = el, bg = parse(getComputedStyle(bgEl).backgroundColor);
  while (bg.a === 0 && bgEl.parentElement) { bgEl = bgEl.parentElement; bg = parse(getComputedStyle(bgEl).backgroundColor); }
  const fg = parse(getComputedStyle(el).color);
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return Math.round(((a + 0.05) / (b + 0.05)) * 100) / 100;
}`;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox", "--disable-dev-shm-usage"] });

  // ---------------------------------------------------------------- 1. alur normal, desktop
  {
    const page = await newPage(browser);
    check("halaman awal: kotak galat dan kartu hasil tersembunyi", !(await visible(page, "#alert")) && !(await visible(page, "#cards")));
    await page.screenshot({ path: `${OUT}/00_awal.png`, fullPage: true });
    check("disclaimer selalu terlihat", await visible(page, ".disclaimer"), await text(page, ".disclaimer"));
    const nCities = await page.$$eval("#city option", (o) => o.length - 1);
    check("daftar kota dimuat dari API", nCities >= 10, `${nCities} kota`);
    await upload(page, F.photo);
    check("pratinjau muncul", await visible(page, "#preview-img"));
    await page.select("#city", "jakarta");
    const clsBefore = await page.evaluate(() => window.__cls);
    await page.click("#analyze");
    await page.waitForFunction(() => document.querySelector("#dropzone").classList.contains("scanning")
      || document.querySelector("#analyze").textContent.includes("Menganalisis"), { timeout: 5000 }).catch(() => {});
    await waitDone(page);
    await new Promise((r) => setTimeout(r, 1500)); // animasi selesai sebelum tangkapan layar
    const stages = await page.$$eval("#stages li", (l) => l.map((x) => `${x.dataset.stage}:${x.className}`));
    check("tiga tahap menyala sesuai event API", stages.every((s) => s.endsWith(":selesai") || s.endsWith(":gagal")), stages.join(", "));
    check("kartu hasil tampil", await visible(page, "#cards"));
    check("chip kategori terisi", (await text(page, "#cat-chip")).length > 0, await text(page, "#cat-chip"));
    check("rentang indeks tampil", /\d+–\d+/.test(await text(page, "#cat-range")), await text(page, "#cat-range"));
    check("pembanding IQAir tampil", (await text(page, "#iq-body")).length > 0, (await text(page, "#iq-body")).slice(0, 80));
    check("3 petunjuk visual + skala", (await page.$$("#hints li.hint-row")).length === 3 && (await page.$$("#hints .hint-scale")).length === 1);
    check("kartu belum pasti bergaya beda (amber)", (await page.$eval("#main-card", (e) => e.classList.contains("uncertain"))) === (await text(page, "#cat-chip")).startsWith("Belum pasti"));
    check("riwayat sesi bertambah", (await page.$$eval("#history li", (l) => l.filter((x) => !x.classList.contains("muted")).length)) >= 1);
    const cls = (await page.evaluate(() => window.__cls)) - clsBefore;
    check("tidak ada pergeseran tata letak saat hasil muncul (CLS < 0.1)", cls < 0.1, `CLS ${cls.toFixed(4)}`);
    for (const [sel, label] of [["body", "teks utama"], [".tagline", "teks sekunder"], [".disclaimer strong", "disclaimer"],
      ["#cat-chip", "chip kategori"], [".btn.primary", "tombol utama"], ["#advice", "saran"], [".history li span:last-child", "riwayat"]]) {
      const c = await page.evaluate(`(${CONTRAST_FN})(${JSON.stringify(sel)})`);
      check(`kontras ${label} >= 4.5:1`, c !== null && c >= 4.5, `${c}:1`);
    }
    check("tanpa error JavaScript", page.errors.length === 0, page.errors.join(" | "));
    await page.screenshot({ path: `${OUT}/01_desktop_hasil.png`, fullPage: true });
    await page.close();
  }

  // ---------------------------------------------------------------- 2. keadaan galat
  {
    const page = await newPage(browser);
    await upload(page, F.fake);
    await page.click("#analyze");
    await waitDone(page);
    check("file palsu: pesan galat + tombol coba lagi", await visible(page, "#alert") && await visible(page, "#retry"),
      `${await text(page, "#alert-title")} — ${await text(page, "#alert-msg")}`);
    check("file palsu: tahap periksa merah", (await page.$eval('[data-stage="periksa"]', (e) => e.className)) === "gagal");
    check("file palsu: pratinjau rusak diganti pesan", await visible(page, ".preview-missing"));
    await new Promise((r) => setTimeout(r, 600)); // animasi masuk kotak galat selesai
    await page.screenshot({ path: `${OUT}/02_galat_file_palsu.png` });

    await upload(page, F.dark);
    await page.click("#analyze");
    await waitDone(page);
    await new Promise((r) => setTimeout(r, 600));
    check("foto gelap ditolak dengan alasan jelas", /gelap|malam/i.test(await text(page, "#alert-msg")), await text(page, "#alert-msg"));
    await page.screenshot({ path: `${OUT}/03_galat_foto_gelap.png` });

    await upload(page, F.big);
    check("file > 10 MB ditolak di browser", await visible(page, "#alert") && /besar/i.test(await text(page, "#alert-title")),
      await text(page, "#alert-title"));

    await upload(page, F.photo);  // tanpa kota: IQAir tidak tersedia, prediksi tetap jalan
    await page.select("#city", "");
    await page.click("#analyze");
    await waitDone(page);
    check("tanpa lokasi: hasil tetap tampil, IQAir diberi keterangan", await visible(page, "#cards")
      && /kota|lokasi/i.test(await text(page, "#iq-body")), await text(page, "#iq-body"));
    await page.screenshot({ path: `${OUT}/04_iqair_tidak_tersedia.png`, fullPage: true });
    await page.close();
  }
  {
    // Model tidak tersedia & server mati: respons API disimulasikan (intersepsi), yang diuji adalah tampilan UI-nya.
    const page = await newPage(browser);
    await page.setRequestInterception(true);
    let mode = "model";
    page.on("request", (req) => {
      const u = req.url();
      if (u.endsWith("/api/predict") && mode === "server") return req.respond({ status: 503, contentType: "application/json", body: '{"detail":"Layanan sedang tidak tersedia."}' });
      if (u.endsWith("/api/predict")) return req.respond({ status: 202, contentType: "application/json", body: '{"job_id":"sim"}' });
      if (u.endsWith("/api/jobs/sim/events")) {
        const res = { status: "error", code: "model_tidak_tersedia", message: "Model belum tersedia. Coba lagi beberapa saat lagi.", disclaimer: "x" };
        return req.respond({ status: 200, contentType: "text/event-stream",
          body: `event: tahap\ndata: {"stage":"periksa","status":"selesai"}\n\nevent: tahap\ndata: {"stage":"analisis","status":"gagal"}\n\nevent: hasil\ndata: ${JSON.stringify(res)}\n\n` });
      }
      return req.continue();
    });
    await upload(page, F.photo);
    await page.click("#analyze");
    await waitDone(page);
    check("model tidak tersedia: pesan jelas", /model/i.test(await text(page, "#alert-msg")), await text(page, "#alert-msg"));
    await page.screenshot({ path: `${OUT}/05_galat_model.png` });
    mode = "server";
    await page.click("#retry");
    await waitDone(page);
    check("server membalas 503: pesan jelas + coba lagi", await visible(page, "#retry") && /tidak tersedia|gagal/i.test(
      `${await text(page, "#alert-title")} ${await text(page, "#alert-msg")}`), await text(page, "#alert-msg"));
    await page.close();
  }

  // ---------------------------------------------------------------- 3. lebar ponsel 360 px
  {
    const page = await newPage(browser, { width: 360, height: 740 });
    await upload(page, F.photo);
    await page.select("#city", "bandung");
    await page.click("#analyze");
    await waitDone(page);
    await new Promise((r) => setTimeout(r, 1500));
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    check("360 px: tanpa gulir horizontal", sw <= 360, `scrollWidth ${sw}`);
    const small = await page.$$eval("button, select, [role=button]", (els) => els.filter((e) => e.offsetParent)
      .map((e) => [e.id || e.className, Math.round(e.getBoundingClientRect().height)]).filter(([, h]) => h < 44));
    check("360 px: target sentuh >= 44 px", small.length === 0, JSON.stringify(small));
    await page.screenshot({ path: `${OUT}/06_ponsel_360.png`, fullPage: true });
    await page.close();
  }

  // ---------------------------------------------------------------- 4. keyboard saja
  {
    const page = await newPage(browser);
    const focusInfo = () => page.evaluate(() => {
      const e = document.activeElement; const s = getComputedStyle(e);
      return { id: e.id || e.className || e.tagName, outline: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2 };
    });
    const seen = [];
    for (let i = 0; i < 8; i++) { await page.keyboard.press("Tab"); seen.push(await focusInfo()); }
    check("Tab menjangkau area unggah, kota, lokasi, persetujuan", ["dropzone", "city", "geo", "consent"].every((id) => seen.some((s) => s.id === id)),
      seen.map((s) => s.id).join(" → "));
    const focusable = seen.filter((s) => s.id !== "BODY");  // setelah elemen terakhir, fokus kembali ke dokumen
    check("fokus selalu terlihat (outline >= 2 px)", focusable.every((s) => s.outline), JSON.stringify(focusable.filter((s) => !s.outline)));
    check("elemen tersembunyi tidak bisa difokus", !seen.some((s) => s.id === "retry"), seen.map((s) => s.id).join(" → "));
    await page.focus("#dropzone");
    const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }), page.keyboard.press("Enter")]);
    await chooser.accept([F.photo]);
    check("Enter di area unggah membuka pemilih file", await visible(page, "#preview-img"));
    await page.focus("#city");
    await page.keyboard.press("ArrowDown");
    await page.focus("#consent");
    await page.keyboard.press("Space");
    check("persetujuan bisa dicentang dengan Spasi", await page.$eval("#consent", (e) => e.checked));
    await page.keyboard.press("Space"); // batalkan lagi: jangan simpan foto uji
    await page.focus("#analyze");
    await page.keyboard.press("Enter");
    await waitDone(page);
    check("analisis bisa dijalankan dengan keyboard", await visible(page, "#cards"));
    await page.close();
  }

  // ---------------------------------------------------------------- 5. prefers-reduced-motion
  {
    const page = await newPage(browser, { reduced: true });
    await upload(page, F.photo);
    await page.select("#city", "jakarta");
    await page.click("#analyze");
    await waitDone(page);
    const anim = await page.evaluate(() => {
      const card = document.querySelector(".card"), g = document.querySelector("#gauge-fg");
      return { card: getComputedStyle(card).animationName, gauge: getComputedStyle(g).transitionDuration,
        num: document.querySelector("#conf-num").textContent };
    });
    check("reduced motion: tanpa animasi kartu dan busur", anim.card === "none" && /^0s/.test(anim.gauge), JSON.stringify(anim));
    check("reduced motion: angka langsung nilai akhir", Number(anim.num) > 0, anim.num);
    await page.screenshot({ path: `${OUT}/07_reduced_motion.png` });
    await page.close();
  }

  await browser.close();
  fs.writeFileSync(`${OUT}/report.json`, JSON.stringify({ passed: results.length - failed, failed, results }, null, 2));
  console.log(`\n${results.length - failed} lulus, ${failed} gagal`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
