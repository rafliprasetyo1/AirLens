// Halaman Beta: polling GET /api/sensor/... setiap 3 detik, berhenti saat tab tersembunyi.
// Dua format node: lama (satu MQ-2, rasio Rs) dan baru (4 MQ + model gas Beta + SHAP, revisi Beta SHAP).
// Semua teks dari server dipasang dengan textContent (tanpa innerHTML).
"use strict";

const API = "/api/sensor";
// Layar booth (localhost) polling 3 s; lewat ngrok 10 s, karena paket ngrok gratis membatasi jumlah permintaan per bulan.
const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
const POLL_MS = LOCAL ? 3000 : 10000;
const $ = (id) => document.getElementById(id);
const el = {
  status: $("status"), word: $("status-word"), detail: $("status-detail"), notice: $("notice"),
  noticeTitle: $("notice-title"), noticeText: $("notice-text"),
  id: $("node-id"), online: $("node-online"), seen: $("node-seen"), rs: $("node-rs"), rowRs: $("row-rs"),
  baseline: $("node-baseline"), rowModel: $("row-model"), model: $("node-model"),
  pick: $("node-pick"), select: $("node-select"), chart: $("chart"), empty: $("chart-empty"),
  chartTitle: $("chart-title"), chartLegend: $("chart-legend"),
  decision: $("decision"), probs: $("probs"), wf: $("waterfall"), wfReason: $("wf-reason"), wfCaption: $("wf-caption"),
  modelMissing: $("model-missing"), modelMetrics: $("model-metrics"), modelCite: $("model-cite"),
  globalPlots: $("global-plots"),
};
const WORDS = { warming_up: "Warming up", normal: "Normal", alert: "Alert", offline: "Offline" };
const CLASS_TEXT = { clean_air: "Clean air", alcohol: "Alcohol / VOC", smoke: "Smoke", smoke_alcohol: "Smoke + alcohol" };
const SENSORS = [["MQ2", "MQ-2", "#2ba8e0"], ["MQ3", "MQ-3", "#f2c14e"], ["MQ7", "MQ-7", "#c9a7ff"],
  ["MQ135", "MQ-135", "#7fd4a8"]];
const FEATURE_TEXT = { r_mq2: "MQ-2", r_mq3: "MQ-3", r_mq7: "MQ-7", r_mq135: "MQ-135", mq3_over_mq2: "MQ-3 / MQ-2" };
let nodeId = null, chosenByUser = false, timer = 0;
let histNode = null, histRows = [], nodesCache = null, nodesAt = 0, explainFor = null;

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
  return r.json();
}

// Alat asli yang online diutamakan, lalu simulator yang online, lalu node yang terakhir terlihat.
function chooseNode(nodes) {
  if (chosenByUser && nodes.some((n) => n.node_id === nodeId)) return nodeId;
  const pick = nodes.find((n) => n.online && !n.simulated) || nodes.find((n) => n.online) || nodes[0];
  return pick ? pick.node_id : null;
}

function renderPicker(nodes) {
  el.pick.hidden = nodes.length < 2;
  if (nodes.length < 2) return;
  const want = nodes.map((n) => n.node_id).join("|");
  if (el.select.dataset.ids !== want) {
    el.select.replaceChildren(...nodes.map((n) => {
      const o = document.createElement("option");
      o.value = n.node_id;
      o.textContent = n.simulated ? `${n.node_id} (Simulated)` : n.node_id;
      return o;
    }));
    el.select.dataset.ids = want;
  }
  el.select.value = nodeId;
}

function ago(s) {
  if (s == null) return "–";
  if (s < 60) return `${Math.round(s)} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}
const pct = (p) => `${Math.round(p * 100)}%`;

function renderStatus(d) {
  const state = d.online ? d.state : "offline";
  const mq4 = d.format === "mq4", m = d.model || {};
  el.status.dataset.state = state;
  el.word.textContent = WORDS[state] || state;
  let detail;
  if (!d.online) detail = "No reading for more than 20 seconds. Check the node's power and WiFi.";
  else if (d.valid === false) detail = "A sensor is not giving a valid reading. Check its cable.";
  else if (d.state === "warming_up") {
    const w = d.warmup || {};
    detail = w.remaining_s > 0 ? `Heating the sensors: about ${Math.ceil(w.remaining_s / 60)} min left.`
      : `Learning clean air: ${w.samples} of ${w.needed} readings.`;
  } else if (mq4 && m.available && m.probs) {
    detail = `${CLASS_TEXT[m.class] || m.class}, ${pct(m.probs[m.class])} sure`;
  } else detail = d.ratio != null ? `MQ-2 at ${d.ratio.toFixed(2)}× the clean-air baseline` : "";
  el.detail.textContent = detail;

  const alcohol = mq4 && m.alert_label === "alcohol";
  el.noticeTitle.textContent = alcohol ? "Alcohol or VOC detected" : "Possible local smoke or gas";
  el.noticeText.textContent = alcohol
    ? "Something like sanitizer, perfume or solvent is nearby. Ventilate the room if the smell is strong."
    : "Open the windows and check for a source nearby, such as burning rubbish, incense or a gas leak.";
  el.notice.hidden = !(d.online && d.state === "alert");

  el.id.replaceChildren(document.createTextNode(d.node_id));
  if (d.simulated) {
    const tag = document.createElement("span");
    tag.className = "sim";
    tag.textContent = "Simulated";
    el.id.append(tag);
  }
  el.online.textContent = d.online ? "Online" : "Offline";
  el.seen.textContent = ago(d.seconds_since);
  el.rowRs.hidden = mq4;
  el.rs.textContent = d.rs_kohm != null && d.valid ? `${d.rs_kohm.toFixed(2)} kΩ` : d.valid === false ? "invalid reading" : "–";
  if (mq4) {
    const b = d.sensors && d.sensors.baseline_rs_kohm;
    el.baseline.textContent = b ? SENSORS.map(([k, n]) => `${n} ${b[k].toFixed(2)} kΩ`).join(" · ") : "being learned";
  } else {
    el.baseline.textContent = d.baseline_kohm != null ? `${d.baseline_kohm.toFixed(2)} kΩ` : "being learned";
  }
  el.rowModel.hidden = !mq4;
  el.model.textContent = m.available ? m.version : "not available (MQ-2 rule)";
}

// ------------------------------------------------------------------ grafik SVG (tanpa pustaka)
const NS = "http://www.w3.org/2000/svg";
const H = 240, PAD = { l: 40, r: 12, t: 14, b: 28 }, YMAX = 1.5, WINDOW_MS = 30 * 60 * 1000;
function svg(tag, attrs, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}
function linePath(readings, value, x, y, x0) {
  // Garis terputus di bacaan tanpa nilai (pemanasan/tidak valid) dan di jeda > 20 detik (node offline).
  let path = "", prev = null, points = 0;
  for (const r of readings) {
    const t = Date.parse(r.t), v = value(r);
    if (v == null || t < x0) { prev = null; continue; }
    path += `${prev == null || t - prev > 20000 ? "M" : "L"}${x(t).toFixed(1)},${y(v).toFixed(1)}`;
    prev = t; points++;
  }
  return [path, points];
}
function renderChart(readings, thresholds, mq4) {
  const W = Math.max(320, Math.round(el.chart.clientWidth || 640));
  el.chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const now = Date.now(), x0 = now - WINDOW_MS;
  const x = (t) => PAD.l + ((t - x0) / WINDOW_MS) * (W - PAD.l - PAD.r);
  const y = (v) => PAD.t + (1 - Math.min(v, YMAX) / YMAX) * (H - PAD.t - PAD.b);
  const kids = [el.chart.querySelector("desc")];
  for (const v of [0.5, 1.0, 1.5]) {
    kids.push(svg("line", { class: "grid", x1: PAD.l, x2: W - PAD.r, y1: y(v), y2: y(v) }));
    kids.push(svg("text", { class: "axis", x: PAD.l - 8, y: y(v) + 4, "text-anchor": "end" }, v.toFixed(1)));
  }
  if (!mq4) {
    kids.push(svg("rect", { class: "alert-band", x: PAD.l, y: y(thresholds.alert), width: W - PAD.l - PAD.r, height: y(0) - y(thresholds.alert) }));
    kids.push(svg("line", { class: "rec", x1: PAD.l, x2: W - PAD.r, y1: y(thresholds.recover), y2: y(thresholds.recover) }));
    kids.push(svg("line", { class: "thr", x1: PAD.l, x2: W - PAD.r, y1: y(thresholds.alert), y2: y(thresholds.alert) }));
  }
  for (const [label, t] of [["30 min ago", x0], ["15 min", now - WINDOW_MS / 2], ["now", now]]) {
    const anchor = t === x0 ? "start" : t === now ? "end" : "middle";
    kids.push(svg("text", { class: "axis", x: x(t), y: H - 8, "text-anchor": anchor }, label));
  }
  let total = 0;
  if (mq4) {
    for (const [k, , color] of SENSORS) {
      const [d, n] = linePath(readings, (r) => r.ratios && r.ratios[`r_${k.toLowerCase()}`], x, y, x0);
      if (d) kids.push(svg("path", { class: "series", d, style: `stroke:${color}` }));
      total += n;
    }
  } else {
    const [d, n] = linePath(readings, (r) => r.ratio, x, y, x0);
    if (d) kids.push(svg("path", { class: "series", d }));
    total = n;
  }
  el.chart.replaceChildren(...kids);
  el.empty.hidden = total > 0;
}
function renderLegend(mq4) {
  if (el.chartLegend.dataset.mq4 === String(mq4)) return;
  el.chartLegend.dataset.mq4 = String(mq4);
  el.chartTitle.textContent = mq4 ? "Each sensor's ratio to clean air, last 30 minutes (lower = more gas)"
    : "Ratio to clean air, last 30 minutes";
  if (mq4) {
    el.chartLegend.replaceChildren(...SENSORS.map(([, name, color]) => {
      const s = document.createElement("span");
      const key = document.createElement("span");
      key.className = "key line";
      key.style.borderTopColor = color;
      s.append(key, name);
      return s;
    }));
  } else {
    el.chartLegend.replaceChildren();
    const a = Object.assign(document.createElement("span"), { className: "key line" });
    const b = Object.assign(document.createElement("span"), { className: "key dash" });
    el.chartLegend.append(a, " reading ", b, " alert below 0.6");
  }
}

// ------------------------------------------------------------------ keputusan model: peluang + waterfall SHAP
function renderProbs(probs, chosen) {
  el.probs.replaceChildren(...Object.keys(CLASS_TEXT).map((c) => {
    const li = document.createElement("li");
    li.dataset.chosen = String(c === chosen);
    const name = Object.assign(document.createElement("span"), { className: "p-name", textContent: CLASS_TEXT[c] });
    const bar = Object.assign(document.createElement("span"), { className: "p-bar" });
    const fill = Object.assign(document.createElement("span"), { className: "p-fill" });
    fill.style.width = `${Math.round((probs[c] || 0) * 100)}%`;
    bar.append(fill);
    const val = Object.assign(document.createElement("span"), { className: "p-val", textContent: pct(probs[c] || 0) });
    li.append(name, bar, val);
    return li;
  }));
}

function renderWaterfall(ex) {
  // Mulai dari nilai dasar (skor rata-rata model), tiap fitur menggeser skor; urut dari dorongan terbesar.
  const W = Math.max(320, Math.round(el.wf.clientWidth || 640));
  const items = Object.entries(ex.shap).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const rowH = 30, top = 10, labelW = Math.min(170, W * 0.36), right = 64;
  const Hh = top + rowH * (items.length + 2) + 24;
  el.wf.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  let run = ex.expected_value;
  const points = [run];
  for (const [, v] of items) { run += v; points.push(run); }
  const lo = Math.min(...points, 0), hi = Math.max(...points, 0);
  const pad = (hi - lo) * 0.08 || 1;
  const x = (v) => labelW + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (W - labelW - right);
  const kids = [el.wf.querySelector("desc")];
  kids.push(svg("line", { class: "wf-zero", x1: x(0), x2: x(0), y1: top - 4, y2: Hh - 22 }));
  const row = (i, label, from, to, cls, valueText) => {
    const yy = top + i * rowH;
    kids.push(svg("text", { class: "wf-label", x: labelW - 10, y: yy + rowH / 2 + 4, "text-anchor": "end" }, label));
    const a = Math.min(x(from), x(to)), b = Math.max(x(from), x(to));
    kids.push(svg("rect", { class: cls, x: a, y: yy + 5, width: Math.max(2, b - a), height: rowH - 10, rx: 3 }));
    kids.push(svg("text", { class: "wf-value", x: b + 6, y: yy + rowH / 2 + 4 }, valueText));
  };
  row(0, "Average score", 0, ex.expected_value, "wf-base", ex.expected_value.toFixed(2));
  let cur = ex.expected_value;
  items.forEach(([f, v], i) => {
    const val = ex.features && ex.features[f];
    const label = `${FEATURE_TEXT[f] || f}${val != null ? ` = ${val.toFixed(2)}${f.startsWith("r_") ? "×" : ""}` : ""}`;
    row(i + 1, label, cur, cur + v, v >= 0 ? "wf-pos" : "wf-neg", `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}`);
    cur += v;
  });
  row(items.length + 1, `Score for “${CLASS_TEXT[ex.class] || ex.class}”`, 0, ex.score, "wf-final", ex.score.toFixed(2));
  kids.push(svg("text", { class: "axis", x: labelW, y: Hh - 6 }, "red: pushes towards this class · blue: pushes away"));
  el.wf.replaceChildren(...kids);
  el.wfCaption.textContent = `SHAP for the latest reading: why “${CLASS_TEXT[ex.class] || ex.class}”`;
  el.wfReason.textContent = ex.reason || "";
}

async function renderDecision(latest) {
  if (latest.format !== "mq4") { el.decision.hidden = true; return; }
  el.decision.hidden = false;
  const m = latest.model || {};
  el.modelMissing.hidden = Boolean(m.available) || latest.state === "warming_up";
  if (!m.available || !m.probs) {
    el.probs.replaceChildren();
    el.wf.replaceChildren(el.wf.querySelector("desc"));
    el.wfReason.textContent = latest.state === "warming_up" ? "The explanation appears once the clean-air baseline is learned." : "";
    return;
  }
  renderProbs(m.probs, m.class);
  const key = `${latest.node_id}|${latest.received_at}`;
  if (key === explainFor) return;                       // penjelasan hanya diambil ulang bila ada bacaan baru
  try {
    const ex = await getJSON(`/api/beta/explain/latest?node_id=${encodeURIComponent(latest.node_id)}`);
    if (ex.model_available) { renderWaterfall(ex); explainFor = key; }
  } catch { /* coba lagi pada putaran berikutnya */ }
}

// ------------------------------------------------------------------ ringkasan model (sekali)
async function loadModelSummary() {
  try {
    const s = await getJSON("/api/beta/model");
    if (s.available && s.test_macro_f1 != null) {
      el.modelMetrics.textContent = `On held-out readings from the training data the model reaches a macro-F1 of `
        + `${s.test_macro_f1.toFixed(2)} (the old MQ-2-only rule: ${(s.baseline_rule_test_macro_f1 ?? 0).toFixed(2)}). `
        + "Expect lower scores on our own device until it is calibrated.";
    }
    if (!s.available) el.globalPlots.hidden = true;
  } catch { el.globalPlots.hidden = true; }
  el.globalPlots.querySelectorAll("img").forEach((img) => {
    img.addEventListener("error", () => { img.closest("figure").hidden = true; });
  });
}

// ------------------------------------------------------------------ polling
async function tick() {
  try {
    if (!nodesCache || LOCAL || Date.now() - nodesAt > 30000) { nodesCache = await getJSON(`${API}/nodes`); nodesAt = Date.now(); }
    const nodes = nodesCache;
    nodeId = chooseNode(nodes);
    renderPicker(nodes);
    if (!nodeId) {
      el.status.dataset.state = "loading";
      el.word.textContent = "No sensor yet";
      el.detail.textContent = "Waiting for the first reading from an AirLens Beta node or the simulator.";
      el.notice.hidden = true;
      el.decision.hidden = true;
      renderLegend(true);
      renderChart([], { alert: 0.6, recover: 0.8 }, true);
      return;
    }
    // Riwayat bertahap: unduh 30 menit sekali, lalu hanya bacaan baru (since), simpan di browser.
    const since = histNode === nodeId && histRows.length ? `&since=${encodeURIComponent(histRows[histRows.length - 1].t)}` : "";
    const [latest, add] = await Promise.all([
      getJSON(`${API}/latest?node_id=${encodeURIComponent(nodeId)}`),
      getJSON(`${API}/history?node_id=${encodeURIComponent(nodeId)}&minutes=30${since}`),
    ]);
    if (!since) { histRows = []; histNode = nodeId; }
    const cutoff = Date.now() - 30 * 60 * 1000;
    histRows = histRows.concat(add.readings).filter((r) => Date.parse(r.t) >= cutoff);
    const hist = { readings: histRows };
    const mq4 = latest.format === "mq4";
    renderStatus(latest);
    renderLegend(mq4);
    renderChart(hist.readings, latest.thresholds, mq4);
    await renderDecision(latest);
  } catch (err) {
    el.status.dataset.state = "error";
    el.word.textContent = "No connection";
    el.detail.textContent = "AirLens can't be reached right now. The page keeps trying.";
    el.notice.hidden = true;
  }
}
function schedule() {
  clearTimeout(timer);
  if (document.hidden) return;
  timer = setTimeout(async () => { await tick(); schedule(); }, POLL_MS);
}
el.select.addEventListener("change", () => { nodeId = el.select.value; chosenByUser = true; histNode = null; tick(); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) { tick(); schedule(); } else clearTimeout(timer); });
loadModelSummary();
tick().then(schedule);
