/* Zaply service worker — app shell caching + offline fallback.
   API responses are never cached (always live).
   Code files (css/js/html) are network-first so updates apply immediately;
   images and other statics are stale-while-revalidate. */
const VERSION = "zaply-v12";
const SHELL = [
  "/",
  "/css/styles.css",
  "/css/admin.css",
  "/js/app.js",
  "/js/api.js",
  "/js/ui.js",
  "/js/icons.js",
  "/offline.html",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  // allSettled: one missing asset must never leave a zombie service worker
  e.waitUntil(
    caches.open(VERSION)
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("push", (e) => {
  let data = { title: ElevenData, body: "You have a new notification" };
  try {
    data = e.data.json();
  } catch {}

  const options = {
    body: data.body,
    icon: "/img/icon-192.png",
    badge: "/img/icon-192.png",
    vibrate: [100, 50, 100],
    data: { url: data.url || "/" },
  };

  e.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = e.notification.data?.url || "/";
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((winn) => {
      for (const w of winn) {
        if (w.url.includes(location.origin) && "focus" in w) {
          w.navigate(url);
          return w.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // Never cache API traffic — wallet data must be live.
  if (url.pathname.startsWith("/api/")) return;

  // Page navigations: network first, fall back to cache, then offline page.
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() =>
          caches.match(e.request).then((hit) => hit || caches.match("/offline.html"))
        )
    );
    return;
  }

  // Code files: network-first — always prefer fresh, cache is only a fallback.
  if (/\.(css|js|mjs|json|webmanifest)$/.test(url.pathname)) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(e.request, copy));
          }
          return res;
        })
        .catch(() => caches.match(e.request).then((hit) => hit || Response.error()))
    );
    return;
  }

  // Images & other statics: stale-while-revalidate.
  e.respondWith(
    caches.match(e.request).then((hit) => {
      const refresh = fetch(e.request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(e.request, copy));
          }
          return res;
        })
        .catch(() => hit);
      return hit || refresh;
    })
  );
});
