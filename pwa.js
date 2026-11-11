/* TRL 앱 설치(PWA) — 서비스 워커 등록 + '📲 앱 설치' 버튼 + '🔔 알림 받기'(웹 푸시). 2026-11-12 */
const VAPID_PUBLIC = "BKwWSi_sQqLn6ROiJ8CR0AecFzcWyuYUvjQ_cps6NNVinyzus6NKCbP2DNWXT4lpOu9SYZ8nUh4LeIow3QIAxUA";   // tools/push_notify.py 개인 키와 짝
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  const btn = document.getElementById("installBtn");
  if (!btn || standalone) return;                       // 이미 앱으로 열었으면 버튼 숨김
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => {   // 안드로이드·PC 크롬·엣지
    e.preventDefault(); deferred = e; btn.hidden = false;
  });
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (ios) btn.hidden = false;                            // 아이폰은 사파리 '홈 화면에 추가'로 안내
  btn.addEventListener("click", async () => {
    if (deferred) {
      deferred.prompt();
      await deferred.userChoice.catch(() => null);
      deferred = null; btn.hidden = true;
    } else if (ios) {
      alert("아이폰: 사파리 아래쪽 공유 버튼(□↑) → '홈 화면에 추가'를 누르면 TRL 앱이 설치됩니다.");
    } else {
      alert("브라우저 메뉴(⋮) → '앱 설치' 또는 '홈 화면에 추가'를 누르세요.");
    }
  });
  window.addEventListener("appinstalled", () => { btn.hidden = true; });
})();

/* 🔔 알림 받기: 이 기기의 받는 주소를 만들어 '코드'로 보여 준다 → 노트북에서 push_notify.py add 로 한 번 등록 */
(function () {
  const btn = document.getElementById("pushBtn");
  if (!btn || !("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  btn.hidden = false;
  const b64 = (s) => btoa(unescape(encodeURIComponent(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const key = (s) => { const p = "=".repeat((4 - s.length % 4) % 4), r = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(r, (c) => c.charCodeAt(0)); };
  btn.addEventListener("click", async () => {
    if (ios && !standalone) { alert("아이폰은 먼저 '홈 화면에 추가'로 TRL 앱을 설치한 뒤, 그 앱에서 '알림 받기'를 눌러 주세요."); return; }
    try {
      if ((await Notification.requestPermission()) !== "granted") { alert("알림이 꺼져 있습니다. 휴대폰 설정에서 TRL(또는 브라우저) 알림을 허용해 주세요."); return; }
      const reg = await navigator.serviceWorker.ready;
      const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key(VAPID_PUBLIC) });
      const code = "TRLPUSH:" + b64(JSON.stringify(sub.toJSON()));
      try { await navigator.clipboard.writeText(code); alert("알림 코드를 복사했습니다.\n카톡 '나에게'나 Claude에게 붙여 넣어 보내 주시면 이 기기를 등록합니다(한 번만)."); }
      catch { prompt("아래 알림 코드를 길게 눌러 복사한 뒤 Claude에게 보내 주세요(한 번만).", code); }
    } catch (e) { alert("알림 등록 실패: " + (e && e.message ? e.message : e)); }
  });
})();
