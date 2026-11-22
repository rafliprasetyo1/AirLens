// Banner kejadian (halaman Beta). Sumber: GET /api/events/latest lalu SSE /api/events/stream.
// Kejadian datang dari trigger engine (config/triggers.yaml); halaman tidak memutuskan apa pun sendiri.
// Pemakaian: <div class="event-banner" data-airlens-events data-room="booth" hidden></div> + skrip ini.
// Semua teks dipasang dengan textContent. Notifikasi sistem dan Web Push menyusul di Tahap 4.
"use strict";

(() => {
  const box = document.querySelector("[data-airlens-events]");
  if (!box) return;
  const room = box.dataset.room || "booth";
  const TITLES = {
    smoke_confirmed: "Smoke confirmed",
    invisible_gas: "Gas detected",
    visible_smoke: "Visible smoke",
    back_to_normal: "Back to normal",
  };
  const NORMAL_SHOW_MS = 120000;   // "Back to normal" tetap terlihat 2 menit, lalu banner disembunyikan
  let hideTimer = 0, source = null, retry = 0;

  const time = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  function show(ev) {
    clearTimeout(hideTimer);
    const normal = ev.kind === "back_to_normal";
    const age = Date.now() - new Date(ev.at).getTime();
    if (normal && age > NORMAL_SHOW_MS) { box.hidden = true; return; }

    const title = document.createElement("p");
    title.className = "event-title";
    title.textContent = TITLES[ev.kind] || ev.kind;
    if (ev.simulated) {
      const tag = document.createElement("span");
      tag.className = "event-sim";
      tag.textContent = "Simulated";
      title.append(" ", tag);
    }
    const msg = document.createElement("p");
    msg.className = "event-msg";
    msg.textContent = ev.message;
    const meta = document.createElement("p");
    meta.className = "event-meta";
    const who = (ev.sources || []).join(", ");
    meta.textContent = `${time(ev.at)}${who ? ` · ${who}` : ""}`;

    box.replaceChildren(title, msg, meta);
    box.dataset.kind = ev.kind;
    box.dataset.priority = ev.priority;
    // Prioritas tinggi diumumkan segera oleh pembaca layar; sisanya sopan.
    box.setAttribute("role", ev.priority === "high" ? "alert" : "status");
    box.hidden = false;
    if (normal) hideTimer = setTimeout(() => { box.hidden = true; }, NORMAL_SHOW_MS - age);
  }

  async function initial() {
    try {
      const r = await fetch(`/api/events/latest?room=${encodeURIComponent(room)}`, { cache: "no-store" });
      if (!r.ok) return;
      const { event, state } = await r.json();
      if (!event) return;
      // Keadaan normal + kejadian lama: tidak ada yang perlu ditampilkan.
      if (!state.current || state.current === "back_to_normal") {
        if (event.kind === "back_to_normal") show(event);
        return;
      }
      show(event);
    } catch { /* jaringan putus: SSE akan mencoba lagi */ }
  }

  // Saat alerts aktif (shared/alerts.js), koneksi tetap dibuka di tab latar belakang agar notifikasi tetap masuk.
  const keepOpen = () => { try { return localStorage.getItem("airlens-alerts") === "on"; } catch { return false; } };

  function connect() {
    if (source || (document.hidden && !keepOpen())) return;
    source = new EventSource(`/api/events/stream?room=${encodeURIComponent(room)}`);
    source.addEventListener("kejadian", (e) => {
      retry = 0;
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; /* pesan rusak diabaikan */ }
      show(ev);
      // kejadian BARU (bukan keadaan awal) diteruskan ke shared/alerts.js untuk notifikasi sistem
      window.dispatchEvent(new CustomEvent("airlens:event", { detail: ev }));
    });
    source.onerror = () => {
      source.close();
      source = null;
      retry = Math.min(retry + 1, 6);
      setTimeout(() => { initial(); connect(); }, 1000 * 2 ** retry);
    };
  }

  // Tab tersembunyi: tutup koneksi (hemat baterai di HP); saat kembali, ambil keadaan terakhir lalu sambung lagi.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && !keepOpen()) { if (source) { source.close(); source = null; } }
    else { initial(); connect(); }
  });
  initial();
  connect();
})();
