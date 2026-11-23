// AirLens frontend: unggah -> POST /api/predict -> event SSE per tahap -> hasil.
// Semua teks dari server dirender dengan textContent (tanpa innerHTML).
"use strict";

const API = "/api";
const $ = (id) => document.getElementById(id);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const el = {
  dz: $("dropzone"), file: $("file"), empty: $("dz-empty"), preview: $("preview"), img: $("preview-img"),
  name: $("preview-name"), city: $("city"), geo: $("geo"), geoStatus: $("geo-status"), consent: $("consent"),
  analyze: $("analyze"), stages: $("stages"), live: $("live"), placeholder: $("placeholder"), alert: $("alert"),
  alertTitle: $("alert-title"), alertMsg: $("alert-msg"), retry: $("retry"), cards: $("cards"), results: $("hasil"),
  gauge: $("gauge-fg"), confNum: $("conf-num"), eyebrow: $("verdict-eyebrow"), chip: $("cat-chip"),
  range: $("cat-range"), advice: $("advice"), smoke: $("smoke-badge"), iq: $("iq-body"), hints: $("hints"),
  probs: $("probs"), modelInfo: $("model-info"), history: $("history"), mainCard: $("main-card"),
};
const narrow = window.matchMedia("(max-width: 860px)");
const STAGE_TEXT = { mulai: "running…", selesai: "done", gagal: "failed" };
const STAGE_NAME = { periksa: "Checking photo", analisis: "Analysing haze", iqair: "Comparing with IQAir" };
const MAX_BYTES = 10 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp", "image/heif", "image/heic"];
// Sebagian browser (Chrome/Edge di Windows dan Android) memberi tipe kosong untuk foto HEIC: cek ekstensinya juga.
// Server tetap memeriksa isi file yang sebenarnya.
const EXTS = /\.(jpe?g|png|webp|heic|heif)$/i;
const isHeif = (f) => /heic|heif/i.test(f.type) || /\.(heic|heif)$/i.test(f.name);

let selected = null;      // File
let coords = null;        // {lat, lon}
let busy = false;
let source = null;        // EventSource aktif
let previewUrl = null;

// ------------------------------------------------------------------ util
function node(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "style") Object.assign(n.style, v);
    else n.setAttribute(k, v);
  }
  for (const c of children) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}
const pct = (p) => Math.round(p * 100);
function announce(msg) { el.live.textContent = ""; requestAnimationFrame(() => { el.live.textContent = msg; }); }
function fmtTime(iso) {
  try { return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; }
}

// ------------------------------------------------------------------ pilih file & seret-lepas
function pick(file) {
  if (!file) return;
  if (!TYPES.includes(file.type) && !EXTS.test(file.name)) return showAlert("Unsupported format", "Use a JPG/JPEG, PNG, WebP or HEIF/HEIC photo.", "warn");
  if (file.size > MAX_BYTES) return showAlert("File too large", "The maximum size is 10 MB.", "warn");
  selected = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  el.img.src = previewUrl;
  el.name.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  el.empty.hidden = true;
  el.preview.hidden = false;
  el.analyze.disabled = false;
  hideAlert();
}
el.img.addEventListener("error", () => {
  if (!el.img.getAttribute("src")) return;
  el.img.hidden = true;
  let msg = el.preview.querySelector(".preview-missing");
  if (!msg) { msg = node("div", { class: "preview-missing" }, ""); el.preview.prepend(msg); }
  // Browser selain Safari tidak bisa menampilkan HEIC; fotonya tetap bisa dianalisis server.
  msg.textContent = selected && isHeif(selected)
    ? "This browser cannot preview HEIF/HEIC. The photo can still be analysed."
    : "No preview: the file may not be an image.";
  msg.hidden = false;
});
el.img.addEventListener("load", () => {
  el.img.hidden = false;
  const msg = el.preview.querySelector(".preview-missing");
  if (msg) msg.hidden = true;
});
el.dz.addEventListener("click", () => !busy && el.file.click());
el.dz.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && !busy) { e.preventDefault(); el.file.click(); }
});
el.file.addEventListener("change", () => pick(el.file.files[0]));
for (const ev of ["dragenter", "dragover"]) {
  el.dz.addEventListener(ev, (e) => { e.preventDefault(); if (!busy) el.dz.classList.add("drag"); });
}
for (const ev of ["dragleave", "dragend", "drop"]) {
  el.dz.addEventListener(ev, (e) => { e.preventDefault(); el.dz.classList.remove("drag"); });
}
el.dz.addEventListener("drop", (e) => { if (!busy) pick(e.dataTransfer.files[0]); });

// ------------------------------------------------------------------ lokasi
async function loadCities() {
  try {
    const r = await fetch(`${API}/cities`);
    for (const c of await r.json()) el.city.append(node("option", { value: c.id }, `${c.name} (${c.state})`));
  } catch { el.geoStatus.textContent = "The city list did not load; use your device location."; }
}
const GEO = "__geo__";   // pilihan dropdown "My location" (koordinat perangkat, bukan kota dari daftar)
el.city.addEventListener("change", () => {
  if (el.city.value && el.city.value !== GEO) { coords = null; el.geoStatus.textContent = "Using the selected city."; }
});
function geoOption(label) {
  let opt = el.city.querySelector(`option[value="${GEO}"]`);
  if (!opt) { opt = node("option", { value: GEO }, ""); el.city.insertBefore(opt, el.city.options[1] || null); }
  opt.textContent = label;
  el.city.value = GEO;
}
el.geo.addEventListener("click", () => {
  if (!window.isSecureContext) { el.geoStatus.textContent = "Device location only works over https:// (for example the ngrok address). Choose a city from the list."; return; }
  if (!navigator.geolocation) { el.geoStatus.textContent = "This browser does not support location. Choose a city from the list."; return; }
  el.geoStatus.textContent = "Asking for location permission…";
  el.geo.disabled = true;
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      el.geo.disabled = false;
      coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      geoOption("My location (finding an IQAir station…)");
      el.geoStatus.textContent = `Location found (${coords.lat.toFixed(2)}, ${coords.lon.toFixed(2)}). Finding the nearest IQAir station…`;
      try {
        const r = await fetch(`${API}/nearest-city?lat=${coords.lat}&lon=${coords.lon}`);
        if (!r.ok) throw new Error(String(r.status));
        const c = await r.json();
        const place = [c.city, c.state].filter(Boolean).join(", ");
        geoOption(`My location: ${place}`);
        el.geoStatus.textContent = `Comparing with the nearest IQAir station: ${place} (US AQI ${c.aqi_us} now).`;
      } catch {
        geoOption("My location");
        el.geoStatus.textContent = "Using your device location; the nearest IQAir station is found during analysis.";
      }
    },
    (err) => {
      el.geo.disabled = false;
      coords = null;
      el.geoStatus.textContent = err.code === 1
        ? "Location permission was denied. On iPhone: Settings > Privacy & Security > Location Services > Safari Websites > While Using, then try again. Or choose a city from the list."
        : err.code === 3 ? "Finding your location took too long. Try again, or choose a city from the list."
        : "Your location could not be found (GPS or network). Choose a city from the list.";
    },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 },
  );
});

// ------------------------------------------------------------------ tahap & keadaan
function resetStages() {
  for (const li of el.stages.children) { li.className = ""; li.querySelector("[data-state]").textContent = ""; }
}
function setStage(stage, status) {
  const li = el.stages.querySelector(`[data-stage="${stage}"]`);
  if (!li) return;
  li.className = status;
  li.querySelector("[data-state]").textContent = STAGE_TEXT[status] || "";
  announce(`${STAGE_NAME[stage]}: ${STAGE_TEXT[status] || status}`);
  el.dz.classList.toggle("scanning", status === "mulai" && (stage === "periksa" || stage === "analisis"));
}
function showAlert(title, msg, kind = "error") {
  el.alertTitle.textContent = title;
  el.alertMsg.textContent = msg;
  el.alert.className = `alert${kind === "warn" ? " warn" : ""}`;
  el.alert.hidden = false;
  el.placeholder.hidden = true;
}
function hideAlert() { el.alert.hidden = true; }
function setBusy(b) {
  busy = b;
  el.analyze.disabled = b || !selected;
  el.analyze.textContent = b ? "Analysing…" : "Analyse photo";
  el.dz.setAttribute("aria-disabled", String(b));
  if (!b) el.dz.classList.remove("scanning");
}

// ------------------------------------------------------------------ kirim & ikuti event
async function analyze() {
  if (!selected || busy) return;
  setBusy(true);
  resetStages();
  hideAlert();
  el.cards.hidden = true;
  el.placeholder.hidden = false;
  const form = new FormData();
  form.append("file", selected);
  if (el.city.value && el.city.value !== GEO) form.append("city_id", el.city.value);
  else if (coords) { form.append("lat", coords.lat); form.append("lon", coords.lon); }
  form.append("store_photo", el.consent.checked ? "true" : "false");
  if (narrow.matches) el.stages.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
  let job;
  try {
    // 502/503/504 = layanan sedang dinyalakan ulang atau tunnel ngrok tersambung ulang: coba lagi otomatis (3 kali, ±9 detik).
    let r;
    for (let attempt = 0; ; attempt++) {
      r = await fetch(`${API}/predict`, { method: "POST", body: form });
      if (![502, 503, 504].includes(r.status) || attempt >= 3) break;
      setStage("periksa", "mulai");
      el.stages.querySelector('[data-stage="periksa"] [data-state]').textContent = `server not ready, retrying ${attempt + 1}/3`;
      announce(`Server not ready, retrying ${attempt + 1} of 3`);
      await new Promise((ok) => setTimeout(ok, 1500 * (attempt + 1)));
    }
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      const down = [502, 503, 504].includes(r.status);
      throw new Error(typeof body.detail === "string" ? body.detail
        : down ? `The service is unavailable (server replied ${r.status}). Wait a moment and try again.` : `Server replied ${r.status}.`);
    }
    job = await r.json();
  } catch (err) {
    setBusy(false);
    return showAlert("Could not send the photo", err.message || "The server is unreachable. Check your connection and try again.");
  }
  follow(job.job_id);
}

function follow(jobId) {
  if (source) source.close();
  currentJob = jobId;
  source = new EventSource(`${API}/jobs/${jobId}/events`);
  source.addEventListener("tahap", (e) => {
    const ev = JSON.parse(e.data);
    if (ev.stage in STAGE_NAME) setStage(ev.stage, ev.status);
  });
  source.addEventListener("hasil", (e) => {
    source.close();
    source = null;
    finish(JSON.parse(e.data));
  });
  source.onerror = () => {
    // Koneksi SSE putus: ambil status terakhir sekali sebagai cadangan.
    if (!source) return;
    source.close();
    source = null;
    fetch(`${API}/jobs/${jobId}`).then((r) => r.json()).then((j) => {
      for (const ev of j.events || []) if (ev.stage in STAGE_NAME) setStage(ev.stage, ev.status);
      if (j.done) finish(j.result);
      else { setBusy(false); showAlert("Connection lost", "Progress could not be followed. Try again."); }
    }).catch(() => { setBusy(false); showAlert("Connection lost", "The server is unreachable. Try again."); });
  };
}

// ------------------------------------------------------------------ hasil
function finish(res) {
  setBusy(false);
  if (res.status === "rejected") {
    showAlert("This photo cannot be used", res.message);
    return addHistory("Rejected", "#b9b8b2", res.message);
  }
  if (res.status === "error") {
    showAlert("Cannot process yet", res.message);
    return;
  }
  renderResult(res);
  el.results.focus({ preventScroll: true });
  el.results.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
}

function countUp(target) {
  if (reduceMotion.matches) { el.confNum.textContent = target; return; }
  const t0 = performance.now(), dur = 1000;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    el.confNum.textContent = Math.round(target * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderResult(res) {
  const uncertain = res.status === "uncertain";
  const cat = uncertain ? res.top_candidate : res.category;
  const root = document.documentElement;
  root.style.setProperty("--cat", uncertain ? "#e7c35a" : cat.color);
  root.style.setProperty("--cat-ink", uncertain ? "#0b0b0b" : cat.text_color);

  // Belum pasti: tampilkan dua kandidat teratas (peluang terkalibrasi, jadi boleh dijumlahkan).
  const ru = uncertain ? res.runner_up : null;
  el.eyebrow.textContent = uncertain ? (ru ? "Uncertain: top two candidates" : "Uncertain: top candidate")
    : "Estimated level";
  el.chip.textContent = uncertain ? `Uncertain (maybe ${cat.label})` : cat.label;
  el.range.textContent = ru ? candidateRange(cat, ru) : `${cat.aqi_range[0]}–${cat.aqi_range[1]}`;
  el.advice.textContent = uncertain
    ? (ru ? `Probably ${cat.label} (${pct(res.confidence)}%) or ${ru.label} (${pct(ru.p)}%), `
        + `${pct(res.confidence + ru.p)}% combined. ` : "")
      + `Confidence ${pct(res.confidence)}% is below the ${pct(res.threshold)}% threshold. Try another photo with more sky, or check the IQAir comparison.`
    : cat.advice;
  el.smoke.hidden = !res.model?.smoke;
  el.mainCard.classList.toggle("uncertain", uncertain);

  // Busur keyakinan: dikosongkan dulu, lalu diisi (transisi CSS).
  const len = 157;
  el.gauge.style.transition = "none";
  el.gauge.style.strokeDashoffset = len;
  el.confNum.textContent = "0";
  void el.gauge.getBoundingClientRect();
  el.gauge.style.transition = "";
  requestAnimationFrame(() => { el.gauge.style.strokeDashoffset = len * (1 - res.confidence); });
  countUp(pct(res.confidence));

  renderIqair(res.iqair);
  renderHints(res.hints);
  renderProbs(res.probabilities, cat.key);
  el.modelInfo.textContent = res.model
    ? `Model ${res.model.version} · data ${String(res.model.data_version || "").slice(0, 12)} · ${Math.round(res.latency_ms)} ms`
    : "";

  el.placeholder.hidden = true;
  // Mulai ulang animasi masuk bertahap.
  el.cards.hidden = true;
  void el.cards.offsetWidth;
  el.cards.hidden = false;
  announce(uncertain ? `Uncertain result. Top candidate ${cat.label}${ru ? `, then ${ru.label}` : ""}.`
    : `Estimate: ${cat.label}, ${pct(res.confidence)} percent confidence.`);
  addHistory(uncertain ? "Uncertain" : cat.label, uncertain ? "#9a9993" : cat.color,
    `confidence ${pct(res.confidence)}%${res.iqair?.status === "ok" ? ` · IQAir ${res.iqair.aqi_us}` : ""}`);
}

// Rentang AQI dua kandidat: digabung bila bersebelahan, dipisah bila tidak.
function candidateRange(a, b) {
  const [lo, hi] = a.aqi_range[0] < b.aqi_range[0] ? [a, b] : [b, a];
  return lo.aqi_range[1] + 1 === hi.aqi_range[0]
    ? `${lo.aqi_range[0]}–${hi.aqi_range[1]}`
    : `${lo.aqi_range[0]}–${lo.aqi_range[1]} or ${hi.aqi_range[0]}–${hi.aqi_range[1]}`;
}

function renderIqair(iq) {
  el.iq.replaceChildren();
  if (!iq || iq.status !== "ok") {
    el.iq.append(node("p", { class: "muted" }, iq?.message || "IQAir comparison unavailable."));
    return;
  }
  const grid = node("div", { class: "iq-grid" },
    node("span", { class: "iq-aqi" }, iq.aqi_us),
    node("div", {},
      node("p", {}, node("strong", {}, "US AQI"), ` in ${iq.city}${iq.state ? `, ${iq.state}` : ""}`),
      node("p", { class: "muted small" }, iq.stale
        ? `No internet: using the last saved IQAir reading (fetched ${fmtTime(iq.fetched_at)}).`
        : `Updated ${fmtTime(iq.observed_at)}${iq.cached ? " (cached)" : ""}`)));
  const chip = node("p", { class: "chip", style: { background: iq.category.color, color: iq.category.text_color, marginTop: ".5rem" } },
    iq.category.label);
  el.iq.append(grid, chip);
  if (typeof iq.selisih_kategori === "number") {
    const d = iq.selisih_kategori;
    const text = d === 0 ? "The estimate MATCHES IQAir."
      : `The estimate is ${Math.abs(d)} level${Math.abs(d) > 1 ? "s" : ""} ${d > 0 ? "worse" : "better"} than IQAir`
        + (iq.jarak_ke_rentang ? ` (the IQAir AQI is ${iq.jarak_ke_rentang} points outside the estimated range).` : ".");
    el.iq.append(node("p", { class: "iq-diff" }, text));
  } else {
    el.iq.append(node("p", { class: "iq-diff muted" }, "No difference shown because the result is uncertain."));
  }
}

function renderHints(hints) {
  el.hints.replaceChildren();
  for (const h of hints || []) {
    const fill = node("span");
    // Bar = tingkat kabut relatif data latih: persentil dibalik untuk petunjuk yang TURUN saat berkabut (kontras).
    const haze = h.percentile == null ? null : Math.round(h.hazier === "naik" ? h.percentile : 100 - h.percentile);
    const desc = haze == null ? "no training-data reference" : `hazier than ${haze}% of training photos`;
    el.hints.append(node("li", { class: "hint-row" },
      node("div", { class: "hint-head" }, node("span", {}, h.label),
        node("span", { class: "pct-text" }, haze == null ? "—" : `${haze}%`)),
      node("div", { class: "bar", role: "img", "aria-label": `${h.label}: ${desc}` }, fill),
      node("p", { class: "muted small" }, `${desc}, value ${h.value.toFixed(3)}`)));
    requestAnimationFrame(() => { fill.style.width = `${haze ?? 0}%`; });
  }
  el.hints.append(node("li", { class: "hint-scale", "aria-hidden": "true" }, node("span", {}, "clearer"), node("span", {}, "hazier")));
}

function renderProbs(probs, topKey) {
  el.probs.replaceChildren();
  for (const p of probs || []) {
    const fill = node("span");
    el.probs.append(node("li", { class: `prob-row${p.key === topKey ? " top" : ""}` },
      node("span", {}, p.label), node("div", { class: "bar", "aria-hidden": "true" }, fill),
      node("span", { class: "val" }, `${pct(p.p)}%`)));
    requestAnimationFrame(() => { fill.style.width = `${pct(p.p)}%`; });
  }
}

// ------------------------------------------------------------------ riwayat sesi
function addHistory(label, color, detail) {
  let items = [];
  try { items = JSON.parse(sessionStorage.getItem("airlens-history") || "[]"); } catch { /* sessionStorage tidak tersedia */ }
  items.unshift({ label, color, detail, at: new Date().toISOString(), file: selected?.name || "" });
  items = items.slice(0, 10);
  try { sessionStorage.setItem("airlens-history", JSON.stringify(items)); } catch { /* abaikan */ }
  renderHistory(items);
}
function renderHistory(items) {
  if (!items) { try { items = JSON.parse(sessionStorage.getItem("airlens-history") || "[]"); } catch { items = []; } }
  el.history.replaceChildren();
  if (!items.length) { el.history.append(node("li", { class: "muted" }, "Nothing yet.")); return; }
  for (const it of items) {
    el.history.append(node("li", {},
      node("span", { class: "swatch", style: { background: it.color }, "aria-hidden": "true" }),
      node("span", {}, `${fmtTime(it.at)} · ${it.label} · ${it.detail}`)));
  }
}

let currentJob = null;

el.analyze.addEventListener("click", analyze);
el.retry.addEventListener("click", () => { hideAlert(); el.placeholder.hidden = false; if (selected) analyze(); else el.dz.focus(); });
loadCities();
renderHistory();
