// Notifikasi kejadian AirLens untuk semua halaman: tombol lonceng di header + panel "Enable alerts" (Beta, Live).
// Izin notifikasi HANYA diminta saat tombol ditekan. Sumber kejadian: trigger engine lewat SSE (/api/events/stream);
// teks notifikasi datang dari server (event.notification), sama dengan Web Push. Notifikasi ditampilkan lewat service
// worker (registration.showNotification), karena `new Notification()` tidak berjalan di Chrome Android.
// Di halaman: getar singkat dan bunyi pendek (bisa dimatikan). Web Push (website tertutup) aktif bila server punya kunci
// VAPID. Yang disimpan di server hanya subscription push; di browser hanya pilihan aktif/bunyi (localStorage).
"use strict";

(() => {
  const KEY = "airlens-alerts", SOUND = "airlens-alert-sound";
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* mode privat */ } } };
  const supported = "Notification" in window && "serviceWorker" in navigator;
  const pushSupported = supported && "PushManager" in window;
  let enabled = store.get(KEY) === "on" && supported && Notification.permission === "granted";
  let audio = null, source = null;

  // ---------------------------------------------------------------- UI: lonceng di header + panel
  const bell = document.createElement("button");
  bell.type = "button";
  bell.className = "alerts-bell";
  bell.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M12 3a6 6 0 0 0-6 6v3.6L4.3 15.4A1 1 0 0 0 5.2 17h13.6a1 1 0 0 0 .9-1.6L18 12.6V9a6 6 0 0 0-6-6zm0 19a3 3 0 0 0 2.8-2H9.2A3 3 0 0 0 12 22z" fill="currentColor"/></svg><span class="sr-only"></span>';
  const nav = document.querySelector("header .site-nav");
  if (nav) nav.insertAdjacentElement("afterend", bell);
  const panel = document.querySelector("[data-airlens-alerts-panel]");
  const pBtn = panel && panel.querySelector("[data-alerts-toggle]");
  const pSound = panel && panel.querySelector("[data-alerts-sound]");
  const pMsg = panel && panel.querySelector("[data-alerts-status]");

  function say(text) { if (pMsg) pMsg.textContent = text; }
  function render() {
    bell.setAttribute("aria-pressed", String(enabled));
    bell.title = enabled ? "Alerts on (click to turn off)" : "Enable alerts";
    bell.querySelector(".sr-only").textContent = enabled ? "Alerts on" : "Enable alerts";
    if (pBtn) pBtn.textContent = enabled ? "Disable alerts" : "Enable alerts";
    if (pSound) pSound.checked = store.get(SOUND) !== "off";
    if (!supported) say("This browser can't show notifications. On iPhone, add AirLens to the Home Screen first (iOS 16.4+).");
  }

  // ---------------------------------------------------------------- service worker + push
  async function registration() {
    return navigator.serviceWorker.register("/sw.js");
  }
  function b64ToBytes(b64) {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }
  async function subscribePush(reg) {
    if (!pushSupported) return "page";
    const r = await fetch("/api/push/public-key", { cache: "no-store" });
    if (!r.ok) return "page";                                   // server tanpa kunci VAPID: hanya saat tab terbuka
    const { public_key } = await r.json();
    let sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(public_key) });
    const j = sub.toJSON();
    await fetch("/api/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint: j.endpoint, keys: j.keys }) });
    return "push";
  }

  async function enable() {
    if (!supported) { render(); return; }
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { say("Notifications are blocked. Allow them in the browser's site settings."); return; }
    const reg = await registration();
    unlockAudio();
    // Notifikasi halaman langsung aktif; Web Push dicoba di latar (bisa lambat atau tidak tersedia di browser ini).
    enabled = true;
    store.set(KEY, "on");
    say("Alerts on while this site is open. Setting up alerts for when it is closed…");
    render();
    listen();
    const timeout = new Promise((resolve) => setTimeout(() => resolve("timeout"), 10000));
    let mode;
    try { mode = await Promise.race([subscribePush(reg), timeout]); } catch { mode = "page"; }
    if (!enabled) return;
    say(mode === "push" ? "Alerts on. They also arrive when this site is closed (Android Chrome; iPhone via Home Screen)."
      : "Alerts on while this site is open. Closed-site alerts are not available in this browser.");
  }

  async function disable() {
    enabled = false;
    store.set(KEY, "off");
    try {
      const reg = await navigator.serviceWorker.getRegistration("/");
      const sub = reg && (await reg.pushManager.getSubscription());
      if (sub) {
        await fetch("/api/push/unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }) });
        await sub.unsubscribe();
      }
    } catch { /* tetap dimatikan di halaman ini */ }
    if (source) { source.close(); source = null; }
    say("Alerts off.");
    render();
  }

  const toggle = () => (enabled ? disable() : enable());
  bell.addEventListener("click", toggle);
  if (pBtn) pBtn.addEventListener("click", toggle);
  if (pSound) pSound.addEventListener("change", () => store.set(SOUND, pSound.checked ? "on" : "off"));

  // ---------------------------------------------------------------- reaksi terhadap kejadian
  function unlockAudio() {
    try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); audio.resume(); } catch { audio = null; }
  }
  function beep(high) {
    if (!audio || store.get(SOUND) === "off") return;
    const o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = high ? 880 : 520;
    g.gain.setValueAtTime(0.0001, audio.currentTime);
    g.gain.exponentialRampToValueAtTime(0.2, audio.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.35);
    o.connect(g).connect(audio.destination);
    o.start(); o.stop(audio.currentTime + 0.4);
  }
  async function onEvent(ev) {
    if (!enabled || !ev || !ev.notification) return;
    const n = ev.notification, high = n.priority === "high";
    try {
      const reg = await navigator.serviceWorker.ready;
      await reg.showNotification(n.title, { body: n.body, tag: n.tag, icon: "/icons/airlens-192.png",
        data: { url: n.url }, requireInteraction: high, renotify: false });
    } catch { /* izin dicabut */ }
    if (n.kind !== "back_to_normal") {
      if (navigator.vibrate) navigator.vibrate(high ? [200, 100, 200] : 150);
      beep(high);
    }
  }
  // Halaman dengan banner kejadian (Beta, Live) sudah membuka SSE di shared/events.js: cukup dengarkan.
  window.addEventListener("airlens:event", (e) => onEvent(e.detail));
  function listen() {
    if (!enabled || source || document.querySelector("[data-airlens-events]")) return;
    source = new EventSource("/api/events/stream");
    source.addEventListener("kejadian", (e) => { try { onEvent(JSON.parse(e.data)); } catch { /* abaikan */ } });
    source.onerror = () => { source.close(); source = null; setTimeout(listen, 5000); };
  }

  if (enabled) registration().catch(() => {});
  render();
  listen();
})();
