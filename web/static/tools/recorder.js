// Perekam kalibrasi Beta: baca baris JSON firmware lewat Web Serial, tempel label skenario aktif, unduh CSV.
// Data hanya di memori halaman ini (tidak dikirim ke mana pun) sampai tombol Download CSV ditekan.
"use strict";

const $ = (id) => document.getElementById(id);
const el = {
  connect: $("connect"), disconnect: $("disconnect"), status: $("status"), labels: $("labels"), chart: $("chart"),
  legend: $("legend"), latest: $("latest"), download: $("download"), clear: $("clear"), rows: $("rows"),
  noSerial: $("no-serial"),
};
const SENSORS = [["mq2_mv", "MQ-2", "#5aa2ff"], ["mq3_mv", "MQ-3", "#e3b23c"], ["mq7_mv", "MQ-7", "#b591f2"],
  ["mq135_mv", "MQ-135", "#4fc27f"]];
const WINDOW_MS = 10 * 60 * 1000;
let port = null, reader = null, label = "none", records = [];
const seconds = { clean_air: 0, smoke: 0, alcohol: 0, smoke_alcohol: 0 };

function say(text, kind = "") { el.status.textContent = text; el.status.dataset.kind = kind; }

el.legend.replaceChildren(...SENSORS.map(([, name, c]) => {
  const s = document.createElement("span");
  s.style.setProperty("--c", c);
  s.textContent = name;
  return s;
}));

el.labels.addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-label]");
  if (!b) return;
  label = b.dataset.label;
  el.labels.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
});

function fmt(s) { return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; }

function onLine(line) {
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  if (msg.mq2_mv == null) {
    if (msg.event) say(`Device: ${msg.event}${msg.status ? ` (${msg.status})` : ""}`);
    return;
  }
  const now = new Date();
  const prev = records[records.length - 1];
  records.push({ t: now, uptime_s: msg.uptime_s, node_id: msg.node_id, label,
    ...Object.fromEntries(SENSORS.map(([k]) => [k, msg[k]])) });
  if (label in seconds && prev) seconds[label] += Math.min(10, (now - prev.t) / 1000);
  document.querySelectorAll("[data-count]").forEach((d) => { d.textContent = fmt(seconds[d.dataset.count]); });
  el.latest.textContent = `Latest: ${SENSORS.map(([k, n]) => `${n} ${msg[k]} mV`).join(" · ")} · label ${label}`;
  el.rows.textContent = `${records.length} readings recorded.`;
  el.download.disabled = el.clear.disabled = records.length === 0;
  draw();
}

const NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}
function draw() {
  const W = Math.max(320, Math.round(el.chart.clientWidth || 640)), H = 240, P = { l: 48, r: 10, t: 10, b: 24 };
  el.chart.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const now = Date.now(), x0 = now - WINDOW_MS;
  const recent = records.filter((r) => r.t.getTime() >= x0);
  const kids = [el.chart.querySelector("desc")];
  if (recent.length) {
    const vals = recent.flatMap((r) => SENSORS.map(([k]) => r[k]));
    const lo = Math.max(0, Math.min(...vals) - 50), hi = Math.max(...vals) + 50;
    const x = (t) => P.l + ((t - x0) / WINDOW_MS) * (W - P.l - P.r);
    const y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
    for (const v of [lo, (lo + hi) / 2, hi]) {
      kids.push(svg("line", { class: "grid", x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
      kids.push(svg("text", { class: "axis", x: P.l - 6, y: y(v) + 4, "text-anchor": "end" }, Math.round(v)));
    }
    for (const [k, , c] of SENSORS) {
      const d = recent.map((r, i) => `${i ? "L" : "M"}${x(r.t.getTime()).toFixed(1)},${y(r[k]).toFixed(1)}`).join("");
      kids.push(svg("path", { d, fill: "none", stroke: c, "stroke-width": 2 }));
    }
    kids.push(svg("text", { class: "axis", x: P.l, y: H - 6 }, "10 min ago"));
    kids.push(svg("text", { class: "axis", x: W - P.r, y: H - 6, "text-anchor": "end" }, "now"));
  }
  el.chart.replaceChildren(...kids);
}

async function readLoop() {
  const decoder = new TextDecoderStream();
  const closed = port.readable.pipeTo(decoder.writable).catch(() => {});
  reader = decoder.readable.getReader();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (line) onLine(line);
      }
    }
  } catch { /* port ditutup */ }
  await closed;
}

el.connect.addEventListener("click", async () => {
  try {
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: 115200 });
  } catch (e) {
    say(e && e.name === "NotFoundError" ? "No device selected." : `Could not open the port: ${e.message || e}`, "error");
    return;
  }
  el.connect.disabled = true;
  el.disconnect.disabled = false;
  say("Connected. Waiting for readings (one every 2 seconds)…", "ok");
  readLoop();
});

el.disconnect.addEventListener("click", async () => {
  try { if (reader) await reader.cancel(); } catch { /* sudah tertutup */ }
  try { await port.close(); } catch { /* sudah tertutup */ }
  port = reader = null;
  el.connect.disabled = false;
  el.disconnect.disabled = true;
  say("Disconnected. The recording stays on this page until you download or clear it.");
});

el.download.addEventListener("click", () => {
  const head = ["timestamp", "uptime_s", "node_id", ...SENSORS.map(([k]) => k), "label"];
  const rows = records.map((r) => [r.t.toISOString(), r.uptime_s ?? "", r.node_id ?? "", ...SENSORS.map(([k]) => r[k]),
    r.label]);
  const csv = [head, ...rows].map((row) => row.join(",")).join("\n") + "\n";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const node = (records[0] && records[0].node_id) || "beta";
  a.download = `airlens_beta_recording_${node}_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "")}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
  records.saved = records.length;
});

el.clear.addEventListener("click", () => {
  if (records.length && !confirm("Delete all recorded readings from this page?")) return;
  records = [];
  Object.keys(seconds).forEach((k) => { seconds[k] = 0; });
  document.querySelectorAll("[data-count]").forEach((d) => { d.textContent = "0:00"; });
  el.rows.textContent = "0 readings recorded.";
  el.download.disabled = el.clear.disabled = true;
  draw();
});

window.addEventListener("beforeunload", (ev) => {
  if (records.length && records.saved !== records.length) { ev.preventDefault(); ev.returnValue = ""; }
});

if (!("serial" in navigator)) {
  el.noSerial.hidden = false;
  el.connect.disabled = true;
  say("Connect a device: not available in this browser.", "error");
}
