// Service worker AirLens: menampilkan notifikasi kejadian (dari halaman yang terbuka atau dari Web Push saat tertutup)
// dan membuka halaman yang relevan saat notifikasi diketuk. Tidak menyimpan cache apa pun (website tetap online-only).
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

function show(n) {
  return self.registration.showNotification(n.title || "AirLens", {
    body: n.body || "",
    tag: n.tag || "airlens",           // tag sama = notifikasi halaman dan push digabung, tidak dobel
    icon: "/icons/airlens-192.png",
    badge: "/icons/airlens-192.png",
    data: { url: n.url || "/" },
    requireInteraction: n.priority === "high",
    renotify: false,
  });
}

self.addEventListener("push", (e) => {
  let n;
  try { n = e.data ? e.data.json() : {}; } catch { n = { title: "AirLens", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(show(n));
});

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "show") e.waitUntil(show(e.data.notification || {}));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) {
      if (new URL(c.url).pathname === url && "focus" in c) return c.focus();
    }
    return self.clients.openWindow(url);
  }));
});
