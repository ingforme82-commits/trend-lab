/* TRL 앱(PWA) 서비스 워커 — 2026-11-12
 * 시세·속보가 1분마다 바뀌는 사이트라 '네트워크 먼저': 항상 최신을 받고, 인터넷이 끊겼을 때만 마지막으로 본 화면을 보여 준다.
 * 다른 사이트(시세 API·폰트 등) 요청은 건드리지 않는다. 화면 파일을 바꾸면 VERSION 을 올린다.
 */
const VERSION = "trl-app-v83-index-quotes-four-tabs-quotes-core-layout-desktop-nav-market-notices-country-notices-tw-five-core-nav-archive-record-archive-overview-archive-only-scroll-stability-ant-locale-colors-chart-news-newest-lev-price-fix-trend-level-clean-nxt-single-quote-kr-us-overlap-bold-ma5-asia-etn-refresh-validate-feed-preserve-trends-require-chan-require-populated-markets-apply-trend-early-fix-horizontal-index-krx-after-hours-global-sector-tsms-flow-remove-lev-summary-nxt-close-two-price-cards-wti-hl-perp-stale-session-s7-kosdaq-flow-s7-inst-remove-koru-sksq-tsmx-twse-stock-quotes-cco-text-1-dedupe-skhx-mkt-notice-chan-loop-fix-close-two-cells-global-list-color-mobile-dedupe";
const SHELL = ["./", "index.html", "study.html", "localize.js", "i18n-ui.js", "gtranslate.js", "langauto.js", "style.css", "app.js", "news.js", "viewport.js", "chart.js", "count.js", "fold.js", "tint.js",
  "manifest.webmanifest", "pwa.js", "presence.js", "flow-core.js", "flow.js", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

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

/* 앱 푸시(노트북의 tools/push_notify.py 가 보냄) — 2026-11-12 */
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "TRL", {
    body: d.body || "", tag: d.tag || undefined, icon: "icons/icon-192.png", badge: "icons/icon-192.png",
    data: { url: d.url || "./" },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "./";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
    for (const w of ws) { if ("focus" in w) { w.navigate(url).catch(() => {}); return w.focus(); } }
    return self.clients.openWindow(url);
  }));
});
