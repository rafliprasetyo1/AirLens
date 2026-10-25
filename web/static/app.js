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
const STAGE_TEXT = { mulai: "berjalan…", selesai: "selesai", gagal: "gagal" };
const STAGE_NAME = { periksa: "Memeriksa foto", analisis: "Menganalisis kabut", iqair: "Membandingkan dengan IQAir" };
const MAX_BYTES = 10 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];

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
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; }
}

// ------------------------------------------------------------------ pilih file & seret-lepas
function pick(file) {
  if (!file) return;
  if (!TYPES.includes(file.type)) return showAlert("Format tidak didukung", "Gunakan foto JPEG, PNG, atau WebP.", "warn");
  if (file.size > MAX_BYTES) return showAlert("File terlalu besar", "Ukuran maksimal 10 MB.", "warn");
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
  if (!msg) { msg = node("div", { class: "preview-missing" }, "Pratinjau tidak tersedia: berkas mungkin bukan gambar."); el.preview.prepend(msg); }
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
  } catch { el.geoStatus.textContent = "Daftar kota gagal dimuat; gunakan lokasi perangkat."; }
}
el.city.addEventListener("change", () => {
  if (el.city.value) { coords = null; el.geoStatus.textContent = "Memakai kota yang dipilih."; }
});
el.geo.addEventListener("click", () => {
  if (!navigator.geolocation) { el.geoStatus.textContent = "Peramban ini tidak mendukung lokasi."; return; }
  el.geoStatus.textContent = "Meminta izin lokasi…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      el.city.value = "";
      el.geoStatus.textContent = "Lokasi perangkat dipakai untuk mencari stasiun IQAir terdekat.";
    },
    () => { coords = null; el.geoStatus.textContent = "Izin lokasi ditolak. Pilih kota dari daftar."; },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
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
  el.analyze.textContent = b ? "Menganalisis…" : "Analisis foto";
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
  if (el.city.value) form.append("city_id", el.city.value);
  else if (coords) { form.append("lat", coords.lat); form.append("lon", coords.lon); }
  form.append("store_photo", el.consent.checked ? "true" : "false");
  if (narrow.matches) el.stages.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
  let job;
  try {
    const r = await fetch(`${API}/predict`, { method: "POST", body: form });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : `Server membalas ${r.status}.`);
    }
    job = await r.json();
  } catch (err) {
    setBusy(false);
    return showAlert("Gagal mengirim foto", err.message || "Server tidak terjangkau. Periksa koneksi lalu coba lagi.");
  }
  follow(job.job_id);
}

function follow(jobId) {
  if (source) source.close();
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
      else { setBusy(false); showAlert("Koneksi terputus", "Kemajuan tidak bisa diikuti. Coba lagi."); }
    }).catch(() => { setBusy(false); showAlert("Koneksi terputus", "Server tidak terjangkau. Coba lagi."); });
  };
}

// ------------------------------------------------------------------ hasil
function finish(res) {
  setBusy(false);
  if (res.status === "rejected") {
    showAlert("Foto tidak bisa dipakai", res.message);
    return addHistory("Ditolak", "#b9b8b2", res.message);
  }
  if (res.status === "error") {
    showAlert("Belum bisa memproses", res.message);
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

  el.eyebrow.textContent = uncertain ? "Belum pasti — kandidat teratas" : "Perkiraan kategori";
  el.chip.textContent = uncertain ? `Belum pasti (mungkin: ${cat.label})` : cat.label;
  el.range.textContent = `${cat.aqi_range[0]}–${cat.aqi_range[1]}`;
  el.advice.textContent = uncertain
    ? `Keyakinan ${pct(res.confidence)}% di bawah ambang ${pct(res.threshold)}%. Coba foto lain dengan langit lebih terlihat, atau lihat pembanding IQAir.`
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
  announce(uncertain ? `Hasil belum pasti. Kandidat teratas ${cat.label}.`
    : `Perkiraan: ${cat.label}, keyakinan ${pct(res.confidence)} persen.`);
  addHistory(uncertain ? "Belum pasti" : cat.label, uncertain ? "#9a9993" : cat.color,
    `keyakinan ${pct(res.confidence)}%${res.iqair?.status === "ok" ? ` · IQAir ${res.iqair.aqi_us}` : ""}`);
}

function renderIqair(iq) {
  el.iq.replaceChildren();
  if (!iq || iq.status !== "ok") {
    el.iq.append(node("p", { class: "muted" }, iq?.message || "Pembanding IQAir tidak tersedia."));
    return;
  }
  const grid = node("div", { class: "iq-grid" },
    node("span", { class: "iq-aqi" }, iq.aqi_us),
    node("div", {},
      node("p", {}, node("strong", {}, "AQI US"), ` · ${iq.city}${iq.state ? `, ${iq.state}` : ""}`),
      node("p", { class: "muted small" }, `Diperbarui ${fmtTime(iq.observed_at)}${iq.cached ? " (dari cache)" : ""}`)));
  const chip = node("p", { class: "chip", style: { background: iq.category.color, color: iq.category.text_color, marginTop: ".5rem" } },
    iq.category.label);
  el.iq.append(grid, chip);
  if (typeof iq.selisih_kategori === "number") {
    const d = iq.selisih_kategori;
    const text = d === 0 ? "Kategori perkiraan SAMA dengan IQAir."
      : `Perkiraan ${Math.abs(d)} kategori ${d > 0 ? "lebih buruk" : "lebih baik"} dari IQAir`
        + (iq.jarak_ke_rentang ? ` (AQI IQAir berjarak ${iq.jarak_ke_rentang} poin dari rentang perkiraan).` : ".");
    el.iq.append(node("p", { class: "iq-diff" }, text));
  } else {
    el.iq.append(node("p", { class: "iq-diff muted" }, "Selisih tidak dihitung karena hasil belum pasti."));
  }
}

function renderHints(hints) {
  el.hints.replaceChildren();
  for (const h of hints || []) {
    const fill = node("span");
    // Bar = tingkat kabut relatif data latih: persentil dibalik untuk petunjuk yang TURUN saat berkabut (kontras).
    const haze = h.percentile == null ? null : Math.round(h.hazier === "naik" ? h.percentile : 100 - h.percentile);
    const desc = haze == null ? "tanpa pembanding data latih" : `lebih berkabut dari ${haze}% foto latih`;
    el.hints.append(node("li", { class: "hint-row" },
      node("div", { class: "hint-head" }, node("span", {}, h.label),
        node("span", { class: "pct-text" }, haze == null ? "—" : `${haze}%`)),
      node("div", { class: "bar", role: "img", "aria-label": `${h.label}: ${desc}` }, fill),
      node("p", { class: "muted small" }, `${desc} · nilai ${h.value.toFixed(3)}`)));
    requestAnimationFrame(() => { fill.style.width = `${haze ?? 0}%`; });
  }
  el.hints.append(node("li", { class: "hint-scale", "aria-hidden": "true" }, node("span", {}, "lebih jernih"), node("span", {}, "lebih berkabut")));
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
  if (!items.length) { el.history.append(node("li", { class: "muted" }, "Belum ada.")); return; }
  for (const it of items) {
    el.history.append(node("li", {},
      node("span", { class: "swatch", style: { background: it.color }, "aria-hidden": "true" }),
      node("span", {}, `${fmtTime(it.at)} · ${it.label} · ${it.detail}`)));
  }
}

el.analyze.addEventListener("click", analyze);
el.retry.addEventListener("click", () => { hideAlert(); el.placeholder.hidden = false; if (selected) analyze(); else el.dz.focus(); });
loadCities();
renderHistory();
