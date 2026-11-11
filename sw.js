/* TRL 앱(PWA) 서비스 워커 — 2026-11-12
 * 시세·속보가 1분마다 바뀌는 사이트라 '네트워크 먼저': 항상 최신을 받고, 인터넷이 끊겼을 때만 마지막으로 본 화면을 보여 준다.
 * 다른 사이트(시세 API·폰트 등) 요청은 건드리지 않는다. 화면 파일을 바꾸면 VERSION 을 올린다.
 */
const VERSION = "trl-app-v1";
const SHELL = ["./", "index.html", "study.html", "style.css", "app.js", "news.js", "chart.js", "count.js",
  "manifest.webmanifest", "pwa.js", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;   // 외부 요청은 그대로
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }).then((hit) => hit || caches.match("./")))
  );
});
